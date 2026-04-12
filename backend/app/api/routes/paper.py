from fastapi import APIRouter, Query

from backend.app.api.error_handling import to_http_exception
from backend.app.api.job_submission import submit_background_job_or_raise
from backend.app.application.execution.service import (
    cancel_paper_order,
    create_paper_order,
    get_alert_history,
    get_paper_control_panel,
    get_internal_portfolio,
    get_signal_history,
    get_trade_history,
    list_paper_orders,
)
from backend.app.schemas.requests import PaperOrderCreateRequest, PaperSignalRefreshRequest
from backend.app.services.background_jobs import JOB_TYPE_PAPER_REFRESH
from backend.app.services.job_workflows import run_paper_signal_refresh_workflow


router = APIRouter(prefix="/paper", tags=["paper"])


@router.get("/control-panel")
def paper_control_panel():
    return get_paper_control_panel()


@router.get("/portfolio")
def paper_portfolio():
    return get_internal_portfolio()


@router.get("/trades")
def paper_trades(limit: int = 100):
    return get_trade_history(limit=limit)


@router.get("/alerts")
def paper_alerts(limit: int = 100):
    return get_alert_history(limit=limit)


@router.get("/signals")
def paper_signals(limit: int = 100):
    return get_signal_history(limit=limit)


@router.get("/orders")
def paper_orders(limit: int = 100):
    return list_paper_orders(limit=limit, status=None)


@router.post("/orders")
def paper_order_create(payload: PaperOrderCreateRequest):
    try:
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
    except Exception as exc:
        raise to_http_exception(exc, default_status=400) from exc


@router.post("/orders/{order_id}/cancel")
def paper_order_cancel(order_id: int):
    try:
        return cancel_paper_order(order_id)
    except Exception as exc:
        raise to_http_exception(exc, default_status=404) from exc


@router.post("/refresh")
def paper_refresh(payload: PaperSignalRefreshRequest, sync: bool = Query(default=False)):
    payload_dict = payload.model_dump()
    if sync:
        return run_paper_signal_refresh_workflow(payload_dict)
    return submit_background_job_or_raise(
        job_type=JOB_TYPE_PAPER_REFRESH,
        payload=payload_dict,
        requested_by="anonymous",
    )
