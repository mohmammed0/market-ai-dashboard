from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.engine import make_url
from sqlalchemy import select

from backend.app.core.logging_utils import get_logger, log_event
from backend.app.config import ALPACA_ACCOUNT_REFRESH_SECONDS, AUTO_TRADING_CYCLE_MINUTES, DATABASE_URL
from backend.app.models.runtime_settings import RuntimeSetting
from backend.app.services.cache import get_cache
from backend.app.services.storage import session_scope
from core.runtime_paths import SETTINGS_KEY_PATH, ensure_runtime_directories, sqlite_file_path

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - optional dependency at runtime
    Fernet = None
    InvalidToken = Exception


class RuntimeSettingsError(RuntimeError):
    pass


logger = get_logger(__name__)


@dataclass(frozen=True)
class SettingSpec:
    key: str
    env_name: str
    default: Any
    kind: str = "text"
    secret: bool = False


SETTING_SPECS: dict[str, SettingSpec] = {
    "broker.provider": SettingSpec("broker.provider", "MARKET_AI_BROKER_PROVIDER", "none"),
    "broker.order_submission_enabled": SettingSpec(
        "broker.order_submission_enabled",
        "MARKET_AI_BROKER_ORDER_SUBMISSION_ENABLED",
        False,
        kind="bool",
    ),
    "broker.live_execution_enabled": SettingSpec(
        "broker.live_execution_enabled",
        "MARKET_AI_BROKER_LIVE_EXECUTION_ENABLED",
        False,
        kind="bool",
    ),
    "alpaca.enabled": SettingSpec("alpaca.enabled", "MARKET_AI_ALPACA_ENABLED", False, kind="bool"),
    "alpaca.api_key": SettingSpec("alpaca.api_key", "ALPACA_API_KEY", "", secret=True),
    "alpaca.secret_key": SettingSpec("alpaca.secret_key", "ALPACA_SECRET_KEY", "", secret=True),
    "alpaca.paper": SettingSpec("alpaca.paper", "ALPACA_PAPER", True, kind="bool"),
    "alpaca.url_override": SettingSpec("alpaca.url_override", "ALPACA_URL_OVERRIDE", ""),
    "auto_trading.enabled": SettingSpec(
        "auto_trading.enabled",
        "MARKET_AI_AUTO_TRADING_ENABLED",
        False,
        kind="bool",
    ),
    "auto_trading.cycle_minutes": SettingSpec(
        "auto_trading.cycle_minutes",
        "MARKET_AI_AUTO_TRADING_CYCLE_MINUTES",
        AUTO_TRADING_CYCLE_MINUTES,
        kind="int",
    ),
}

_ALPACA_API_VERSION_SEGMENTS = {"v1", "v2", "v2beta1"}
_ALPACA_TRADING_ENDPOINT_SEGMENTS = {
    "account",
    "orders",
    "positions",
    "clock",
    "calendar",
    "assets",
    "watchlists",
    "options",
    "corporate_actions",
}
_ALPACA_TRADING_HOSTS = {"api.alpaca.markets", "paper-api.alpaca.markets"}
_ALPACA_INVALID_TRADING_HOSTS = {
    "broker-api.alpaca.markets",
    "broker-api.sandbox.alpaca.markets",
    "data.alpaca.markets",
    "data.sandbox.alpaca.markets",
    "stream.data.alpaca.markets",
    "stream.data.sandbox.alpaca.markets",
}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    return text not in {"0", "false", "no", "off"}


def _coerce_text(value: Any, default: str = "") -> str:
    if value is None:
        return str(default)
    text = str(value).strip()
    return text or str(default)


def _normalize_alpaca_url_override(value: Any) -> str:
    text = _coerce_text(value, default="")
    if not text:
        return ""

    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    if scheme not in {"http", "https"} or not host or host in _ALPACA_INVALID_TRADING_HOSTS:
        return ""

    segments = [segment for segment in parsed.path.split("/") if segment]
    lower_segments = [segment.lower() for segment in segments]
    cut_index = None

    for index, segment in enumerate(lower_segments):
        if segment in _ALPACA_API_VERSION_SEGMENTS:
            cut_index = index
            break

    if cut_index is None and host in _ALPACA_TRADING_HOSTS:
        for index, segment in enumerate(lower_segments):
            if segment in _ALPACA_TRADING_ENDPOINT_SEGMENTS:
                cut_index = index
                break

    if cut_index is not None:
        segments = segments[:cut_index]

    normalized_path = "/" + "/".join(segments) if segments else ""
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path.rstrip("/"), "", ""))


def _serialize_value(spec: SettingSpec, value: Any) -> str:
    if spec.kind == "bool":
        return "1" if _coerce_bool(value, default=bool(spec.default)) else "0"
    if spec.kind == "int":
        try:
            return str(int(value))
        except Exception:
            return str(int(spec.default))
    return _coerce_text(value, default=str(spec.default))


def _deserialize_value(spec: SettingSpec, value: str | None) -> Any:
    if spec.kind == "bool":
        return _coerce_bool(value, default=bool(spec.default))
    if spec.kind == "int":
        try:
            return int(str(value).strip())
        except Exception:
            return int(spec.default)
    return _coerce_text(value, default=str(spec.default))


def _secret_mask(value: str | None) -> str | None:
    text = _coerce_text(value, default="")
    if not text:
        return None
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _redact_text(message: str, secrets: list[str | None]) -> str:
    result = str(message or "").strip()
    for secret in secrets:
        text = _coerce_text(secret, default="")
        if text:
            result = result.replace(text, "***")
    return result


def _describe_database_runtime(database_url: str) -> dict[str, Any]:
    sqlite_path = sqlite_file_path(database_url)
    payload: dict[str, Any] = {
        "driver": None,
        "database_name": None,
        "host": None,
        "port": None,
        "path": None if sqlite_path is None else str(sqlite_path),
        "credentials_present": False,
    }
    try:
        parsed = make_url(database_url)
    except Exception:
        return payload

    payload["driver"] = parsed.drivername
    payload["database_name"] = parsed.database
    payload["host"] = parsed.host
    payload["port"] = parsed.port
    payload["credentials_present"] = bool(parsed.username or parsed.password)
    return payload


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    if Fernet is None:
        raise RuntimeSettingsError("cryptography is not installed in the backend environment.")
    ensure_runtime_directories()
    key_path = Path(SETTINGS_KEY_PATH)
    if key_path.exists():
        key = key_path.read_bytes().strip()
    else:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            key_path.chmod(0o600)
        except Exception:
            pass
    return Fernet(key)


def _encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_secret(value: str | None) -> str:
    text = _coerce_text(value, default="")
    if not text:
        return ""
    try:
        return _fernet().decrypt(text.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeSettingsError("Stored runtime secret could not be decrypted.") from exc


def _records_by_key() -> dict[str, dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                select(RuntimeSetting.key, RuntimeSetting.value_text, RuntimeSetting.is_secret)
            ).all()
            return {
                row.key: {
                    "value_text": row.value_text,
                    "is_secret": bool(row.is_secret),
                }
                for row in rows
            }
    except Exception:
        return {}


def _resolve_setting(key: str, records: dict[str, dict[str, Any]] | None = None) -> tuple[Any, str]:
    spec = SETTING_SPECS[key]
    rows = records if records is not None else _records_by_key()
    record = rows.get(key)
    if record and record.get("value_text") is not None:
        raw_value = _decrypt_secret(record.get("value_text")) if spec.secret else record.get("value_text")
        return _deserialize_value(spec, raw_value), "ui_managed"
    if spec.env_name in os.environ:
        return _deserialize_value(spec, os.environ.get(spec.env_name)), "environment"
    return spec.default, "default"


def _sdk_installed(package: str) -> bool:
    try:
        __import__(package)
        return True
    except Exception:
        return False


def _build_broker_payload(records: dict[str, dict[str, Any]] | None = None, *, include_secrets: bool = False) -> dict:
    provider, provider_source = _resolve_setting("broker.provider", records)
    order_submission_enabled, order_submission_source = _resolve_setting("broker.order_submission_enabled", records)
    live_execution_enabled, live_execution_source = _resolve_setting("broker.live_execution_enabled", records)
    alpaca_enabled, alpaca_enabled_source = _resolve_setting("alpaca.enabled", records)
    alpaca_api_key, alpaca_api_key_source = _resolve_setting("alpaca.api_key", records)
    alpaca_secret_key, alpaca_secret_key_source = _resolve_setting("alpaca.secret_key", records)
    alpaca_paper, alpaca_paper_source = _resolve_setting("alpaca.paper", records)
    alpaca_url_override, alpaca_url_override_source = _resolve_setting("alpaca.url_override", records)
    alpaca_url_override = _normalize_alpaca_url_override(alpaca_url_override)

    alpaca_sdk_installed = _sdk_installed("alpaca")
    alpaca_configured = bool(alpaca_api_key and alpaca_secret_key)
    provider_name = _coerce_text(provider, default="none").lower()

    if provider_name != "alpaca":
        detail = "Broker integration is disabled."
        status = "disabled"
    elif not alpaca_enabled:
        detail = "Alpaca integration is disabled."
        status = "standby"
    elif not alpaca_sdk_installed:
        detail = "alpaca-py is not installed in the backend environment."
        status = "error"
    elif not alpaca_configured:
        detail = "Alpaca API credentials are not configured."
        status = "warning"
    else:
        detail = "Alpaca credentials are configured."
        status = "ready"

    auto_trading_enabled, auto_trading_source = _resolve_setting("auto_trading.enabled", records)
    auto_trading_cycle_minutes, auto_trading_cycle_source = _resolve_setting("auto_trading.cycle_minutes", records)
    return {
        "provider": provider_name,
        "provider_source": provider_source,
        "order_submission_enabled": bool(order_submission_enabled),
        "order_submission_source": order_submission_source,
        "live_execution_enabled": bool(live_execution_enabled),
        "live_execution_source": live_execution_source,
        "auto_trading_enabled": bool(auto_trading_enabled),
        "auto_trading_source": auto_trading_source,
        "auto_trading_cycle_minutes": int(auto_trading_cycle_minutes),
        "auto_trading_cycle_source": auto_trading_cycle_source,
        "alpaca": {
            "enabled": bool(alpaca_enabled),
            "enabled_source": alpaca_enabled_source,
            "configured": alpaca_configured,
            "api_key": _coerce_text(alpaca_api_key, default="") if include_secrets else None,
            "api_key_masked": _secret_mask(alpaca_api_key),
            "api_key_source": alpaca_api_key_source,
            "secret_key": _coerce_text(alpaca_secret_key, default="") if include_secrets else None,
            "secret_key_masked": _secret_mask(alpaca_secret_key),
            "secret_key_source": alpaca_secret_key_source,
            "paper": bool(alpaca_paper),
            "paper_source": alpaca_paper_source,
            "url_override": _coerce_text(alpaca_url_override, default=""),
            "url_override_source": alpaca_url_override_source,
            "sdk_installed": alpaca_sdk_installed,
            "status": status,
            "detail": detail,
            "account_refresh_seconds": ALPACA_ACCOUNT_REFRESH_SECONDS,
        },
    }


def get_runtime_settings_overview() -> dict:
    records = _records_by_key()
    database = _describe_database_runtime(DATABASE_URL)
    return {
        "database": database,
        "database_path": database.get("path"),
        "credentials_precedence": ["ui_managed", "environment", "default"],
        "key_store_path": str(SETTINGS_KEY_PATH),
        "broker": _build_broker_payload(records, include_secrets=False),
    }


def get_broker_runtime_config() -> dict:
    payload = _build_broker_payload(include_secrets=True)
    alpaca = payload["alpaca"]
    return {
        "provider": payload["provider"],
        "provider_source": payload["provider_source"],
        "order_submission_enabled": payload["order_submission_enabled"],
        "order_submission_source": payload["order_submission_source"],
        "live_execution_enabled": payload["live_execution_enabled"],
        "live_execution_source": payload["live_execution_source"],
        "alpaca": {
            "enabled": alpaca["enabled"],
            "configured": alpaca["configured"],
            "api_key": alpaca["api_key"],
            "secret_key": alpaca["secret_key"],
            "paper": alpaca["paper"],
            "url_override": alpaca["url_override"],
            "sdk_installed": alpaca["sdk_installed"],
            "detail": alpaca["detail"],
        },
    }


def get_alpaca_runtime_config() -> dict:
    payload = get_broker_runtime_config()
    return {
        **payload["alpaca"],
        "provider": payload["provider"],
        "order_submission_enabled": payload["order_submission_enabled"],
        "live_execution_enabled": payload["live_execution_enabled"],
    }


def get_broker_guardrails() -> dict:
    payload = get_broker_runtime_config()
    return {
        "order_submission_enabled": payload["order_submission_enabled"],
        "live_execution_enabled": payload["live_execution_enabled"],
    }


def _upsert_setting(session, key: str, value: Any, *, secret: bool = False, delete_when_blank: bool = False) -> None:
    row = session.execute(select(RuntimeSetting).where(RuntimeSetting.key == key)).scalar_one_or_none()
    text_value = _coerce_text(value, default="")
    if delete_when_blank and not text_value:
        if row is not None:
            session.delete(row)
        return

    stored_value = _encrypt_secret(text_value) if secret and text_value else text_value
    if row is None:
        session.add(RuntimeSetting(key=key, value_text=stored_value, is_secret=secret))
        return
    row.value_text = stored_value
    row.is_secret = secret


def _delete_setting(session, key: str) -> None:
    row = session.execute(select(RuntimeSetting).where(RuntimeSetting.key == key)).scalar_one_or_none()
    if row is not None:
        session.delete(row)


def invalidate_runtime_caches() -> None:
    cache = get_cache()
    if hasattr(cache, "delete_prefix"):
        cache.delete_prefix("broker:alpaca:")


def save_alpaca_runtime_settings(
    *,
    enabled: bool,
    provider: str,
    paper: bool,
    api_key: str | None = None,
    secret_key: str | None = None,
    clear_api_key: bool = False,
    clear_secret_key: bool = False,
    url_override: str | None = None,
    auto_trading_enabled: bool | None = None,
    order_submission_enabled: bool | None = None,
    auto_trading_cycle_minutes: int | None = None,
) -> dict:
    clean_provider = _coerce_text(provider, default="alpaca").lower()
    if clean_provider not in {"alpaca", "none"}:
        clean_provider = "alpaca"
    clean_url_override = _normalize_alpaca_url_override(url_override)
    with session_scope() as session:
        _upsert_setting(session, "broker.provider", clean_provider)
        _upsert_setting(session, "alpaca.enabled", enabled)
        _upsert_setting(session, "alpaca.paper", paper)
        if clear_api_key:
            _delete_setting(session, "alpaca.api_key")
        elif api_key is not None and str(api_key).strip():
            _upsert_setting(session, "alpaca.api_key", str(api_key).strip(), secret=True)
        if clear_secret_key:
            _delete_setting(session, "alpaca.secret_key")
        elif secret_key is not None and str(secret_key).strip():
            _upsert_setting(session, "alpaca.secret_key", str(secret_key).strip(), secret=True)
        if url_override is not None:
            _upsert_setting(session, "alpaca.url_override", clean_url_override, delete_when_blank=True)
        if auto_trading_enabled is not None:
            _upsert_setting(session, "auto_trading.enabled", auto_trading_enabled)
        if auto_trading_cycle_minutes is not None:
            _upsert_setting(session, "auto_trading.cycle_minutes", max(1, min(int(auto_trading_cycle_minutes), 720)))
        if order_submission_enabled is not None:
            _upsert_setting(session, "broker.order_submission_enabled", order_submission_enabled)
    invalidate_runtime_caches()
    try:
        from backend.app.services.scheduler_runtime import sync_auto_trading_schedule

        sync_auto_trading_schedule()
    except Exception:
        pass
    overview = get_runtime_settings_overview()["broker"]
    alpaca_overview = overview.get("alpaca", {}) if isinstance(overview, dict) else {}
    log_event(
        logger,
        logging.INFO,
        "runtime_settings.alpaca.saved",
        provider=overview.get("provider"),
        enabled=alpaca_overview.get("enabled"),
        paper=alpaca_overview.get("paper"),
        api_key_updated=bool(api_key),
        secret_key_updated=bool(secret_key),
        api_key_cleared=bool(clear_api_key),
        secret_key_cleared=bool(clear_secret_key),
        auto_trading_cycle_minutes=overview.get("auto_trading_cycle_minutes"),
    )
    return overview


def test_alpaca_runtime_settings() -> dict:
    payload = get_alpaca_runtime_config()
    mode = "paper" if payload["paper"] else "live"
    secrets = [payload["api_key"], payload["secret_key"]]
    if payload["provider"] != "alpaca":
        result = {"ok": False, "detail": "Broker provider is disabled.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="provider_disabled", mode=mode)
        return result
    if not payload["enabled"]:
        result = {"ok": False, "detail": "Alpaca integration is disabled.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="disabled", mode=mode)
        return result
    if not payload["configured"]:
        result = {"ok": False, "detail": "Alpaca API credentials are not configured.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="missing_keys", mode=mode)
        return result
    if not payload["sdk_installed"]:
        result = {"ok": False, "detail": "alpaca-py is not installed.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="sdk_missing", mode=mode)
        return result

    try:
        from alpaca.trading.client import TradingClient
    except Exception:
        result = {"ok": False, "detail": "alpaca-py is not installed.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="sdk_missing", mode=mode)
        return result

    try:
        kwargs = {"paper": payload["paper"]}
        if payload["url_override"]:
            kwargs["url_override"] = payload["url_override"]
        client = TradingClient(payload["api_key"], payload["secret_key"], **kwargs)
        account = client.get_account()
        result = {
            "ok": True,
            "detail": f"Connected to Alpaca {mode} account.",
            "mode": mode,
            "account_id": str(getattr(account, "id", "") or ""),
            "account_status": str(getattr(account, "status", "") or ""),
        }
        log_event(logger, logging.INFO, "runtime_settings.alpaca.test", ok=True, mode=mode, account_status=result["account_status"])
        return result
    except Exception as exc:  # pragma: no cover - external service
        detail = _redact_text(str(exc) or "Alpaca connection test failed.", secrets)
        result = {"ok": False, "detail": detail, "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="connection_failed", mode=mode, detail=detail)
        return result


def get_auto_trading_config() -> dict:
    """Get auto-trading configuration from runtime settings."""
    auto_enabled, auto_source = _resolve_setting("auto_trading.enabled")
    cycle_minutes, cycle_source = _resolve_setting("auto_trading.cycle_minutes")
    order_sub, order_sub_source = _resolve_setting("broker.order_submission_enabled")
    alpaca_config = get_alpaca_runtime_config()
    return {
        "auto_trading_enabled": bool(auto_enabled),
        "auto_trading_source": auto_source,
        "cycle_minutes": int(cycle_minutes),
        "cycle_minutes_source": cycle_source,
        "order_submission_enabled": bool(order_sub),
        "alpaca_enabled": alpaca_config.get("enabled", False),
        "alpaca_configured": alpaca_config.get("configured", False),
        "alpaca_paper": alpaca_config.get("paper", True),
        "ready": bool(auto_enabled) and bool(order_sub) and alpaca_config.get("enabled", False) and alpaca_config.get("configured", False),
    }


def is_auto_trading_enabled() -> bool:
    """Quick check: is auto-trading fully enabled and configured?"""
    config = get_auto_trading_config()
    return config["ready"]
