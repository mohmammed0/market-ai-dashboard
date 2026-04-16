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
    before = get_broker_summary(refresh=True)
    mode = str(before.get("mode") or "disabled").strip().lower()
    paper = bool(before.get("paper", False))
    provider = str(before.get("provider") or "none")
    live_execution_enabled = bool(before.get("live_execution_enabled", False))
    before_positions = len(before.get("positions") or [])
    before_open_orders = int((before.get("totals") or {}).get("open_orders") or 0)

    if provider == "none":
        return {
            "ok": False,
            "error": "Broker provider is not configured.",
            "audit": {
                "provider": provider,
                "mode": mode,
                "paper": paper,
                "before_positions": before_positions,
                "before_open_orders": before_open_orders,
            },
        }

    if not paper or mode != "paper" or live_execution_enabled:
        return {
            "ok": False,
            "error": "Refusing to liquidate a non-paper broker account.",
            "audit": {
                "provider": provider,
                "mode": mode,
                "paper": paper,
                "live_execution_enabled": live_execution_enabled,
                "before_positions": before_positions,
                "before_open_orders": before_open_orders,
            },
        }

    result = _liquidate_broker_positions(cancel_open_orders=cancel_open_orders)
    sync_result = None
    after = None
    if result.get("ok"):
        try:
            from backend.app.application.execution.service import sync_internal_positions_from_broker

            sync_result = sync_internal_positions_from_broker(strategy_mode="classic")
        except Exception as exc:
            sync_result = {"ok": False, "error": str(exc)}
        after = get_broker_summary(refresh=True)
        log_event(
            logger,
            logging.WARNING,
            "broker.paper_reset.executed",
            provider=provider,
            before_positions=before_positions,
            after_positions=len((after or {}).get("positions") or []),
            before_open_orders=before_open_orders,
            after_open_orders=int(((after or {}).get("totals") or {}).get("open_orders") or 0),
            sync_ok=bool(sync_result is None or sync_result.get("ok", True)),
        )
    else:
        log_event(
            logger,
            logging.WARNING,
            "broker.paper_reset.failed",
            provider=provider,
            before_positions=before_positions,
            before_open_orders=before_open_orders,
            error=result.get("error"),
        )

    result["audit"] = {
        "provider": provider,
        "mode": mode,
        "paper": paper,
        "live_execution_enabled": live_execution_enabled,
        "before_positions": before_positions,
        "before_open_orders": before_open_orders,
        "after_positions": len((after or {}).get("positions") or []),
        "after_open_orders": int(((after or {}).get("totals") or {}).get("open_orders") or 0),
    }
    if after is not None:
        result["post_liquidation_summary"] = {
            "account": after.get("account"),
            "totals": after.get("totals"),
            "positions": after.get("positions"),
        }
    if sync_result is not None:
        result["internal_sync"] = sync_result
    return result
