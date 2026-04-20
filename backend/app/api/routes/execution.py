from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.execution.service import (
    confirm_paper_order,
    create_paper_order,
    cancel_paper_order,
    get_alert_history,
    get_execution_audit,
    get_execution_reconciliation,
    get_internal_portfolio,
    get_signal_history,
    get_trade_history,
    list_paper_orders,
    preview_paper_order,
    refresh_signals,
)
from backend.app.readmodels import build_execution_monitor_readmodel
from backend.app.schemas.requests import PaperSignalRefreshRequest
from backend.app.services.execution_halt import disable_halt, enable_halt, get_halt_status


router = APIRouter(prefix="/execution", tags=["execution"])


class HaltRequest(BaseModel):
    reason: str = ""
    enabled_by: str = "api"


class PreviewOrderRequest(BaseModel):
    symbol: str
    side: str  # "BUY" | "SELL"
    quantity: float
    order_type: str = "market"
    limit_price: float | None = None
    strategy_mode: str | None = "manual"
    notes: str | None = None


class PaperOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    order_type: str = "market"
    limit_price: float | None = None
    strategy_mode: str | None = "manual"
    notes: str | None = None
    client_order_id: str | None = None


class ExecutionReconcileRequest(BaseModel):
    broker: str = "alpaca"
    strategy_mode: str = "classic"
    apply_sync: bool = False


@router.get("/portfolio")
def execution_portfolio():
    return build_execution_monitor_readmodel(limit=200)["portfolio"]


@router.get("/trades")
def execution_trades(limit: int = Query(default=200, ge=1, le=500)):
    return get_trade_history(limit=limit)


@router.get("/signals")
def execution_signals(limit: int = Query(default=200, ge=1, le=500)):
    return get_signal_history(limit=limit)


@router.get("/alerts")
def execution_alerts(limit: int = Query(default=200, ge=1, le=500), severity: str | None = None):
    return get_alert_history(limit=limit, severity=severity)


@router.get("/audit")
def execution_audit(limit: int = Query(default=200, ge=1, le=500), symbol: str | None = None):
    return get_execution_audit(limit=limit, symbol=symbol)


@router.get("/reconcile")
def execution_reconcile(
    broker: str = Query(default="alpaca"),
    strategy_mode: str = Query(default="classic"),
):
    return get_execution_reconciliation(
        broker=broker,
        strategy_mode=strategy_mode,
        apply_sync=False,
    )


@router.post("/reconcile")
def execution_reconcile_apply(payload: ExecutionReconcileRequest):
    return get_execution_reconciliation(
        broker=payload.broker,
        strategy_mode=payload.strategy_mode,
        apply_sync=payload.apply_sync,
    )


@router.post("/refresh")
def execution_refresh(payload: PaperSignalRefreshRequest):
    return refresh_signals(
        symbols=payload.symbols,
        mode=payload.mode,
        start_date=payload.start_date,
        end_date=payload.end_date,
        auto_execute=payload.auto_execute,
        quantity=payload.quantity,
        idempotency_key=payload.idempotency_key,
    )


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------

@router.post("/halt")
def execution_halt(payload: HaltRequest):
    """Enable the execution kill switch.  All new execution attempts are blocked."""
    return enable_halt(reason=payload.reason, enabled_by=payload.enabled_by)


@router.get("/halt-status")
def execution_halt_status():
    """Return the current halt state."""
    return get_halt_status()


@router.delete("/halt")
def execution_halt_clear():
    """Clear the execution kill switch.  Execution is permitted again."""
    return disable_halt(disabled_by="api")


# ---------------------------------------------------------------------------
# Broker-managed order compatibility surfaces
# ---------------------------------------------------------------------------

@router.get("/orders")
def execution_orders(
    limit: int = Query(default=100, ge=1, le=500),
    status: str | None = None,
):
    return list_paper_orders(limit=limit, status=status)


@router.get("/monitor")
def execution_monitor(limit: int = Query(default=100, ge=1, le=500)):
    return build_execution_monitor_readmodel(limit=limit)


@router.post("/orders")
def execution_create_order(payload: PaperOrderRequest):
    return create_paper_order(
        symbol=payload.symbol,
        side=payload.side,
        quantity=payload.quantity,
        order_type=payload.order_type,
        limit_price=payload.limit_price,
        strategy_mode=payload.strategy_mode,
        notes=payload.notes,
        client_order_id=payload.client_order_id,
    )


@router.delete("/orders/{order_id}")
def execution_cancel_order(order_id: str):
    try:
        return cancel_paper_order(order_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Two-phase execution: preview → confirm
# ---------------------------------------------------------------------------

@router.post("/preview")
def execution_preview(payload: PreviewOrderRequest):
    """Phase 1 — compute a fill preview without placing an order.

    Returns an ``ExecutionPreview`` with a ``preview_id`` that must be passed
    to ``POST /execution/confirm/{preview_id}`` within 5 minutes to execute.
    """
    preview = preview_paper_order(
        symbol=payload.symbol,
        side=payload.side,
        quantity=payload.quantity,
        order_type=payload.order_type,
        limit_price=payload.limit_price,
        strategy_mode=payload.strategy_mode,
        notes=payload.notes,
    )
    return preview.model_dump(mode="json")


@router.post("/confirm/{preview_id}")
def execution_confirm(preview_id: str):
    """Phase 2 — confirm a previously computed preview, placing the paper order.

    The preview_id must be obtained from ``POST /execution/preview`` and
    submitted within 5 minutes of generation.
    """
    result = confirm_paper_order(preview_id)
    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Trust / audit surfaces
# ---------------------------------------------------------------------------

@router.get("/orders/{order_id}/fill-details")
def order_fill_details(order_id: int):
    """Return structured fill details for a paper order.

    Parses the fill audit data from the order's associated audit event and
    returns it as a structured breakdown: reference_price, spread, slippage,
    fee, fill_price, fill_ratio, partial fill status.
    """
    import json
    from backend.app.services.storage import session_scope
    from backend.app.models.execution import ExecutionAuditEvent, PaperOrder

    with session_scope() as session:
        order = session.query(PaperOrder).filter(PaperOrder.id == order_id).first()
        if order is None:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

        # Parse fill details from notes (compact format)
        notes_breakdown = _parse_fill_notes(order.notes) if order.notes else {}

        # Find associated audit event for full fill data
        audit_row = (
            session.query(ExecutionAuditEvent)
            .filter(
                ExecutionAuditEvent.event_type == "paper_order_created",
                ExecutionAuditEvent.symbol == order.symbol,
            )
            .order_by(ExecutionAuditEvent.created_at.desc())
            .first()
        )
        audit_fill = {}
        trace_id = None
        if audit_row and audit_row.payload_json:
            try:
                payload = json.loads(audit_row.payload_json)
                audit_fill = payload.get("fill") or {}
                trace_id = payload.get("trace_id") or audit_row.correlation_id
            except Exception:
                pass

    return {
        "order_id": order_id,
        "symbol": order.symbol,
        "side": order.side,
        "status": order.status,
        "trace_id": trace_id,
        "fill_breakdown": audit_fill or notes_breakdown,
        "notes_raw": order.notes,
    }


@router.get("/trades/{trade_id}/trust")
def trade_trust_details(trade_id: int):
    """Return trust-surface data for a paper trade: fill details,
    associated audit events, and journal entry link."""
    import json
    from backend.app.services.storage import session_scope
    from backend.app.models.execution import PaperTrade, ExecutionAuditEvent
    from backend.app.models.journal import TradeJournalEntry

    with session_scope() as session:
        trade = session.query(PaperTrade).filter(PaperTrade.id == trade_id).first()
        if trade is None:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        # Parse fill details from trade notes
        fill_breakdown = _parse_fill_notes(trade.notes) if trade.notes else {}

        # Find associated audit events
        audit_events = (
            session.query(ExecutionAuditEvent)
            .filter(
                ExecutionAuditEvent.symbol == trade.symbol,
                ExecutionAuditEvent.strategy_mode == trade.strategy_mode,
            )
            .order_by(ExecutionAuditEvent.created_at.desc())
            .limit(5)
            .all()
        )
        events = []
        for row in audit_events:
            try:
                payload = json.loads(row.payload_json) if row.payload_json else {}
            except Exception:
                payload = {}
            events.append({
                "event_type": row.event_type,
                "correlation_id": row.correlation_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "fill": payload.get("fill"),
            })

        # Check for linked journal entry
        journal = session.query(TradeJournalEntry).filter(
            TradeJournalEntry.paper_trade_id == trade_id
        ).first()
        journal_link = {
            "has_journal": journal is not None,
            "journal_id": journal.id if journal else None,
            "result_classification": journal.result_classification if journal else None,
        } if True else {}

    return {
        "trade_id": trade_id,
        "symbol": trade.symbol,
        "strategy_mode": trade.strategy_mode,
        "action": trade.action,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": trade.price,
        "realized_pnl": trade.realized_pnl,
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
        "fill_breakdown": fill_breakdown,
        "recent_audit_events": events,
        "journal": journal_link,
    }


def _parse_fill_notes(notes: str | None) -> dict:
    """Parse the compact fill string from order/trade notes into a structured dict.

    Expected format: ref=123.4500 | spread=+0.0062 | slip=+0.0062 | fill=123.4624 | qty=10/10 | fee=0.0500
    """
    if not notes:
        return {}
    result = {}
    for part in notes.split("|"):
        part = part.strip()
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "ref":
            result["reference_price"] = _try_float(value)
        elif key == "spread":
            result["spread_adj"] = _try_float(value)
        elif key == "slip":
            result["slippage_adj"] = _try_float(value)
        elif key == "fill":
            result["fill_price"] = _try_float(value)
        elif key == "fee":
            result["fee_amount"] = _try_float(value)
        elif key == "qty":
            if "/" in value:
                filled, _, requested = value.partition("/")
                result["filled_quantity"] = _try_float(filled)
                result["requested_quantity"] = _try_float(requested)
                req = _try_float(requested)
                result["fill_ratio"] = round(_try_float(filled) / req, 4) if req else 1.0
                result["is_partial"] = result["fill_ratio"] < 1.0
    return result


def _try_float(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0
