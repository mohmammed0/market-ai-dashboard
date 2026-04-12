"""Readiness API — commercial-grade platform readiness surfaces.

Provides unified answers to operator questions:
- GET /readiness/platform     — overall platform health / readiness
- GET /readiness/strategies   — strategy readiness classifications
- GET /readiness/audit-chain/{trace_id} — full audit chain for a trace
"""

from fastapi import APIRouter, Path, Query

router = APIRouter(prefix="/readiness", tags=["readiness"])


@router.get("/platform")
def platform_readiness():
    """Unified platform readiness: stack health, execution safety,
    strategy trust, orchestration health."""
    from backend.app.services.platform_readiness import get_platform_readiness
    return get_platform_readiness()


@router.get("/strategies")
def strategy_readiness(limit: int = Query(default=20, ge=1, le=100)):
    """Classify recent strategy evaluations into readiness states:
    exploratory, candidate, review_ready, rejected."""
    from backend.app.services.strategy_readiness import get_readiness_summary
    return get_readiness_summary(limit=limit)


@router.get("/audit-chain/{trace_id}")
def audit_chain(trace_id: str = Path(..., min_length=1)):
    """Retrieve the full audit event chain for a given trace_id.

    A trace_id links: preview → confirm → order_created → trade/fill events.
    Returns all audit events with matching correlation_id, ordered chronologically.
    """
    from backend.app.services.storage import session_scope
    from backend.app.models.execution import ExecutionAuditEvent

    with session_scope() as session:
        rows = (
            session.query(ExecutionAuditEvent)
            .filter(ExecutionAuditEvent.correlation_id == trace_id)
            .order_by(ExecutionAuditEvent.created_at.asc())
            .all()
        )
        events = []
        for row in rows:
            import json
            try:
                payload = json.loads(row.payload_json) if row.payload_json else {}
            except Exception:
                payload = {}
            events.append({
                "id": row.id,
                "event_type": row.event_type,
                "source": row.source,
                "symbol": row.symbol,
                "strategy_mode": row.strategy_mode,
                "correlation_id": row.correlation_id,
                "payload": payload,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })

    return {
        "trace_id": trace_id,
        "events": events,
        "event_count": len(events),
        "chain_complete": len(events) > 0,
    }
