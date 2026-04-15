import logging
import time
from threading import Lock

from fastapi import APIRouter
from sqlalchemy import text

from backend.app.config import (
    API_TITLE,
    API_VERSION,
    APP_ENV,
    DATABASE_AUTO_MIGRATE,
    DATABASE_IS_POSTGRESQL,
    DATABASE_IS_SQLITE,
    ENABLE_SCHEDULER,
    SCHEDULER_RUNNER_ROLE,
    SCHEDULER_STARTUP_ENABLED,
    SERVER_ROLE,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.db.session import engine
from backend.app.services.runtime_control import get_runtime_control_plane
from core.runtime_paths import sqlite_file_path

router = APIRouter(tags=["health"])
logger = get_logger(__name__)
_HEALTH_CACHE_TTL_SECONDS = 10.0
_STACK_CACHE_TTL_SECONDS = 30.0
_cache_lock = Lock()
_cached_stack_payload: dict | None = None
_cached_stack_expires_at = 0.0
_cached_health_context: dict | None = None
_cached_health_context_expires_at = 0.0


def _build_stack_summary() -> dict:
    """Quick non-blocking stack summary for health output."""
    try:
        from backend.app.services.stack_validator import validate_stack
        report = validate_stack()
        # Compact: subsystem -> status
        compact = {sub["subsystem"]: sub.get("status", "unknown") for sub in report["subsystems"]}
        compact["_summary"] = report["summary"]
        return compact
    except Exception:
        return {"error": "stack validation unavailable"}


def _stack_summary() -> dict:
    global _cached_stack_payload, _cached_stack_expires_at
    now = time.monotonic()
    with _cache_lock:
        if _cached_stack_payload is not None and now < _cached_stack_expires_at:
            return dict(_cached_stack_payload)
    payload = _build_stack_summary()
    with _cache_lock:
        _cached_stack_payload = dict(payload)
        _cached_stack_expires_at = now + _STACK_CACHE_TTL_SECONDS
    return dict(payload)


def _build_health_context() -> dict:
    control_plane = get_runtime_control_plane()
    return {
        "process": control_plane.get("process"),
        "orchestration": control_plane.get("orchestration"),
        "broker_runtime": control_plane.get("broker_runtime"),
        "cache": control_plane.get("cache"),
        "orchestration_topology": control_plane.get("orchestration_topology"),
        "environment_bootstrap": control_plane.get("environment_bootstrap"),
    }


def _health_context() -> dict:
    global _cached_health_context, _cached_health_context_expires_at
    now = time.monotonic()
    with _cache_lock:
        if _cached_health_context is not None and now < _cached_health_context_expires_at:
            return dict(_cached_health_context)
    payload = _build_health_context()
    with _cache_lock:
        _cached_health_context = dict(payload)
        _cached_health_context_expires_at = now + _HEALTH_CACHE_TTL_SECONDS
    return dict(payload)


@router.get("/health")
def health_check():
    health_context = _health_context()
    return {
        "status": "ok",
        "service": API_TITLE,
        "version": API_VERSION,
        "environment": APP_ENV,
        "database_backend": "postgresql" if DATABASE_IS_POSTGRESQL else "sqlite",
        "scheduler_enabled": ENABLE_SCHEDULER,
        "scheduler_runner_role": SCHEDULER_RUNNER_ROLE,
        "server_role": SERVER_ROLE,
        "live_stack": _stack_summary(),
        **health_context,
    }


@router.get("/ready")
def readiness_check():
    control_plane = get_runtime_control_plane()
    database = {"status": "unknown"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database["status"] = "ok"
        database["path"] = None if sqlite_file_path(str(engine.url)) is None else str(sqlite_file_path(str(engine.url)))
    except Exception as exc:
        database = {"status": "error", "detail": str(exc)}

    overall = "ready" if database["status"] == "ok" else "degraded"
    if overall != "ready":
        log_event(logger, logging.WARNING, "health.readiness", status=overall, database_status=database.get("status"), role=SERVER_ROLE)
    return {
        "status": overall,
        "database": database,
        "database_backend": "postgresql" if DATABASE_IS_POSTGRESQL else "sqlite",
        "live_stack": _stack_summary(),
        "scheduler_enabled": ENABLE_SCHEDULER,
        "scheduler_runner_role": SCHEDULER_RUNNER_ROLE,
        "scheduler_startup_enabled": SCHEDULER_STARTUP_ENABLED,
        "database_auto_migrate": DATABASE_AUTO_MIGRATE,
        "server_role": SERVER_ROLE,
        "process": control_plane.get("process"),
        "orchestration": control_plane.get("orchestration"),
        "broker_runtime": control_plane.get("broker_runtime"),
        "cache": control_plane.get("cache"),
        "orchestration_topology": control_plane.get("orchestration_topology"),
        "environment_bootstrap": control_plane.get("environment_bootstrap"),
        "storage": control_plane.get("storage"),
    }
