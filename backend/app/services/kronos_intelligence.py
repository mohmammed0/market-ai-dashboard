from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from backend.app.core.logging_utils import log_event
from backend.app.services.cache import get_cache, get_cache_status
from backend.app.services.market_data import load_history
from backend.app.services.market_session_intelligence import normalize_session_state
from backend.app.services.runtime_settings import get_auto_trading_config

logger = logging.getLogger(__name__)

_PRICE_COLUMNS = ["open", "high", "low", "close"]
_FEATURE_COLUMNS = ["open", "high", "low", "close", "volume", "amount"]
_INTERVAL_FREQ = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "60m": "60min",
    "1h": "60min",
    "1d": "1D",
}


@dataclass
class _KronosRuntime:
    loaded: bool = False
    warmed: bool = False
    enabled: bool = False
    model_name: str = ""
    tokenizer_name: str = ""
    device: str = "cpu"
    error: str | None = None
    last_error_at: str | None = None
    last_inference_at: str | None = None
    last_warmup_at: str | None = None
    last_batch_inference_at: str | None = None
    last_timeout_at: str | None = None
    load_latency_ms: float = 0.0
    warmup_latency_ms: float = 0.0
    last_batch_duration_ms: float = 0.0
    last_batch_symbol_count: int = 0
    timeout_count: int = 0
    degraded_mode: bool = False
    degraded_reason: str | None = None
    predictor: Any = None
    cache: dict[str, dict] = field(default_factory=dict)


_RUNTIME = _KronosRuntime()
_LOCK = threading.Lock()
_SHARED_STATUS_KEY = "kronos:runtime:status"
_SHARED_BATCH_KEY = "kronos:runtime:batch"
_SHARED_SYMBOL_CACHE_PREFIX = "kronos:runtime:symbol"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    return text not in {"0", "false", "no", "off"}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(float(value), high))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _worker_id() -> str:
    host = str(os.getenv("HOSTNAME") or os.getenv("COMPUTERNAME") or "").strip()
    return host or f"pid-{os.getpid()}"


def _parse_iso_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _age_seconds(value: Any) -> float | None:
    parsed = _parse_iso_timestamp(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return round(max(delta.total_seconds(), 0.0), 3)


def _shared_status_ttl_seconds(config: dict) -> int:
    return max(_safe_int(config.get("kronos_cache_ttl_seconds"), 600) * 6, 3600)


def _shared_batch_ttl_seconds(config: dict) -> int:
    return max(_safe_int(config.get("kronos_cache_ttl_seconds"), 600) * 2, 1800)


def _shared_symbol_ttl_seconds(config: dict) -> int:
    return max(_safe_int(config.get("kronos_cache_ttl_seconds"), 600), 30)


def _shared_symbol_cache_storage_key(cache_key: str) -> str:
    return f"{_SHARED_SYMBOL_CACHE_PREFIX}:{cache_key}"


def _local_runtime_status_payload(config: dict) -> dict:
    cache_status = get_cache_status()
    ready = bool(
        config.get("kronos_enabled", False)
        and _RUNTIME.loaded
        and (_RUNTIME.warmed or not config.get("kronos_warmup_enabled", True))
    )
    return {
        "kronos_enabled": bool(config.get("kronos_enabled", False)),
        "kronos_loaded": bool(_RUNTIME.loaded),
        "kronos_warmed": bool(_RUNTIME.warmed),
        "kronos_model_name": _RUNTIME.model_name or config.get("kronos_model_name"),
        "kronos_tokenizer_name": _RUNTIME.tokenizer_name or config.get("kronos_tokenizer_name"),
        "kronos_device": _RUNTIME.device or _resolve_device(config.get("kronos_device_preference")),
        "kronos_ready": ready,
        "kronos_error": _RUNTIME.error,
        "kronos_last_error": _RUNTIME.error,
        "kronos_last_error_at": _RUNTIME.last_error_at,
        "kronos_last_inference_at": _RUNTIME.last_inference_at,
        "kronos_last_warmup_at": _RUNTIME.last_warmup_at,
        "kronos_last_batch_inference_at": _RUNTIME.last_batch_inference_at,
        "kronos_last_timeout_at": _RUNTIME.last_timeout_at,
        "kronos_load_latency_ms": _RUNTIME.load_latency_ms,
        "kronos_warmup_latency_ms": _RUNTIME.warmup_latency_ms,
        "kronos_last_batch_duration_ms": _RUNTIME.last_batch_duration_ms,
        "kronos_last_batch_symbol_count": int(_RUNTIME.last_batch_symbol_count),
        "kronos_timeout_count": int(_RUNTIME.timeout_count),
        "kronos_degraded_mode": bool(_RUNTIME.degraded_mode),
        "kronos_degraded_reason": _RUNTIME.degraded_reason,
        "kronos_cache_size": len(_RUNTIME.cache),
        "kronos_cache_backend": cache_status.get("provider"),
        "kronos_cache_shared": bool(cache_status.get("shared_across_processes")),
        "kronos_status_source": "process_local",
        "kronos_worker_id": _worker_id(),
        "config": config,
    }


def _load_shared_runtime_status() -> dict:
    payload = get_cache().get(_SHARED_STATUS_KEY)
    return payload if isinstance(payload, dict) else {}


def _persist_shared_runtime_status(config: dict, extra: dict | None = None) -> dict:
    payload = dict(_local_runtime_status_payload(config))
    if isinstance(extra, dict):
        payload.update({key: value for key, value in extra.items() if value is not None})
    payload["kronos_status_source"] = "shared"
    payload["kronos_worker_id"] = _worker_id()
    payload["kronos_updated_at"] = _now_iso()
    get_cache().set(_SHARED_STATUS_KEY, payload, ttl_seconds=_shared_status_ttl_seconds(config))
    return payload


def get_kronos_batch_cache_snapshot(*, auto_config: dict | None = None, include_symbols: bool = False) -> dict:
    config = get_kronos_runtime_config(auto_config)
    payload = get_cache().get(_SHARED_BATCH_KEY)
    if not isinstance(payload, dict):
        return {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    created_at = summary.get("kronos_batch_cache_created_at") or payload.get("kronos_batch_cache_created_at")
    expires_at = summary.get("kronos_batch_cache_expires_at") or payload.get("kronos_batch_cache_expires_at")
    age_seconds = _age_seconds(created_at)
    stale = False
    expires_dt = _parse_iso_timestamp(expires_at)
    if expires_dt is not None:
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
        stale = expires_dt.astimezone(timezone.utc) < datetime.now(timezone.utc)
    result = {
        **summary,
        "kronos_batch_cache_ready": bool(summary.get("kronos_batch_cache_ready", summary.get("kronos_batch_ready_count"))),
        "kronos_batch_cache_created_at": created_at,
        "kronos_batch_cache_expires_at": expires_at,
        "kronos_cache_age_seconds": age_seconds,
        "kronos_cache_symbol_count": _safe_int(summary.get("kronos_cache_symbol_count"), _safe_int(summary.get("kronos_batch_symbol_count"), 0)),
        "kronos_cache_source": "shared_batch",
        "kronos_stale": bool(stale),
    }
    if include_symbols:
        result["symbols"] = payload.get("symbols") if isinstance(payload.get("symbols"), dict) else {}
    return result


def _persist_shared_batch_payload(*, symbols: dict[str, dict], summary: dict, config: dict) -> dict:
    ttl_seconds = _shared_batch_ttl_seconds(config)
    created_at = _now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()
    normalized_summary = {
        **summary,
        "kronos_batch_cache_ready": bool(summary.get("kronos_batch_ready_count", 0) > 0),
        "kronos_batch_cache_created_at": created_at,
        "kronos_batch_cache_expires_at": expires_at,
        "kronos_cache_symbol_count": len(symbols or {}),
        "kronos_cache_source": "shared_batch",
        "kronos_stale": False,
    }
    payload = {
        "summary": normalized_summary,
        "symbols": symbols if isinstance(symbols, dict) else {},
        "kronos_batch_cache_created_at": created_at,
        "kronos_batch_cache_expires_at": expires_at,
    }
    get_cache().set(_SHARED_BATCH_KEY, payload, ttl_seconds=ttl_seconds)
    return payload


def get_kronos_runtime_config(auto_config: dict | None = None) -> dict:
    config = auto_config if isinstance(auto_config, dict) else get_auto_trading_config()
    return {
        "kronos_enabled": bool(config.get("kronos_enabled", False)),
        "kronos_model_name": str(config.get("kronos_model_name") or "NeoQuasar/Kronos-mini"),
        "kronos_tokenizer_name": str(config.get("kronos_tokenizer_name") or "NeoQuasar/Kronos-Tokenizer-2k"),
        "kronos_device_preference": str(config.get("kronos_device_preference") or "auto").strip().lower() or "auto",
        "kronos_timeout_seconds": max(_safe_int(config.get("kronos_timeout_seconds"), 20), 5),
        "kronos_cache_ttl_seconds": max(_safe_int(config.get("kronos_cache_ttl_seconds"), 600), 30),
        "kronos_weight": _clamp(_safe_float(config.get("kronos_weight"), 0.18), 0.0, 1.0),
        "kronos_premarket_weight": _clamp(_safe_float(config.get("kronos_premarket_weight"), 0.26), 0.0, 1.0),
        "kronos_opening_weight": _clamp(_safe_float(config.get("kronos_opening_weight"), 0.24), 0.0, 1.0),
        "kronos_max_symbols_per_batch": max(_safe_int(config.get("kronos_max_symbols_per_batch"), 20), 1),
        "kronos_min_input_quality": _clamp(_safe_float(config.get("kronos_min_input_quality"), 0.55), 0.0, 1.0),
        "kronos_warmup_enabled": _safe_bool(config.get("kronos_warmup_enabled"), True),
        "kronos_batch_preopen_enabled": _safe_bool(config.get("kronos_batch_preopen_enabled"), True),
        "kronos_fallback_to_base_ensemble": _safe_bool(config.get("kronos_fallback_to_base_ensemble"), True),
        "kronos_prediction_horizon": max(_safe_int(config.get("kronos_prediction_horizon"), 12), 2),
        "kronos_lookback_rows": max(_safe_int(config.get("kronos_lookback_rows"), 280), 80),
        "kronos_input_interval": str(config.get("kronos_input_interval") or "5m").strip().lower() or "5m",
    }


def _resolve_device(preference: str) -> str:
    pref = str(preference or "auto").strip().lower() or "auto"
    if pref != "auto":
        return pref
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _prepare_input(symbol: str, *, interval: str, lookback_rows: int, pred_len: int, session_type: str) -> dict:
    history = load_history(symbol, interval=interval, persist=False)
    items = history.get("items") if isinstance(history, dict) else []
    if not isinstance(items, list) or not items:
        return {
            "kronos_input_ready": False,
            "kronos_input_quality": 0.0,
            "kronos_input_warning_flags": ["history_empty"],
            "kronos_no_trade_reason": "kronos_input_unavailable",
            "history_error": (history or {}).get("error") if isinstance(history, dict) else "history_unavailable",
        }

    frame = pd.DataFrame(items)
    if frame.empty or "datetime" not in frame.columns:
        return {
            "kronos_input_ready": False,
            "kronos_input_quality": 0.0,
            "kronos_input_warning_flags": ["history_invalid"],
            "kronos_no_trade_reason": "kronos_input_invalid",
        }

    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame.get(col), errors="coerce")
    frame = frame.dropna(subset=["datetime", "open", "high", "low", "close"]).sort_values("datetime")
    if frame.empty:
        return {
            "kronos_input_ready": False,
            "kronos_input_quality": 0.0,
            "kronos_input_warning_flags": ["history_all_nan"],
            "kronos_no_trade_reason": "kronos_input_nan",
        }

    frame["volume"] = frame["volume"].fillna(0.0)
    frame["amount"] = pd.to_numeric(frame.get("amount"), errors="coerce")
    frame["amount"] = frame["amount"].fillna(frame["volume"] * frame["close"])
    frame = frame.tail(max(lookback_rows, 80)).reset_index(drop=True)

    row_count = len(frame)
    quality = _clamp(row_count / max(float(lookback_rows), 1.0), 0.0, 1.0)
    warning_flags: list[str] = []
    if row_count < min(lookback_rows, 120):
        warning_flags.append("short_context")
    if float(frame["volume"].tail(20).mean() or 0.0) <= 0:
        warning_flags.append("volume_missing")

    freq = _INTERVAL_FREQ.get(interval, "5min")
    x_ts = frame["datetime"].reset_index(drop=True)
    start_y = x_ts.iloc[-1] + pd.to_timedelta(freq)
    y_ts = pd.Series(pd.date_range(start=start_y, periods=pred_len, freq=freq), name="datetime")

    input_df = frame[[* _FEATURE_COLUMNS]].copy()

    return {
        "kronos_input_ready": True,
        "kronos_input_window_start": str(x_ts.iloc[0]),
        "kronos_input_window_end": str(x_ts.iloc[-1]),
        "kronos_input_timeframe": interval,
        "kronos_input_session_type": session_type,
        "kronos_input_row_count": row_count,
        "kronos_input_quality": round(quality, 4),
        "kronos_input_warning_flags": warning_flags,
        "df": input_df,
        "x_timestamp": x_ts,
        "y_timestamp": y_ts,
        "last_close": _safe_float(frame["close"].iloc[-1], 0.0),
        "last_volume": _safe_float(frame["volume"].iloc[-1], 0.0),
    }


def _ensure_runtime_loaded(config: dict) -> bool:
    with _LOCK:
        _RUNTIME.enabled = bool(config.get("kronos_enabled", False))
        _RUNTIME.model_name = str(config.get("kronos_model_name") or "")
        _RUNTIME.tokenizer_name = str(config.get("kronos_tokenizer_name") or "")
        _RUNTIME.device = _resolve_device(config.get("kronos_device_preference"))

        if not _RUNTIME.enabled:
            _RUNTIME.error = "kronos_disabled"
            _RUNTIME.last_error_at = _now_iso()
            _RUNTIME.loaded = False
            _RUNTIME.warmed = False
            _RUNTIME.predictor = None
            _RUNTIME.degraded_mode = False
            _RUNTIME.degraded_reason = "disabled"
            _persist_shared_runtime_status(config)
            return False

        if _RUNTIME.loaded and _RUNTIME.predictor is not None:
            _persist_shared_runtime_status(config)
            return True

        started = time.perf_counter()
        try:
            from backend.app.vendors.kronos_model import Kronos, KronosPredictor, KronosTokenizer

            tokenizer = KronosTokenizer.from_pretrained(_RUNTIME.tokenizer_name)
            model = Kronos.from_pretrained(_RUNTIME.model_name)
            predictor = KronosPredictor(
                model,
                tokenizer,
                device=_RUNTIME.device,
                max_context=512,
            )
            _RUNTIME.predictor = predictor
            _RUNTIME.loaded = True
            _RUNTIME.error = None
            _RUNTIME.degraded_mode = False
            _RUNTIME.degraded_reason = None
            _RUNTIME.load_latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
            _persist_shared_runtime_status(config)
            log_event(
                logger,
                logging.INFO,
                "kronos.model.loaded",
                model=_RUNTIME.model_name,
                tokenizer=_RUNTIME.tokenizer_name,
                device=_RUNTIME.device,
                latency_ms=_RUNTIME.load_latency_ms,
            )
            return True
        except Exception as exc:
            _RUNTIME.loaded = False
            _RUNTIME.warmed = False
            _RUNTIME.predictor = None
            _RUNTIME.error = str(exc)
            _RUNTIME.last_error_at = _now_iso()
            _RUNTIME.degraded_mode = True
            _RUNTIME.degraded_reason = "model_load_failed"
            _RUNTIME.load_latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
            _persist_shared_runtime_status(config)
            log_event(
                logger,
                logging.WARNING,
                "kronos.model.load_failed",
                model=_RUNTIME.model_name,
                tokenizer=_RUNTIME.tokenizer_name,
                device=_RUNTIME.device,
                error=str(exc),
            )
            return False


def warm_kronos(*, sample_symbol: str = "SPY", auto_config: dict | None = None, session_type: str = "pre_open_preparation") -> dict:
    config = get_kronos_runtime_config(auto_config)
    if not _ensure_runtime_loaded(config):
        return kronos_status(auto_config=auto_config)

    if not config.get("kronos_warmup_enabled", True):
        status = kronos_status(auto_config=auto_config)
        status["kronos_warmup_skipped"] = True
        return status

    started = time.perf_counter()
    prep = _prepare_input(
        sample_symbol,
        interval=config["kronos_input_interval"],
        lookback_rows=min(config["kronos_lookback_rows"], 220),
        pred_len=min(config["kronos_prediction_horizon"], 8),
        session_type=session_type,
    )
    if not prep.get("kronos_input_ready"):
        status = kronos_status(auto_config=auto_config)
        status.update(
            {
                "kronos_warmup_skipped": True,
                "kronos_warmup_reason": "input_not_ready",
                "kronos_input_warning_flags": prep.get("kronos_input_warning_flags", []),
            }
        )
        _persist_shared_runtime_status(config, {"kronos_degraded_mode": True, "kronos_degraded_reason": "warmup_input_not_ready"})
        return status

    try:
        predictor = _RUNTIME.predictor
        predictor.predict(
            df=prep["df"],
            x_timestamp=prep["x_timestamp"],
            y_timestamp=prep["y_timestamp"],
            pred_len=min(config["kronos_prediction_horizon"], 8),
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )
        _RUNTIME.warmed = True
        _RUNTIME.last_warmup_at = _now_iso()
        _RUNTIME.warmup_latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        _RUNTIME.degraded_mode = False
        _RUNTIME.degraded_reason = None
        _persist_shared_runtime_status(config)
        return kronos_status(auto_config=auto_config)
    except Exception as exc:
        _RUNTIME.warmed = False
        _RUNTIME.error = str(exc)
        _RUNTIME.last_error_at = _now_iso()
        _RUNTIME.warmup_latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        _RUNTIME.degraded_mode = True
        _RUNTIME.degraded_reason = "warmup_failed"
        _persist_shared_runtime_status(config)
        status = kronos_status(auto_config=auto_config)
        status["kronos_warmup_error"] = str(exc)
        return status


def kronos_status(*, auto_config: dict | None = None) -> dict:
    config = get_kronos_runtime_config(auto_config)
    local_payload = _local_runtime_status_payload(config)
    shared_payload = _load_shared_runtime_status()
    batch_cache = get_kronos_batch_cache_snapshot(auto_config=auto_config, include_symbols=False)

    effective = dict(local_payload)
    if shared_payload:
        effective.update(shared_payload)
        effective["kronos_status_source"] = shared_payload.get("kronos_status_source") or "shared"
    else:
        effective["kronos_status_source"] = "process_local"

    effective["runtime_local"] = local_payload
    effective["shared_status"] = shared_payload
    effective["kronos_batch_cache"] = batch_cache
    if isinstance(batch_cache, dict) and batch_cache:
        effective.setdefault("kronos_batch_cache_ready", batch_cache.get("kronos_batch_cache_ready"))
        effective.setdefault("kronos_batch_cache_created_at", batch_cache.get("kronos_batch_cache_created_at"))
        effective.setdefault("kronos_batch_cache_expires_at", batch_cache.get("kronos_batch_cache_expires_at"))
        effective.setdefault("kronos_cache_age_seconds", batch_cache.get("kronos_cache_age_seconds"))
        effective.setdefault("kronos_cache_symbol_count", batch_cache.get("kronos_cache_symbol_count"))
        effective.setdefault("kronos_stale", batch_cache.get("kronos_stale"))

    return effective


def _cache_get(cache_key: str, ttl_seconds: int) -> dict | None:
    shared_payload = get_cache().get(_shared_symbol_cache_storage_key(cache_key))
    if isinstance(shared_payload, dict):
        ts = _safe_float(shared_payload.get("_cached_at_epoch"), 0.0)
        if ts > 0:
            age = time.time() - ts
            if age <= ttl_seconds:
                result = dict(shared_payload.get("payload") or {})
                result["kronos_cache_hit"] = True
                result["kronos_cache_source"] = "shared"
                result["kronos_cache_age_seconds"] = round(max(age, 0.0), 3)
                return result

    payload = _RUNTIME.cache.get(cache_key)
    if not isinstance(payload, dict):
        return None
    ts = _safe_float(payload.get("_cached_at_epoch"), 0.0)
    if ts <= 0:
        return None
    age = time.time() - ts
    if age > ttl_seconds:
        return None
    result = dict(payload.get("payload") or {})
    result["kronos_cache_hit"] = True
    result["kronos_cache_source"] = "local"
    result["kronos_cache_age_seconds"] = round(max(age, 0.0), 3)
    return result


def _cache_set(cache_key: str, payload: dict, *, ttl_seconds: int) -> None:
    local_payload = {
        "_cached_at_epoch": time.time(),
        "payload": dict(payload),
    }
    _RUNTIME.cache[cache_key] = local_payload
    get_cache().set(
        _shared_symbol_cache_storage_key(cache_key),
        local_payload,
        ttl_seconds=ttl_seconds,
    )


def run_kronos_inference_for_symbol(
    symbol: str,
    *,
    session_snapshot: dict | None = None,
    auto_config: dict | None = None,
) -> dict:
    normalized_symbol = str(symbol or "").strip().upper()
    config = get_kronos_runtime_config(auto_config)

    base = {
        "symbol": normalized_symbol,
        "kronos_enabled": bool(config.get("kronos_enabled", False)),
        "kronos_ready": False,
        "kronos_loaded": bool(_RUNTIME.loaded),
        "kronos_warmed": bool(_RUNTIME.warmed),
        "kronos_score": 0.0,
        "kronos_confidence": 0.0,
        "kronos_direction_bias": "neutral",
        "kronos_signal_strength": 0.0,
        "kronos_signal_tier": "low",
        "kronos_session_adjusted_score": 0.0,
        "kronos_forecast_horizon": int(config.get("kronos_prediction_horizon", 12)),
        "kronos_forecast_return": 0.0,
        "kronos_forecast_range": 0.0,
        "kronos_expected_volatility": 0.0,
        "kronos_volatility_risk": "unknown",
        "kronos_volatility_regime": "unknown",
        "kronos_upside_path_score": 0.0,
        "kronos_downside_path_score": 0.0,
        "kronos_regime_alignment": "neutral",
        "kronos_premarket_score": 0.0,
        "kronos_opening_score": 0.0,
        "kronos_gap_follow_score": 0.0,
        "kronos_gap_fade_risk": 0.0,
        "kronos_opening_breakout_score": 0.0,
        "kronos_opening_chase_risk": 0.0,
        "kronos_premarket_liquidity_alignment": "unknown",
        "kronos_session_preferred_action": "NO_ACTION",
        "kronos_session_preferred_timing": "wait",
        "kronos_execution_timing_bias": "wait",
        "kronos_order_style_modifier": "no_submit",
        "kronos_size_multiplier": 1.0,
        "kronos_add_size_multiplier": 1.0,
        "kronos_opening_risk_multiplier": 1.0,
        "kronos_premarket_risk_multiplier": 1.0,
        "kronos_exposure_warning": None,
        "kronos_reduce_pressure": 0.0,
        "kronos_no_trade_reason": None,
        "kronos_warning_flags": [],
        "kronos_inference_latency_ms": 0.0,
        "kronos_timeout_hit": False,
        "kronos_cache_hit": False,
        "kronos_cache_source": None,
        "kronos_cache_age_seconds": None,
        "kronos_stale": False,
        "kronos_fallback_used": False,
        "kronos_degraded_mode": bool(_RUNTIME.degraded_mode),
        "kronos_degraded_reason": _RUNTIME.degraded_reason,
    }

    if not normalized_symbol:
        return {**base, "kronos_no_trade_reason": "symbol_missing", "kronos_warning_flags": ["symbol_missing"], "kronos_fallback_used": True}

    if not config.get("kronos_enabled", False):
        return {**base, "kronos_no_trade_reason": "kronos_disabled", "kronos_fallback_used": True}

    session_state = normalize_session_state((session_snapshot or {}).get("session_state") or "regular_session")
    cache_key = f"{normalized_symbol}:{session_state}:{config['kronos_input_interval']}:{config['kronos_prediction_horizon']}"
    cached = _cache_get(cache_key, int(config.get("kronos_cache_ttl_seconds", 600)))
    if cached is not None:
        return {**base, **cached, "kronos_loaded": bool(cached.get("kronos_loaded", _RUNTIME.loaded))}

    if not _ensure_runtime_loaded(config):
        return {
            **base,
            "kronos_loaded": False,
            "kronos_ready": False,
            "kronos_no_trade_reason": "kronos_load_failed",
            "kronos_warning_flags": ["kronos_load_failed"],
            "kronos_error": _RUNTIME.error,
            "kronos_fallback_used": True,
            "kronos_degraded_mode": True,
            "kronos_degraded_reason": _RUNTIME.degraded_reason or "kronos_load_failed",
        }

    started = time.perf_counter()
    prep = _prepare_input(
        normalized_symbol,
        interval=config["kronos_input_interval"],
        lookback_rows=config["kronos_lookback_rows"],
        pred_len=config["kronos_prediction_horizon"],
        session_type=session_state,
    )
    if not prep.get("kronos_input_ready"):
        return {
            **base,
            **{k: prep.get(k) for k in prep.keys() if str(k).startswith("kronos_input_")},
            "kronos_no_trade_reason": prep.get("kronos_no_trade_reason") or "kronos_input_not_ready",
            "kronos_warning_flags": prep.get("kronos_input_warning_flags", []),
            "kronos_fallback_used": True,
        }

    if _safe_float(prep.get("kronos_input_quality"), 0.0) < _safe_float(config.get("kronos_min_input_quality"), 0.55):
        return {
            **base,
            **{k: prep.get(k) for k in prep.keys() if str(k).startswith("kronos_input_")},
            "kronos_no_trade_reason": "kronos_input_quality_low",
            "kronos_warning_flags": [*list(prep.get("kronos_input_warning_flags", [])), "kronos_input_quality_low"],
            "kronos_fallback_used": True,
        }

    predictor = _RUNTIME.predictor
    try:
        pred_df = predictor.predict(
            df=prep["df"],
            x_timestamp=prep["x_timestamp"],
            y_timestamp=prep["y_timestamp"],
            pred_len=config["kronos_prediction_horizon"],
            T=1.0,
            top_p=0.9,
            sample_count=1,
            verbose=False,
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        _RUNTIME.error = str(exc)
        _RUNTIME.last_error_at = _now_iso()
        _RUNTIME.degraded_mode = True
        _RUNTIME.degraded_reason = "inference_failed"
        _persist_shared_runtime_status(config)
        return {
            **base,
            **{k: prep.get(k) for k in prep.keys() if str(k).startswith("kronos_input_")},
            "kronos_loaded": bool(_RUNTIME.loaded),
            "kronos_ready": False,
            "kronos_no_trade_reason": "kronos_inference_failed",
            "kronos_warning_flags": [*list(prep.get("kronos_input_warning_flags", [])), "kronos_inference_failed"],
            "kronos_error": str(exc),
            "kronos_inference_latency_ms": latency_ms,
            "kronos_fallback_used": True,
            "kronos_degraded_mode": True,
            "kronos_degraded_reason": "inference_failed",
        }

    latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    timeout_seconds = _safe_float(config.get("kronos_timeout_seconds"), 20.0)
    timeout_hit = latency_ms > (timeout_seconds * 1000.0)

    closes = pd.to_numeric(pred_df.get("close"), errors="coerce")
    closes = closes.dropna()
    if closes.empty:
        _RUNTIME.degraded_mode = True
        _RUNTIME.degraded_reason = "empty_forecast"
        _persist_shared_runtime_status(config)
        return {
            **base,
            **{k: prep.get(k) for k in prep.keys() if str(k).startswith("kronos_input_")},
            "kronos_loaded": bool(_RUNTIME.loaded),
            "kronos_ready": False,
            "kronos_no_trade_reason": "kronos_empty_forecast",
            "kronos_warning_flags": ["kronos_empty_forecast"],
            "kronos_inference_latency_ms": latency_ms,
            "kronos_timeout_hit": timeout_hit,
            "kronos_fallback_used": True,
            "kronos_degraded_mode": True,
            "kronos_degraded_reason": "empty_forecast",
        }

    last_close = max(_safe_float(prep.get("last_close"), 0.0), 1e-9)
    forecast_close = _safe_float(closes.iloc[-1], last_close)
    forecast_return = ((forecast_close / last_close) - 1.0) * 100.0
    forecast_range = ((float(closes.max()) - float(closes.min())) / last_close) * 100.0
    forecast_vol = _safe_float(closes.pct_change().dropna().std(), 0.0) * 100.0

    direction_bias = "bullish" if forecast_return > 0.20 else "bearish" if forecast_return < -0.20 else "neutral"
    base_score = _clamp(50.0 + forecast_return * 4.2 - forecast_vol * 1.8, 0.0, 100.0)
    confidence = _clamp(42.0 + abs(forecast_return) * 7.5 + max(0.0, 5.0 - forecast_vol), 0.0, 100.0)

    premarket_score = _clamp(base_score - forecast_vol * 0.8, 0.0, 100.0)
    opening_score = _clamp(base_score + (_safe_float(forecast_return) * 0.6), 0.0, 100.0)
    breakout_score = _clamp(base_score + max(forecast_return, 0.0) * 2.4, 0.0, 100.0)
    chase_risk = _clamp(35.0 + max(forecast_return - 1.2, 0.0) * 8.0 + forecast_vol * 3.0, 0.0, 100.0)
    fade_risk = _clamp(40.0 + max(-forecast_return, 0.0) * 8.0 + forecast_vol * 2.2, 0.0, 100.0)

    session_adjusted = base_score
    if session_state == "premarket_live":
        session_adjusted = _clamp(premarket_score, 0.0, 100.0)
    elif session_state == "opening_handoff_window":
        session_adjusted = _clamp(opening_score, 0.0, 100.0)

    preferred_action = "NO_ACTION"
    preferred_timing = "wait"
    timing_bias = "wait"
    order_style = "no_submit"
    no_trade_reason = None

    if session_adjusted >= 72 and chase_risk < 72 and fade_risk < 72:
        if session_state in {"premarket_live", "after_hours"}:
            preferred_action = "PREMARKET_OPEN_LONG"
            preferred_timing = "submit_before_open"
            timing_bias = "submit_now"
            order_style = "extended_hours_limit"
        elif session_state in {"preopen_preparation", "opening_handoff_window", "fully_closed", "overnight_if_supported"}:
            preferred_action = "QUEUE_FOR_OPEN_LONG"
            preferred_timing = "queue_for_open"
            timing_bias = "queue_for_open"
            order_style = "on_open_limit"
        else:
            preferred_action = "REGULAR_SESSION_OPEN_LONG"
            preferred_timing = "submit_now"
            timing_bias = "submit_now"
            order_style = "regular_marketable_limit"
    elif session_adjusted >= 58:
        preferred_action = "WAIT_FOR_OPEN_CONFIRMATION"
        preferred_timing = "wait_for_open_confirmation"
        timing_bias = "wait"
        order_style = "no_submit"
        no_trade_reason = "kronos_prefers_wait_for_open_confirmation"
    elif direction_bias == "bearish" and abs(forecast_return) > 0.5:
        preferred_action = "REDUCE"
        preferred_timing = "risk_reduce"
        timing_bias = "risk_reduce"
        order_style = "regular_limit"
        no_trade_reason = "kronos_reduce_pressure"
    else:
        preferred_action = "NO_ACTION"
        preferred_timing = "wait"
        timing_bias = "wait"
        order_style = "no_submit"
        no_trade_reason = "kronos_low_quality_premarket_structure"

    signal_strength = _clamp((session_adjusted + confidence) / 2.0, 0.0, 100.0)
    if signal_strength >= 78:
        tier = "elite"
    elif signal_strength >= 64:
        tier = "high"
    elif signal_strength >= 50:
        tier = "medium"
    else:
        tier = "low"

    expected_volatility = round(forecast_vol, 4)
    if expected_volatility >= 2.4:
        volatility_regime = "elevated"
        volatility_risk = "high"
    elif expected_volatility >= 1.2:
        volatility_regime = "normal"
        volatility_risk = "medium"
    else:
        volatility_regime = "quiet"
        volatility_risk = "low"

    size_multiplier = _clamp(1.0 - (forecast_vol / 6.0), 0.35, 1.25)
    add_size_multiplier = _clamp(size_multiplier * (1.0 if forecast_return >= 0 else 0.75), 0.25, 1.2)
    opening_risk_multiplier = _clamp(1.0 + (chase_risk / 150.0), 0.8, 1.7)
    premarket_risk_multiplier = _clamp(1.0 + (fade_risk / 160.0), 0.8, 1.8)

    warning_flags = list(prep.get("kronos_input_warning_flags", []))
    if timeout_hit:
        warning_flags.append("kronos_timeout_hit")
    if chase_risk >= 75:
        warning_flags.append("kronos_detects_opening_chase_risk")
    if fade_risk >= 75:
        warning_flags.append("kronos_detects_gap_fade_risk")

    if timeout_hit:
        _RUNTIME.last_timeout_at = _now_iso()
        _RUNTIME.timeout_count += 1
        _RUNTIME.degraded_mode = True
        _RUNTIME.degraded_reason = "inference_timeout"
    else:
        _RUNTIME.degraded_mode = False
        _RUNTIME.degraded_reason = None

    output = {
        **base,
        **{k: prep.get(k) for k in prep.keys() if str(k).startswith("kronos_input_")},
        "kronos_loaded": bool(_RUNTIME.loaded),
        "kronos_warmed": bool(_RUNTIME.warmed),
        "kronos_ready": True,
        "kronos_score": round(base_score, 4),
        "kronos_confidence": round(confidence, 4),
        "kronos_direction_bias": direction_bias,
        "kronos_signal_strength": round(signal_strength, 4),
        "kronos_signal_tier": tier,
        "kronos_session_adjusted_score": round(session_adjusted, 4),
        "kronos_forecast_horizon": int(config["kronos_prediction_horizon"]),
        "kronos_forecast_return": round(forecast_return, 4),
        "kronos_forecast_range": round(forecast_range, 4),
        "kronos_expected_volatility": expected_volatility,
        "kronos_volatility_risk": volatility_risk,
        "kronos_volatility_regime": volatility_regime,
        "kronos_upside_path_score": round(_clamp(50 + max(forecast_return, 0.0) * 6.0, 0.0, 100.0), 4),
        "kronos_downside_path_score": round(_clamp(50 + max(-forecast_return, 0.0) * 6.0, 0.0, 100.0), 4),
        "kronos_regime_alignment": "bullish" if direction_bias == "bullish" else "defensive" if direction_bias == "bearish" else "neutral",
        "kronos_premarket_score": round(premarket_score, 4),
        "kronos_opening_score": round(opening_score, 4),
        "kronos_gap_follow_score": round(_clamp(50 + forecast_return * 6.0, 0.0, 100.0), 4),
        "kronos_gap_fade_risk": round(fade_risk, 4),
        "kronos_opening_breakout_score": round(breakout_score, 4),
        "kronos_opening_chase_risk": round(chase_risk, 4),
        "kronos_premarket_liquidity_alignment": "aligned" if forecast_vol <= 1.8 else "weak",
        "kronos_session_preferred_action": preferred_action,
        "kronos_session_preferred_timing": preferred_timing,
        "kronos_execution_timing_bias": timing_bias,
        "kronos_order_style_modifier": order_style,
        "kronos_size_multiplier": round(size_multiplier, 4),
        "kronos_add_size_multiplier": round(add_size_multiplier, 4),
        "kronos_opening_risk_multiplier": round(opening_risk_multiplier, 4),
        "kronos_premarket_risk_multiplier": round(premarket_risk_multiplier, 4),
        "kronos_exposure_warning": "elevated_volatility" if volatility_risk == "high" else None,
        "kronos_reduce_pressure": round(_clamp(max(-forecast_return, 0.0) * 10.0, 0.0, 100.0), 4),
        "kronos_no_trade_reason": no_trade_reason,
        "kronos_warning_flags": warning_flags,
        "kronos_inference_latency_ms": latency_ms,
        "kronos_timeout_hit": bool(timeout_hit),
        "kronos_cache_hit": False,
        "kronos_cache_source": "fresh_inference",
        "kronos_cache_age_seconds": 0.0,
        "kronos_stale": False,
        "kronos_fallback_used": False,
        "kronos_last_inference_at": _now_iso(),
        "kronos_degraded_mode": bool(_RUNTIME.degraded_mode),
        "kronos_degraded_reason": _RUNTIME.degraded_reason,
    }

    _RUNTIME.last_inference_at = output["kronos_last_inference_at"]
    _cache_set(cache_key, output, ttl_seconds=_shared_symbol_ttl_seconds(config))
    _persist_shared_runtime_status(config)
    return output


def run_kronos_batch(
    symbols: list[str],
    *,
    session_snapshot: dict | None = None,
    auto_config: dict | None = None,
) -> dict:
    config = get_kronos_runtime_config(auto_config)
    started = time.perf_counter()
    normalized = []
    for symbol in symbols or []:
        item = str(symbol or "").strip().upper()
        if item and item not in normalized:
            normalized.append(item)
    normalized = normalized[: max(_safe_int(config.get("kronos_max_symbols_per_batch"), 20), 1)]

    results: dict[str, dict] = {}
    for symbol in normalized:
        results[symbol] = run_kronos_inference_for_symbol(
            symbol,
            session_snapshot=session_snapshot,
            auto_config=auto_config,
        )

    duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
    ready_count = sum(1 for payload in results.values() if bool(payload.get("kronos_ready")))
    cache_hits = sum(1 for payload in results.values() if bool(payload.get("kronos_cache_hit")))
    timeout_count = sum(1 for payload in results.values() if bool(payload.get("kronos_timeout_hit")))
    fallback_count = sum(1 for payload in results.values() if bool(payload.get("kronos_fallback_used")))

    _RUNTIME.last_batch_inference_at = _now_iso()
    _RUNTIME.last_batch_duration_ms = duration_ms
    _RUNTIME.last_batch_symbol_count = len(normalized)
    if timeout_count:
        _RUNTIME.degraded_mode = True
        _RUNTIME.degraded_reason = "batch_timeout"

    summary = {
        "kronos_enabled": bool(config.get("kronos_enabled", False)),
        "kronos_loaded": bool(_RUNTIME.loaded),
        "kronos_warmed": bool(_RUNTIME.warmed),
        "kronos_batch_symbol_count": len(normalized),
        "kronos_batch_ready_count": ready_count,
        "kronos_batch_cache_hits": cache_hits,
        "kronos_batch_duration_ms": duration_ms,
        "kronos_timeout_count": timeout_count,
        "kronos_timeout_hit": bool(timeout_count > 0),
        "kronos_fallback_count": fallback_count,
        "kronos_fallback_used": bool(fallback_count > 0),
        "kronos_readiness_status": "ready" if ready_count > 0 else "degraded",
        "kronos_readiness_warnings": [
            item
            for item in [
                "kronos_disabled" if not config.get("kronos_enabled", False) else None,
                "kronos_not_loaded" if config.get("kronos_enabled", False) and not _RUNTIME.loaded else None,
                "kronos_timeout_hit" if timeout_count else None,
            ]
            if item
        ],
        "kronos_last_batch_inference_at": _RUNTIME.last_batch_inference_at,
        "kronos_degraded_mode": bool(_RUNTIME.degraded_mode),
        "kronos_degraded_reason": _RUNTIME.degraded_reason,
    }

    _persist_shared_batch_payload(symbols=results, summary=summary, config=config)
    _persist_shared_runtime_status(
        config,
        {
            "kronos_last_batch_inference_at": _RUNTIME.last_batch_inference_at,
            "kronos_last_batch_duration_ms": duration_ms,
            "kronos_last_batch_symbol_count": len(normalized),
            "kronos_timeout_count": int(_RUNTIME.timeout_count),
            "kronos_last_timeout_at": _RUNTIME.last_timeout_at,
            "kronos_degraded_mode": bool(_RUNTIME.degraded_mode),
            "kronos_degraded_reason": _RUNTIME.degraded_reason,
        },
    )

    batch_snapshot = get_kronos_batch_cache_snapshot(auto_config=auto_config, include_symbols=False)
    summary.update({
        "kronos_batch_cache_ready": batch_snapshot.get("kronos_batch_cache_ready"),
        "kronos_batch_cache_created_at": batch_snapshot.get("kronos_batch_cache_created_at"),
        "kronos_batch_cache_expires_at": batch_snapshot.get("kronos_batch_cache_expires_at"),
        "kronos_cache_age_seconds": batch_snapshot.get("kronos_cache_age_seconds"),
        "kronos_cache_symbol_count": batch_snapshot.get("kronos_cache_symbol_count"),
        "kronos_cache_source": batch_snapshot.get("kronos_cache_source"),
        "kronos_stale": batch_snapshot.get("kronos_stale"),
    })

    return {
        "symbols": results,
        "summary": summary,
    }
