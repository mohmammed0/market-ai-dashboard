from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.broker.service import (
    get_broker_account,
    get_broker_orders,
    get_broker_positions,
    get_broker_status,
    get_broker_summary,
    liquidate_broker_positions,
)
from backend.app.domain.broker.contracts import BrokerStatus, BrokerSummaryResponse
from backend.app.readmodels import build_broker_readmodel


router = APIRouter(prefix="/broker", tags=["broker"])


class BrokerLiquidationRequest(BaseModel):
    cancel_open_orders: bool = True


@router.get("/status", response_model=BrokerStatus)
def broker_status():
    try:
        return build_broker_readmodel(refresh=False)["status"]
    except Exception as exc:
        return {
            "provider": "none",
            "mode": "disabled",
            "trading_mode": "cash",
            "connected": False,
            "enabled": False,
            "configured": False,
            "detail": str(exc),
            "sdk_installed": False,
        }


@router.get("/summary", response_model=BrokerSummaryResponse)
def broker_summary(refresh: bool = False):
    return build_broker_readmodel(refresh=refresh)["summary"]


@router.get("/account")
def broker_account(refresh: bool = False):
    return build_broker_readmodel(refresh=refresh)["account"]


@router.get("/positions")
def broker_positions(refresh: bool = False):
    return build_broker_readmodel(refresh=refresh)["positions"]


@router.get("/orders")
def broker_orders(refresh: bool = False):
    return build_broker_readmodel(refresh=refresh)["orders"]


@router.post("/liquidate")
def broker_liquidate(payload: BrokerLiquidationRequest):
    return liquidate_broker_positions(cancel_open_orders=payload.cancel_open_orders)
