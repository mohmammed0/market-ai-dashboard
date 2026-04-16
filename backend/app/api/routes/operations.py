from fastapi import APIRouter, Query

from backend.app.services.event_replay import replay_order_events
from backend.app.services.operations import get_operations_logs, get_operations_overview
from backend.app.services.orchestration_gateway import (
    dispatch_maintenance_reconcile,
    get_orchestration_status,
)


router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/overview")
def operations_overview():
    return get_operations_overview()


@router.get("/logs")
def operations_logs(limit: int = Query(default=100, ge=10, le=500)):
    return get_operations_logs(limit=limit)


@router.get("/orchestration")
def orchestration_status():
    """Report orchestration topology: Prefect, Celery, and APScheduler status."""
    return get_orchestration_status()


@router.post("/orchestration/reconcile")
def orchestration_reconcile():
    """Run stale-job reconciliation through the orchestration gateway.

    Uses Celery if available, otherwise falls back to direct in-process execution.
    """
    return dispatch_maintenance_reconcile()


@router.post("/events/replay")
def replay_events(
    limit: int = Query(default=100, ge=1, le=1000),
    event_type: str | None = Query(default=None),
):
    return replay_order_events(limit=limit, event_type=event_type)
