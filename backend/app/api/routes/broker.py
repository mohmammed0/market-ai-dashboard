from fastapi import APIRouter

from backend.app.application.broker.service import (
    get_broker_account,
    get_broker_orders,
    get_broker_positions,
    get_broker_status,
    get_broker_summary,
)


router = APIRouter(prefix="/broker", tags=["broker"])


@router.get("/status")
def broker_status():
    return get_broker_status()


@router.get("/summary")
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
