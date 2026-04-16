from __future__ import annotations

from backend.app.adapters.broker.schemas import BrokerAccountSnapshot, BrokerOrderSnapshot, BrokerPositionSnapshot


def map_account(payload: dict) -> BrokerAccountSnapshot:
    account = payload.get("account") or {}
    return BrokerAccountSnapshot(
        provider=str(payload.get("provider") or "alpaca"),
        connected=bool(payload.get("connected")),
        buying_power=account.get("buying_power"),
        equity=account.get("equity"),
        cash=account.get("cash"),
    )


def map_positions(payload: dict) -> list[BrokerPositionSnapshot]:
    return [BrokerPositionSnapshot(**item) for item in payload.get("items", [])]


def map_orders(payload: dict) -> list[BrokerOrderSnapshot]:
    return [BrokerOrderSnapshot(**item) for item in payload.get("items", [])]


__all__ = ["map_account", "map_orders", "map_positions"]

