from __future__ import annotations

from backend.app.adapters.broker.alpaca import submit_order as submit_alpaca_order
from backend.app.adapters.broker.base import BrokerOrderIntent
from backend.app.services.runtime_settings import get_broker_runtime_config


def route_execution_intent(intent: BrokerOrderIntent, *, broker: str | None = None) -> dict:
    configured_provider = str(get_broker_runtime_config().get("provider") or "alpaca").strip().lower()
    normalized = str(broker or configured_provider or "alpaca").strip().lower()
    if normalized != "alpaca":
        raise RuntimeError(
            f"Broker provider '{normalized}' is not supported. Internal simulated execution is disabled."
        )
    return submit_alpaca_order(intent)


__all__ = ["route_execution_intent"]
