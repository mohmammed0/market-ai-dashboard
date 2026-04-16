from __future__ import annotations

from backend.app.adapters.broker.alpaca.client import get_alpaca_provider


def get_orders_snapshot(refresh: bool = False) -> dict:
    return get_alpaca_provider().get_orders(refresh=refresh)


def cancel_order(order_id: str) -> dict:
    return get_alpaca_provider().cancel_order(order_id)


__all__ = ["cancel_order", "get_orders_snapshot"]

