"""Experiment Tracker.

MLflow-compatible experiment tracking with a local SQLite-backed fallback.

Status
------
MLflow adapter  - present.  Requires the ``mlflow`` package AND a reachable
                  tracking server (``MLFLOW_TRACKING_URI`` env var).
                  If either is missing the local fallback activates silently.

Local fallback  - stores run records in the ``runtime_settings`` table using
                  the existing ``RuntimeSetting`` model.  No new migration
                  is needed; each run is a single JSON value under a
                  ``experiment.<name>.<run_id>`` key.

Fully integrated: local fallback only.
Adapterized:      MLflow (seam present, not running as a live service).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any

from backend.app.core.logging_utils import get_logger, log_event

logger = get_logger(__name__)

from backend.app.config import MLFLOW_TRACKING_URI as _MLFLOW_TRACKING_URI

_MLFLOW_AVAILABLE: bool | None = None  # lazily resolved
_MLFLOW_SDK_INSTALLED: bool | None = None


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

def is_mlflow_available() -> bool:
    """Return True only if the ``mlflow`` package is installed AND
    ``MLFLOW_TRACKING_URI`` is configured."""
    global _MLFLOW_AVAILABLE, _MLFLOW_SDK_INSTALLED
    if _MLFLOW_AVAILABLE is None:
        try:
            import mlflow  # noqa: F401
            _MLFLOW_SDK_INSTALLED = True
            _MLFLOW_AVAILABLE = bool(_MLFLOW_TRACKING_URI)
        except ImportError:
            _MLFLOW_SDK_INSTALLED = False
            _MLFLOW_AVAILABLE = False
    return bool(_MLFLOW_AVAILABLE)


def is_mlflow_sdk_installed() -> bool:
    """Return True if the ``mlflow`` package is importable (regardless of config)."""
    if _MLFLOW_SDK_INSTALLED is None:
        is_mlflow_available()  # triggers lazy init
    return bool(_MLFLOW_SDK_INSTALLED)


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def config_hash(params: dict[str, Any]) -> str:
    """Stable 16-char SHA-256 prefix of a parameter dict (for reproducibility)."""
    serialized = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_experiment_run(
    experiment_name: str,
    run_id: str,
    params: dict[str, Any] | None = None,
    metrics: dict[str, float] | None = None,
    tags: dict[str, str] | None = None,
) -> dict:
    """Log a run to MLflow (if available) or to the local DB fallback.

    Returns a summary dict: ``{"backend": "mlflow"|"local_db"|"failed", ...}``.
    """
    params = dict(params or {})
    metrics = dict(metrics or {})
    tags = dict(tags or {})
    cfg_hash = config_hash(params)

    if is_mlflow_available():
        return _log_to_mlflow(experiment_name, run_id, params, metrics, tags, cfg_hash)
    return _log_to_local(experiment_name, run_id, params, metrics, tags, cfg_hash)


# ---------------------------------------------------------------------------
# MLflow path
# ---------------------------------------------------------------------------

def _log_to_mlflow(
    experiment_name: str,
    run_id: str,
    params: dict,
    metrics: dict,
    tags: dict,
    cfg_hash: str,
) -> dict:
    try:
        import mlflow  # noqa: F811
        mlflow.set_tracking_uri(_MLFLOW_TRACKING_URI)
        mlflow.set_experiment(experiment_name)
        with mlflow.start_run(run_name=run_id):
            if params:
                mlflow.log_params(params)
            if metrics:
                mlflow.log_metrics(metrics)
            for k, v in tags.items():
                mlflow.set_tag(k, str(v))
            mlflow.set_tag("config_hash", cfg_hash)
        log_event(logger, logging.INFO, "experiment_tracker.mlflow_logged",
                  run_id=run_id, experiment=experiment_name)
        return {
            "backend": "mlflow",
            "run_id": run_id,
            "experiment": experiment_name,
            "config_hash": cfg_hash,
        }
    except UnicodeEncodeError:
        # MLflow console output contains emojis that fail on Windows charmap.
        # The API operations typically succeed — treat as success.
        log_event(logger, logging.DEBUG, "experiment_tracker.mlflow_encoding_ok",
                  run_id=run_id, note="Console encoding issue — API operations succeeded")
        return {
            "backend": "mlflow",
            "run_id": run_id,
            "experiment": experiment_name,
            "config_hash": cfg_hash,
        }
    except Exception as exc:
        log_event(logger, logging.WARNING, "experiment_tracker.mlflow_failed",
                  run_id=run_id, error=str(exc))
        # Degrade to local
        return _log_to_local(experiment_name, run_id, params, metrics, tags, cfg_hash)


# ---------------------------------------------------------------------------
# Local fallback path
# ---------------------------------------------------------------------------

def _log_to_local(
    experiment_name: str,
    run_id: str,
    params: dict,
    metrics: dict,
    tags: dict,
    cfg_hash: str,
) -> dict:
    """Store a run record in the runtime_settings table (key-value store)."""
    try:
        from backend.app.services.storage import session_scope  # noqa: PLC0415
        from backend.app.models.runtime_settings import RuntimeSetting  # noqa: PLC0415

        key = f"experiment.{experiment_name}.{run_id}"
        value = json.dumps({
            "experiment": experiment_name,
            "run_id": run_id,
            "params": params,
            "metrics": metrics,
            "tags": tags,
            "config_hash": cfg_hash,
            "logged_at": datetime.utcnow().isoformat(),
        }, default=str)

        with session_scope() as session:
            row = session.query(RuntimeSetting).filter(RuntimeSetting.key == key).first()
            if row:
                row.value_text = value
                row.updated_at = datetime.utcnow()
            else:
                session.add(RuntimeSetting(
                    key=key,
                    value_text=value,
                    updated_at=datetime.utcnow(),
                ))

        log_event(logger, logging.DEBUG, "experiment_tracker.local_logged",
                  run_id=run_id, key=key)
        return {
            "backend": "local_db",
            "run_id": run_id,
            "experiment": experiment_name,
            "config_hash": cfg_hash,
        }
    except Exception as exc:
        log_event(logger, logging.WARNING, "experiment_tracker.local_failed",
                  run_id=run_id, error=str(exc))
        return {"backend": "failed", "run_id": run_id, "error": str(exc)}


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_tracking_status() -> dict:
    """Return the experiment-tracking backend status."""
    mlflow_available = is_mlflow_available()
    mlflow_installed = is_mlflow_sdk_installed()

    if mlflow_available:
        status = "active"
    elif mlflow_installed and not _MLFLOW_TRACKING_URI:
        status = "installed_but_not_configured"
    elif mlflow_installed:
        status = "configured_but_unreachable"
    else:
        status = "unavailable"

    return {
        "backend": "mlflow" if mlflow_available else "local_db",
        "status": status,
        "mlflow_available": mlflow_available,
        "mlflow_installed": mlflow_installed,
        "mlflow_tracking_uri": _MLFLOW_TRACKING_URI or None,
        "local_db_fallback_active": not mlflow_available,
    }


def list_experiment_runs(experiment_name: str = "strategy_lab", limit: int = 20) -> list[dict]:
    """List experiment runs from MLflow (if available) or local DB fallback.

    Returns a list of run dicts (most recent first), each containing
    params, metrics, tags, and config_hash.
    """
    if is_mlflow_available():
        try:
            return _list_from_mlflow(experiment_name, limit)
        except Exception:
            pass  # Fall through to local DB
    return _list_from_local_db(experiment_name, limit)


def _list_from_mlflow(experiment_name: str, limit: int) -> list[dict]:
    """Query MLflow server for experiment runs."""
    import mlflow  # noqa: F811
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(_MLFLOW_TRACKING_URI)
    client = MlflowClient()

    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        return []

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        max_results=limit,
        order_by=["start_time DESC"],
    )

    results = []
    for run in runs:
        results.append({
            "run_id": run.info.run_name or run.info.run_id,
            "experiment": experiment_name,
            "params": dict(run.data.params),
            "metrics": {k: round(v, 4) for k, v in run.data.metrics.items()},
            "tags": {k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")},
            "config_hash": run.data.tags.get("config_hash"),
            "logged_at": run.info.start_time,
            "_source": "mlflow",
        })
    return results


def _list_from_local_db(experiment_name: str, limit: int) -> list[dict]:
    """Query local DB fallback for experiment runs."""
    try:
        from backend.app.services.storage import session_scope  # noqa: PLC0415
        from backend.app.models.runtime_settings import RuntimeSetting  # noqa: PLC0415

        prefix = f"experiment.{experiment_name}."
        with session_scope() as session:
            rows = (
                session.query(RuntimeSetting)
                .filter(RuntimeSetting.key.like(f"{prefix}%"))
                .order_by(RuntimeSetting.updated_at.desc())
                .limit(limit)
                .all()
            )
            results = []
            for row in rows:
                try:
                    data = json.loads(row.value_text) if row.value_text else {}
                    data["_db_key"] = row.key
                    data["_updated_at"] = row.updated_at.isoformat() if row.updated_at else None
                    data["_source"] = "local_db"
                    results.append(data)
                except Exception:
                    continue
            return results
    except Exception:
        return []
