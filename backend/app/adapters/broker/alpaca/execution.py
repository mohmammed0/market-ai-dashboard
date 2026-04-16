from __future__ import annotations

from backend.app.adapters.broker.base import BrokerOrderIntent
from backend.app.adapters.broker.alpaca.client import get_alpaca_provider


def submit_order(intent: BrokerOrderIntent) -> dict:
    provider = get_alpaca_provider()
    return provider.submit_order(
        symbol=intent.symbol,
        qty=intent.qty,
        side=intent.side,
        order_type=intent.order_type,
        time_in_force=intent.time_in_force,
        limit_price=intent.limit_price,
    )


def reconcile() -> dict:
    provider = get_alpaca_provider()
    return {
        "account": provider.get_account(refresh=True),
        "positions": provider.get_positions(refresh=True),
        "orders": provider.get_orders(refresh=True),
    }


__all__ = ["reconcile", "submit_order"]

