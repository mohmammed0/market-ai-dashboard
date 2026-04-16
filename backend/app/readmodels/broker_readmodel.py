from __future__ import annotations

from backend.app.broker.service import (
    get_broker_account,
    get_broker_orders,
    get_broker_positions,
    get_broker_status,
    get_broker_summary,
)


def build_broker_readmodel(*, refresh: bool = False) -> dict:
    return {
        "status": get_broker_status(),
        "summary": get_broker_summary(refresh=refresh),
        "account": get_broker_account(refresh=refresh),
        "positions": get_broker_positions(refresh=refresh),
        "orders": get_broker_orders(refresh=refresh),
    }


__all__ = ["build_broker_readmodel"]

