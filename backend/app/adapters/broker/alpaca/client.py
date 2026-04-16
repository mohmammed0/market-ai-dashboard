from __future__ import annotations

from backend.app.services.broker.registry import get_broker_provider


def get_alpaca_provider():
    provider = get_broker_provider()
    if getattr(provider, "provider_name", "") != "alpaca":
        raise RuntimeError("Configured broker provider is not Alpaca.")
    return provider


__all__ = ["get_alpaca_provider"]

