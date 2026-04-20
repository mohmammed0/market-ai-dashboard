from __future__ import annotations

from typing import Any, Callable

from backend.app.config import (
    APP_ENV,
    CONTINUOUS_LEARNING_ROLE_ALLOWED,
    CONTINUOUS_LEARNING_RUNNER_ROLE,
    CONTINUOUS_LEARNING_STARTUP_ENABLED,
    DATABASE_IS_POSTGRESQL,
    DATABASE_IS_SQLITE,
    SCHEDULER_ROLE_ALLOWED,
    SCHEDULER_RUNNER_ROLE,
    SCHEDULER_STARTUP_ENABLED,
    SERVER_ROLE,
)
from backend.app.services.cache import get_cache_status
from backend.app.services.continuous_learning import get_continuous_learning_runtime_snapshot
from backend.app.services.open_telemetry import get_open_telemetry_status
from backend.app.services.runtime_settings import get_runtime_settings_overview
from backend.app.services.scheduler_runtime import get_scheduler_status
from core.runtime_env import ENV_BOOTSTRAP_INFO
from core.runtime_paths import (
    BACKUPS_DIR,
    CONTINUOUS_LEARNING_ARTIFACTS_DIR,
    CONTINUOUS_LEARNING_LOGS_DIR,
    DATA_DIR,
    DEFAULT_RUNTIME_CACHE_DIR,
    LOGS_DIR,
    MODEL_ARTIFACTS_DIR,
    ROOT_DIR,
    SETTINGS_KEY_PATH,
    SOURCE_CACHE_DIR,
    TRAINING_LOGS_DIR,
)


def _safe(factory: Callable[[], Any], fallback: Any) -> Any:
    try:
        return factory()
    except Exception as exc:
        if isinstance(fallback, dict):
            payload = dict(fallback)
            payload["error"] = " ".join(str(exc).split()) or exc.__class__.__name__
            return payload
        return fallback


def _process_mode() -> str:
    return "mixed" if (SCHEDULER_ROLE_ALLOWED or CONTINUOUS_LEARNING_ROLE_ALLOWED) else "api-only"


def get_runtime_paths() -> dict[str, str]:
    return {
        "root_dir": str(ROOT_DIR),
        "data_dir": str(DATA_DIR),
        "runtime_cache_dir": str(DEFAULT_RUNTIME_CACHE_DIR),
        "source_cache_dir": str(SOURCE_CACHE_DIR),
        "model_artifacts_dir": str(MODEL_ARTIFACTS_DIR),
        "continuous_learning_artifacts_dir": str(CONTINUOUS_LEARNING_ARTIFACTS_DIR),
        "logs_dir": str(LOGS_DIR),
        "training_logs_dir": str(TRAINING_LOGS_DIR),
        "continuous_learning_logs_dir": str(CONTINUOUS_LEARNING_LOGS_DIR),
        "backups_dir": str(BACKUPS_DIR),
        "settings_key_path": str(SETTINGS_KEY_PATH),
    }


def get_runtime_control_plane() -> dict[str, Any]:
    settings = _safe(
        get_runtime_settings_overview,
        {
            "broker": {
                "provider": "none",
                "provider_source": "unknown",
                "order_submission_enabled": False,
                "order_submission_source": "unknown",
                "live_execution_enabled": False,
                "live_execution_source": "unknown",
                "alpaca": {
                    "enabled": False,
                    "paper": True,
                    "configured": False,
                },
            },
            "database": {},
        },
    )
    broker = settings.get("broker") if isinstance(settings, dict) else {}
    alpaca = broker.get("alpaca") if isinstance(broker, dict) else {}
    provider = str((broker or {}).get("provider") or "none").lower()
    effective_broker_mode = "disabled"
    if provider == "alpaca":
        effective_broker_mode = "paper" if bool((alpaca or {}).get("paper", True)) else "live"

    return {
        "environment": APP_ENV,
        "environment_bootstrap": ENV_BOOTSTRAP_INFO,
        "process": {
            "server_role": SERVER_ROLE,
            "process_mode": _process_mode(),
            "serves_api": True,
            "scheduler_runner_role": SCHEDULER_RUNNER_ROLE,
            "scheduler_role_allowed": SCHEDULER_ROLE_ALLOWED,
            "scheduler_startup_enabled": SCHEDULER_STARTUP_ENABLED,
            "continuous_learning_runner_role": CONTINUOUS_LEARNING_RUNNER_ROLE,
            "continuous_learning_role_allowed": CONTINUOUS_LEARNING_ROLE_ALLOWED,
            "continuous_learning_startup_enabled": CONTINUOUS_LEARNING_STARTUP_ENABLED,
        },
        "orchestration": {
            "scheduler": _safe(
                get_scheduler_status,
                {
                    "runtime_state": "unknown",
                    "scheduler_enabled": False,
                    "scheduler_running": False,
                    "blocked": True,
                    "blocked_reason": "Scheduler status is unavailable.",
                },
            ),
            "continuous_learning": _safe(
                get_continuous_learning_runtime_snapshot,
                {
                    "runtime_state": "unknown",
                    "enabled": False,
                    "running": False,
                    "blocked": True,
                    "blocked_reason": "Continuous learning status is unavailable.",
                    "owner": {},
                },
            ),
        },
        "broker_runtime": {
            "provider": provider,
            "provider_source": broker.get("provider_source"),
            "effective_mode": effective_broker_mode,
            "order_submission_enabled": bool(broker.get("order_submission_enabled", False)),
            "order_submission_source": broker.get("order_submission_source"),
            "live_execution_enabled": bool(broker.get("live_execution_enabled", False)),
            "live_execution_source": broker.get("live_execution_source"),
            "alpaca_enabled": bool((alpaca or {}).get("enabled", False)),
            "alpaca_configured": bool((alpaca or {}).get("configured", False)),
            "alpaca_paper": bool((alpaca or {}).get("paper", True)),
        },
        "storage": {
            "database": settings.get("database", {}),
            "database_backend": "postgresql" if DATABASE_IS_POSTGRESQL else "sqlite" if DATABASE_IS_SQLITE else "unknown",
            "paths": get_runtime_paths(),
        },
        "cache": get_cache_status(),
        "observability": {
            "otel": _safe(
                get_open_telemetry_status,
                {
                    "enabled": False,
                    "active": False,
                    "runtime": "unavailable",
                    "detail": "OpenTelemetry status is unavailable.",
                },
            ),
        },
        "orchestration_topology": _safe(
            lambda: __import__(
                "backend.app.services.orchestration_gateway",
                fromlist=["get_orchestration_status"],
            ).get_orchestration_status(),
            {"status": "unavailable"},
        ),
    }
