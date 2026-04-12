"""Stack Validator — Runtime validation of live infrastructure components.

Performs non-destructive connectivity checks against each external service
at startup (or on-demand) and produces a structured report showing which
subsystems are genuinely live vs fallback.

Each probe is defensive: failure = fallback, never crash.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.app.core.logging_utils import get_logger, log_event

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------

def probe_database() -> dict[str, Any]:
    """Verify database connectivity and report backend type."""
    from backend.app.config import DATABASE_IS_POSTGRESQL, DATABASE_IS_SQLITE, DATABASE_URL
    from backend.app.db.session import engine
    from sqlalchemy import text

    result: dict[str, Any] = {
        "subsystem": "database",
        "configured_backend": "postgresql" if DATABASE_IS_POSTGRESQL else "sqlite",
        "url_masked": _mask_db_url(DATABASE_URL),
    }

    try:
        started = time.perf_counter()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT 1")).fetchone()
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
        result["status"] = "active"
        result["latency_ms"] = latency_ms
        result["verified"] = True

        # PostgreSQL-specific version check
        if DATABASE_IS_POSTGRESQL:
            try:
                with engine.connect() as conn:
                    ver = conn.execute(text("SELECT version()")).scalar()
                    result["server_version"] = str(ver).split(",")[0] if ver else None
            except Exception:
                pass
    except Exception as exc:
        result["status"] = "unavailable"
        result["error"] = str(exc)[:200]
        result["verified"] = False

    return result


def probe_redis() -> dict[str, Any]:
    """Verify Redis connectivity and report mode."""
    from backend.app.config import REDIS_ENABLED, REDIS_URL
    from backend.app.services.cache import get_cache, get_cache_status

    result: dict[str, Any] = {
        "subsystem": "redis",
        "configured": bool(REDIS_ENABLED and REDIS_URL),
        "url_masked": _mask_url(REDIS_URL) if REDIS_URL else None,
    }

    if not (REDIS_ENABLED and REDIS_URL):
        result["status"] = "fallback"
        result["mode"] = "in_memory"
        result["reason"] = "REDIS_URL not configured or REDIS_ENABLED=0"
        return result

    # Check if redis package is installed
    try:
        import redis as _redis_check  # noqa: F401
    except ImportError:
        result["status"] = "misconfigured"
        result["mode"] = "in_memory"
        result["reason"] = "redis package not installed (pip install redis)"
        return result

    # Attempt connection
    try:
        import redis
        started = time.perf_counter()
        client = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=3, socket_timeout=3, decode_responses=True)
        pong = client.ping()
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        info = client.info("server")
        client.close()

        result["status"] = "active"
        result["mode"] = "redis"
        result["latency_ms"] = latency_ms
        result["server_version"] = info.get("redis_version")
        result["verified"] = True
    except Exception as exc:
        result["status"] = "unavailable"
        result["mode"] = "in_memory"
        result["error"] = str(exc)[:200]
        result["verified"] = False
        result["reason"] = "Redis configured but not reachable; using in-memory fallback"

    return result


def probe_mlflow() -> dict[str, Any]:
    """Verify MLflow tracking server reachability."""
    from backend.app.config import MLFLOW_TRACKING_URI

    result: dict[str, Any] = {
        "subsystem": "mlflow",
        "configured": bool(MLFLOW_TRACKING_URI),
        "tracking_uri": MLFLOW_TRACKING_URI or None,
    }

    if not MLFLOW_TRACKING_URI:
        result["status"] = "fallback"
        result["mode"] = "local_db"
        result["reason"] = "MLFLOW_TRACKING_URI not configured; using local DB fallback"
        return result

    # Check if mlflow package is installed
    try:
        import mlflow  # noqa: F401
    except ImportError:
        result["status"] = "misconfigured"
        result["mode"] = "local_db"
        result["reason"] = "mlflow package not installed (pip install mlflow)"
        return result

    # Attempt connectivity
    try:
        import mlflow
        import urllib.request
        started = time.perf_counter()
        # Try a lightweight health check on the MLflow server
        tracking_url = MLFLOW_TRACKING_URI.rstrip("/")
        req = urllib.request.Request(f"{tracking_url}/api/2.0/mlflow/experiments/search?max_results=1", method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            status_code = resp.getcode()
        latency_ms = round((time.perf_counter() - started) * 1000, 1)

        if status_code == 200:
            result["status"] = "active"
            result["mode"] = "mlflow"
            result["latency_ms"] = latency_ms
            result["verified"] = True
        else:
            result["status"] = "unavailable"
            result["mode"] = "local_db"
            result["error"] = f"HTTP {status_code}"
            result["verified"] = False
    except Exception as exc:
        result["status"] = "unavailable"
        result["mode"] = "local_db"
        result["error"] = str(exc)[:200]
        result["verified"] = False
        result["reason"] = "MLflow configured but not reachable; using local DB fallback"

    return result


def probe_prefect() -> dict[str, Any]:
    """Verify Prefect API reachability."""
    from backend.app.config import PREFECT_API_URL

    result: dict[str, Any] = {
        "subsystem": "prefect",
        "configured": bool(PREFECT_API_URL),
        "api_url": PREFECT_API_URL or None,
    }

    if not PREFECT_API_URL:
        result["status"] = "fallback"
        result["mode"] = "direct_in_process"
        result["reason"] = "PREFECT_API_URL not configured; heavy workflows run in-process"
        return result

    # Check if prefect package is installed
    try:
        import prefect  # noqa: F401
    except ImportError:
        result["status"] = "misconfigured"
        result["mode"] = "direct_in_process"
        result["reason"] = "prefect package not installed (pip install prefect)"
        return result

    # Attempt connectivity
    try:
        import urllib.request
        started = time.perf_counter()
        api_url = PREFECT_API_URL.rstrip("/")
        req = urllib.request.Request(f"{api_url}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            status_code = resp.getcode()
        latency_ms = round((time.perf_counter() - started) * 1000, 1)

        if status_code == 200:
            result["status"] = "active"
            result["mode"] = "prefect"
            result["latency_ms"] = latency_ms
            result["verified"] = True
        else:
            result["status"] = "unavailable"
            result["mode"] = "direct_in_process"
            result["error"] = f"HTTP {status_code}"
            result["verified"] = False
    except Exception as exc:
        result["status"] = "unavailable"
        result["mode"] = "direct_in_process"
        result["error"] = str(exc)[:200]
        result["verified"] = False
        result["reason"] = "Prefect configured but not reachable; using in-process fallback"

    return result


def probe_celery() -> dict[str, Any]:
    """Verify Celery broker (Redis) reachability."""
    from backend.app.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

    result: dict[str, Any] = {
        "subsystem": "celery",
        "configured": bool(CELERY_BROKER_URL),
        "broker_url_masked": _mask_url(CELERY_BROKER_URL) if CELERY_BROKER_URL else None,
        "result_backend_configured": bool(CELERY_RESULT_BACKEND),
    }

    if not CELERY_BROKER_URL:
        result["status"] = "fallback"
        result["mode"] = "direct_in_process"
        result["reason"] = "CELERY_BROKER_URL not configured; tasks run in-process"
        return result

    # Check if celery package is installed
    try:
        import celery as _celery_check  # noqa: F401
    except ImportError:
        result["status"] = "misconfigured"
        result["mode"] = "direct_in_process"
        result["reason"] = "celery package not installed (pip install celery[redis])"
        return result

    # Attempt broker connectivity (Celery broker is typically Redis)
    try:
        import redis
        started = time.perf_counter()
        client = redis.Redis.from_url(CELERY_BROKER_URL, socket_connect_timeout=3, socket_timeout=3, decode_responses=True)
        pong = client.ping()
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        client.close()

        result["status"] = "active"
        result["mode"] = "celery"
        result["latency_ms"] = latency_ms
        result["verified"] = True
    except ImportError:
        result["status"] = "misconfigured"
        result["mode"] = "direct_in_process"
        result["reason"] = "redis package not installed (needed for Celery broker)"
        result["verified"] = False
    except Exception as exc:
        result["status"] = "unavailable"
        result["mode"] = "direct_in_process"
        result["error"] = str(exc)[:200]
        result["verified"] = False
        result["reason"] = "Celery broker not reachable; tasks will run in-process"

    return result


# ---------------------------------------------------------------------------
# Full stack validation
# ---------------------------------------------------------------------------

def validate_stack() -> dict[str, Any]:
    """Run all probes and return a comprehensive stack report.

    Returns
    -------
    dict with keys: subsystems (list), summary, validated_at
    """
    started = time.perf_counter()

    probes = [
        probe_database,
        probe_redis,
        probe_mlflow,
        probe_prefect,
        probe_celery,
    ]

    subsystems = []
    for probe in probes:
        try:
            subsystems.append(probe())
        except Exception as exc:
            subsystems.append({
                "subsystem": probe.__name__.replace("probe_", ""),
                "status": "error",
                "error": str(exc)[:200],
            })

    total_ms = round((time.perf_counter() - started) * 1000, 1)

    # Build summary
    active_count = sum(1 for s in subsystems if s.get("status") == "active")
    fallback_count = sum(1 for s in subsystems if s.get("status") == "fallback")
    unavailable_count = sum(1 for s in subsystems if s.get("status") == "unavailable")
    misconfigured_count = sum(1 for s in subsystems if s.get("status") == "misconfigured")

    return {
        "subsystems": subsystems,
        "summary": {
            "active": active_count,
            "fallback": fallback_count,
            "unavailable": unavailable_count,
            "misconfigured": misconfigured_count,
            "total": len(subsystems),
            "validation_ms": total_ms,
        },
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def log_stack_status():
    """Validate stack and log results. Called during startup."""
    report = validate_stack()
    summary = report["summary"]

    log_event(
        logger,
        logging.INFO,
        "stack.validated",
        active=summary["active"],
        fallback=summary["fallback"],
        unavailable=summary["unavailable"],
        misconfigured=summary["misconfigured"],
        validation_ms=summary["validation_ms"],
    )

    # Log individual subsystem status at appropriate levels
    for sub in report["subsystems"]:
        level = logging.INFO if sub.get("status") == "active" else logging.WARNING
        log_event(logger, level, f"stack.{sub['subsystem']}",
                  status=sub.get("status"), mode=sub.get("mode"))

    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_db_url(url: str) -> str:
    """Mask password in database URL."""
    if "://" not in url:
        return url
    if "@" in url:
        scheme_rest = url.split("://", 1)
        if len(scheme_rest) == 2:
            creds_host = scheme_rest[1].split("@", 1)
            if len(creds_host) == 2:
                return f"{scheme_rest[0]}://***:***@{creds_host[1]}"
    return url


def _mask_url(url: str) -> str:
    """Mask password in any URL."""
    if not url:
        return ""
    if "@" in url:
        parts = url.split("@", 1)
        prefix = parts[0]
        if ":" in prefix:
            scheme_user = prefix.rsplit(":", 1)[0]
            return f"{scheme_user}:***@{parts[1]}"
    return url
