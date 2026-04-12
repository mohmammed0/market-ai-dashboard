"""Orchestration Gateway — Prefect / Celery live dispatch layer.

Provides a clean boundary between the application and external orchestration
systems.  The existing APScheduler-based scheduler is NOT removed; this
module adds a layered seam on top so heavy workflows and recurring tasks can
be progressively migrated.

Integration status
------------------
Prefect (heavy workflows)
    LIVE-CAPABLE.  If the ``prefect`` package is installed AND
    ``PREFECT_API_URL`` is set and reachable, heavy workflows are submitted
    to Prefect.  Otherwise the fallback calls the existing service function
    in-process, preserving current behaviour.

Celery (short recurring tasks)
    LIVE-CAPABLE.  If the ``celery`` package is installed AND
    ``CELERY_BROKER_URL`` is set and reachable, tasks are dispatched via the
    broker to a Celery worker.  Otherwise the fallback runs in-process.
    Worker can be started via: celery -A backend.app.services.celery_app worker

Named orchestrated workflows
-----------------------------
- ``run_strategy_evaluation_orchestrated`` – strategy_evaluation workflow (Prefect)
- ``run_batch_inference_orchestrated``      – batch_inference workflow (Prefect)
- ``dispatch_maintenance_reconcile``        – stale-job reconciliation task (Celery)
- ``dispatch_quote_snapshot``               – quote snapshot refresh task (Celery)
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from backend.app.core.logging_utils import get_logger, log_event

from backend.app.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND, PREFECT_API_URL

logger = get_logger(__name__)

_PREFECT_API_URL: str = PREFECT_API_URL
_CELERY_BROKER_URL: str = CELERY_BROKER_URL


# ---------------------------------------------------------------------------
# Availability probes
# ---------------------------------------------------------------------------

def is_prefect_available() -> bool:
    try:
        import prefect  # noqa: F401
        return bool(_PREFECT_API_URL)
    except ImportError:
        return False


def is_celery_available() -> bool:
    try:
        import celery  # noqa: F401
        return bool(_CELERY_BROKER_URL)
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Prefect adapter — heavy workflows
# ---------------------------------------------------------------------------

def submit_heavy_workflow(
    workflow_name: str,
    payload: dict[str, Any],
    *,
    fallback: Callable[[dict[str, Any]], Any] | None = None,
) -> dict:
    """Submit a heavy workflow to Prefect or fall back to direct execution.

    Parameters
    ----------
    workflow_name : str
        Logical workflow name (matches Prefect deployment name).
    payload : dict
        Workflow input payload.
    fallback : callable | None
        ``fallback(payload) -> Any`` called when Prefect is not available.
    """
    if is_prefect_available():
        try:
            return _submit_to_prefect(workflow_name, payload)
        except Exception as exc:
            log_event(logger, logging.WARNING, "orchestration.prefect_failed",
                      workflow=workflow_name, error=str(exc))

    log_event(logger, logging.DEBUG, "orchestration.prefect_fallback",
              workflow=workflow_name)
    if fallback is not None:
        result = fallback(payload)
        return result if isinstance(result, dict) else {"result": result}
    return {
        "status": "skipped",
        "reason": "No Prefect and no fallback provided",
        "workflow": workflow_name,
    }


def _submit_to_prefect(workflow_name: str, payload: dict) -> dict:
    """Execute a flow through Prefect's runtime.

    First checks for a registered @flow wrapper (local execution tracked by
    the Prefect server).  Falls back to ``run_deployment`` for pre-registered
    deployments if no local flow is available.
    """
    from backend.app.services.prefect_flows import get_flow  # noqa: PLC0415

    flow_fn = get_flow(workflow_name)
    if flow_fn is not None:
        result = flow_fn(payload=payload)
        flow_run_id = result.pop("_prefect_flow_run_id", None) if isinstance(result, dict) else None
        return {
            "status": "completed",
            "backend": "prefect",
            "workflow": workflow_name,
            "flow_run_id": flow_run_id,
            "result": result if isinstance(result, dict) else {"value": result},
        }

    # No registered flow — try run_deployment for pre-registered deployments
    from prefect.deployments import run_deployment  # type: ignore[import-not-found]
    run = run_deployment(name=workflow_name, parameters=payload)
    return {
        "status": "submitted",
        "backend": "prefect",
        "flow_run_id": str(run.id),
        "workflow": workflow_name,
    }


# ---------------------------------------------------------------------------
# Celery adapter — short recurring tasks
# ---------------------------------------------------------------------------

def dispatch_recurring_task(
    task_name: str,
    payload: dict[str, Any] | None = None,
    *,
    fallback: Callable[[], Any] | None = None,
) -> dict:
    """Dispatch a short recurring task to Celery or fall back to direct execution.

    Parameters
    ----------
    task_name : str
        Celery task name (e.g. ``"tasks.reconcile_stale_jobs"``).
    payload : dict | None
        Optional task kwargs.
    fallback : callable | None
        ``fallback() -> Any`` called when Celery is not available.
    """
    if is_celery_available():
        try:
            return _dispatch_to_celery(task_name, payload or {})
        except Exception as exc:
            log_event(logger, logging.WARNING, "orchestration.celery_failed",
                      task=task_name, error=str(exc))

    log_event(logger, logging.DEBUG, "orchestration.celery_fallback", task=task_name)
    if fallback is not None:
        result = fallback()
        return {
            "status": "executed_inline",
            "backend": "direct",
            "task": task_name,
            "result": result,
        }
    return {
        "status": "skipped",
        "reason": "No Celery and no fallback provided",
        "task": task_name,
    }


def _dispatch_to_celery(task_name: str, payload: dict) -> dict:
    """Send a task to the Celery broker.  Requires ``celery`` + running broker."""
    from backend.app.services.celery_app import get_celery_app  # noqa: PLC0415

    app = get_celery_app()
    if app is None:
        # Celery app creation failed — should not happen since is_celery_available passed
        from celery import Celery  # type: ignore[import-not-found]
        kwargs: dict[str, Any] = {"broker": _CELERY_BROKER_URL}
        if CELERY_RESULT_BACKEND:
            kwargs["backend"] = CELERY_RESULT_BACKEND
        app = Celery("market_ai", **kwargs)

    async_result = app.send_task(task_name, kwargs=payload)
    return {
        "status": "dispatched",
        "backend": "celery",
        "task_id": async_result.id,
        "task": task_name,
    }


# ---------------------------------------------------------------------------
# Named workflow helpers
# ---------------------------------------------------------------------------

def run_strategy_evaluation_orchestrated(payload: dict) -> dict:
    """Run strategy evaluation via Prefect (or direct in-process fallback)."""
    from backend.app.services.job_workflows import run_strategy_evaluation_workflow  # noqa: PLC0415
    return submit_heavy_workflow(
        "strategy_evaluation",
        payload,
        fallback=run_strategy_evaluation_workflow,
    )


def run_batch_inference_orchestrated(payload: dict) -> dict:
    """Run batch inference via Prefect (or direct in-process fallback)."""
    from backend.app.services.job_workflows import run_batch_inference_workflow  # noqa: PLC0415
    return submit_heavy_workflow(
        "batch_inference",
        payload,
        fallback=run_batch_inference_workflow,
    )


def dispatch_maintenance_reconcile() -> dict:
    """Run stale-job reconciliation via Celery (or direct in-process fallback)."""
    def _inline() -> dict:
        from backend.app.services.background_jobs import reconcile_stale_jobs  # noqa: PLC0415
        from backend.app.application.model_lifecycle.training_jobs import (  # noqa: PLC0415
            reconcile_stale_training_jobs,
        )
        return {
            "bg_jobs_reconciled": reconcile_stale_jobs(),
            "training_jobs_reconciled": reconcile_stale_training_jobs(),
        }

    return dispatch_recurring_task(
        "tasks.maintenance_reconcile",
        fallback=_inline,
    )


def dispatch_quote_snapshot() -> dict:
    """Run quote snapshot refresh via Celery (or direct in-process fallback).

    This is the canonical example of a short recurring operational task
    routed through Celery when available.
    """
    def _inline() -> dict:
        from backend.app.services.market_data import fetch_quote_snapshots  # noqa: PLC0415
        from backend.app.config import DEFAULT_SAMPLE_SYMBOLS  # noqa: PLC0415
        result = fetch_quote_snapshots(DEFAULT_SAMPLE_SYMBOLS)
        return {"status": "ok", "snapshots": len(result.get("items", []))}

    return dispatch_recurring_task(
        "tasks.quote_snapshot",
        fallback=_inline,
    )


# ---------------------------------------------------------------------------
# Orchestration status
# ---------------------------------------------------------------------------

def get_orchestration_status() -> dict:
    """Return the current orchestration status: what is active, fallback, or unavailable.

    This is the single authoritative source for understanding the orchestration
    topology at runtime.
    """
    prefect = is_prefect_available()
    celery = is_celery_available()

    def _backend_label(available: bool, name: str) -> str:
        if available:
            return "active"
        try:
            __import__(name)
            return "installed_but_not_configured"
        except ImportError:
            return "unavailable"

    # MLflow status
    try:
        from backend.app.services.experiment_tracker import get_tracking_status
        mlflow_status = get_tracking_status()
    except Exception:
        mlflow_status = {"status": "unavailable", "backend": "local_db"}

    # Registered Prefect flows (locally executable)
    try:
        from backend.app.services.prefect_flows import list_flows  # noqa: PLC0415
        registered_flows = list_flows() if prefect else []
    except Exception:
        registered_flows = []

    return {
        "prefect": {
            "status": _backend_label(prefect, "prefect"),
            "api_url": _PREFECT_API_URL or None,
            "registered_flows": registered_flows,
            "workflows_registered": [
                {"name": "strategy_evaluation", "mode": "prefect" if prefect else "direct_fallback"},
                {"name": "batch_inference", "mode": "prefect" if prefect else "direct_fallback"},
            ],
        },
        "celery": {
            "status": _backend_label(celery, "celery"),
            "broker_url": _CELERY_BROKER_URL or None,
            "result_backend_configured": bool(CELERY_RESULT_BACKEND),
            "tasks_registered": [
                {"name": "tasks.maintenance_reconcile", "mode": "celery" if celery else "direct_fallback"},
                {"name": "tasks.quote_snapshot", "mode": "celery" if celery else "direct_fallback"},
            ],
        },
        "mlflow": mlflow_status,
        "apscheduler": {
            "status": "active",
            "note": "APScheduler remains the primary scheduler. Prefect/Celery are optional overlay.",
        },
        "summary": {
            "heavy_workflows": "prefect" if prefect else "direct_in_process",
            "recurring_tasks": "celery" if celery else "direct_in_process",
            "experiment_tracking": mlflow_status.get("backend", "local_db"),
            "scheduler": "apscheduler",
        },
    }
