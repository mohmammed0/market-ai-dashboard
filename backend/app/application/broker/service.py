from __future__ import annotations

import logging

from backend.app.core.logging_utils import get_logger, log_event
from backend.app.domain.broker.contracts import BrokerAccount, BrokerOrder, BrokerPosition, BrokerStatus, BrokerSummary
from backend.app.repositories.broker_state import BrokerSnapshotRepository
from backend.app.services.broker import (
    get_broker_account as _get_broker_account,
    get_broker_orders as _get_broker_orders,
    get_broker_positions as _get_broker_positions,
    get_broker_status as _get_broker_status,
    get_broker_summary as _get_broker_summary,
    liquidate_broker_positions as _liquidate_broker_positions,
)
from backend.app.services.storage import session_scope

logger = get_logger(__name__)


def _to_status(payload: dict) -> BrokerStatus:
    return BrokerStatus(**{
        "provider": payload.get("provider", "none"),
        "enabled": bool(payload.get("enabled", False)),
        "configured": bool(payload.get("configured", False)),
        "sdk_installed": bool(payload.get("sdk_installed", False)),
        "connected": bool(payload.get("connected", False)),
        "mode": payload.get("mode", "disabled"),
        "trading_mode": payload.get("trading_mode", "cash"),
        "paper": bool(payload.get("paper", True)),
        "live_execution_enabled": bool(payload.get("live_execution_enabled", False)),
        "order_submission_enabled": bool(payload.get("order_submission_enabled", False)),
        "detail": payload.get("detail", ""),
    })


def _to_account(payload: dict | None) -> BrokerAccount | None:
    return None if not payload else BrokerAccount(**payload)


def _to_positions(items: list[dict] | None) -> list[BrokerPosition]:
    return [BrokerPosition(**item) for item in (items or [])]


def _to_orders(items: list[dict] | None) -> list[BrokerOrder]:
    return [BrokerOrder(**item) for item in (items or [])]


def get_broker_status() -> dict:
    return _to_status(_get_broker_status()).model_dump()


def get_broker_summary(refresh: bool = False) -> dict:
    payload = _get_broker_summary(refresh=refresh)
    status = _to_status(payload)
    summary = BrokerSummary(
        status=status,
        account=_to_account(payload.get("account")),
        positions=_to_positions(payload.get("positions")),
        orders=_to_orders(payload.get("orders")),
        totals=payload.get("totals") or {
            "positions": len(payload.get("positions", [])),
            "open_orders": len(payload.get("orders", [])),
            "market_value": sum(float(item.get("market_value") or 0.0) for item in payload.get("positions", [])),
            "unrealized_pnl": sum(float(item.get("unrealized_pnl") or 0.0) for item in payload.get("positions", [])),
        },
    )
    if status.connected:
        with session_scope() as session:
            BrokerSnapshotRepository(session).record_summary(summary)
    else:
        log_event(logger, logging.INFO, "broker.summary.unavailable", provider=status.provider, mode=status.mode, detail=status.detail)
    payload = summary.model_dump()
    payload.update(status.model_dump())
    payload["account"] = None if summary.account is None else summary.account.model_dump()
    payload["positions"] = [item.model_dump() for item in summary.positions]
    payload["orders"] = [item.model_dump() for item in summary.orders]
    return payload


def get_broker_account(refresh: bool = False) -> dict:
    payload = get_broker_summary(refresh=refresh)
    return {key: payload.get(key) for key in payload if key not in {"positions", "orders", "totals"}} | {"account": payload.get("account")}


def get_broker_positions(refresh: bool = False) -> dict:
    payload = get_broker_summary(refresh=refresh)
    status_keys = {key: payload.get(key) for key in payload if key not in {"account", "positions", "orders", "totals"}}
    return {**status_keys, "items": payload.get("positions", []), "count": len(payload.get("positions", []))}


def get_broker_orders(refresh: bool = False) -> dict:
    payload = get_broker_summary(refresh=refresh)
    status_keys = {key: payload.get(key) for key in payload if key not in {"account", "positions", "orders", "totals"}}
    return {**status_keys, "items": payload.get("orders", []), "count": len(payload.get("orders", []))}


def liquidate_broker_positions(cancel_open_orders: bool = True) -> dict:
    return _liquidate_broker_positions(cancel_open_orders=cancel_open_orders)
