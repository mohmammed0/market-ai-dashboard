from fastapi import APIRouter

from backend.app.application.broker.service import (
    get_broker_account,
    get_broker_orders,
    get_broker_positions,
    get_broker_status,
    get_broker_summary,
)
from backend.app.domain.broker.contracts import BrokerStatus, BrokerSummaryResponse


router = APIRouter(prefix="/broker", tags=["broker"])


@router.get("/status", response_model=BrokerStatus)
def broker_status():
    try:
        return get_broker_status()
    except Exception as exc:
        return {
            "provider": "none",
            "effective_mode": "disabled",
            "connected": False,
            "enabled": False,
            "configured": False,
            "detail": str(exc),
            "sdk_installed": False,
        }


@router.get("/summary", response_model=BrokerSummaryResponse)
def broker_summary(refresh: bool = False):
    return get_broker_summary(refresh=refresh)


@router.get("/account")
def broker_account(refresh: bool = False):
    return get_broker_account(refresh=refresh)


@router.get("/positions")
def broker_positions(refresh: bool = False):
    return get_broker_positions(refresh=refresh)


@router.get("/orders")
def broker_orders(refresh: bool = False):
    return get_broker_orders(refresh=refresh)
