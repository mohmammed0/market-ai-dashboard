from fastapi import APIRouter, Query

from backend.app.api.error_handling import to_http_exception
from backend.app.api.job_submission import submit_background_job_or_raise
from backend.app.application.portfolio.service import build_portfolio_snapshot_payload
from backend.app.application.execution.service import (
    cancel_paper_order as cancel_trading_order,
    create_paper_order as create_trading_order,
    get_alert_history,
    get_paper_control_panel as get_trading_control_panel,
    get_internal_portfolio,
    get_signal_history,
    get_trade_history,
    list_paper_orders as list_trading_orders,
)
from backend.app.schemas.requests import PaperOrderCreateRequest as TradingOrderCreateRequest, PaperSignalRefreshRequest as TradingSignalRefreshRequest
from backend.app.services.background_jobs import JOB_TYPE_PAPER_REFRESH
from backend.app.services.job_workflows import run_paper_signal_refresh_workflow as run_trading_signal_refresh_workflow


router = APIRouter(prefix="/trading", tags=["trading"])


@router.get("/control-panel")
def trading_control_panel(refresh_broker: bool = Query(default=False)):
    return get_trading_control_panel(broker_refresh=refresh_broker)


@router.get("/portfolio")
def trading_portfolio():
    return build_portfolio_snapshot_payload()


@router.get("/trades")
def trading_trades(limit: int = 100):
    return get_trade_history(limit=limit)


@router.get("/alerts")
def trading_alerts(limit: int = 100):
    return get_alert_history(limit=limit)


@router.get("/signals")
def trading_signals(limit: int = 100):
    return get_signal_history(limit=limit)


@router.get("/orders")
def trading_orders(limit: int = 100):
    return list_trading_orders(limit=limit, status=None)


@router.post("/orders")
def trading_order_create(payload: TradingOrderCreateRequest):
    try:
        return create_trading_order(
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
def trading_order_cancel(order_id: str):
    try:
        return cancel_trading_order(order_id)
    except Exception as exc:
        raise to_http_exception(exc, default_status=404) from exc


@router.post("/refresh")
def trading_refresh(payload: TradingSignalRefreshRequest, sync: bool = Query(default=False)):
    payload_dict = payload.model_dump()
    if sync:
        return run_trading_signal_refresh_workflow(payload_dict)
    return submit_background_job_or_raise(
        job_type=JOB_TYPE_PAPER_REFRESH,
        payload=payload_dict,
        requested_by="anonymous",
    )
