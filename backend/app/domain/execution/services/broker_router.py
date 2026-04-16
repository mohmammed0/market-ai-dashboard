from __future__ import annotations

from backend.app.adapters.broker.alpaca import submit_order as submit_alpaca_order
from backend.app.adapters.broker.simulated import submit_order as submit_simulated_order
from backend.app.adapters.broker.base import BrokerOrderIntent


def route_execution_intent(intent: BrokerOrderIntent, *, broker: str = "simulated") -> dict:
    normalized = str(broker or "simulated").strip().lower()
    if normalized == "alpaca":
        return submit_alpaca_order(intent)
    return submit_simulated_order(
        symbol=intent.symbol,
        side=intent.side,
        quantity=intent.qty,
        order_type=intent.order_type,
        limit_price=intent.limit_price,
    )


__all__ = ["route_execution_intent"]

