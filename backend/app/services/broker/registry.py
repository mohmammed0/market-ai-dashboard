from __future__ import annotations

from backend.app.services.broker.alpaca import AlpacaBrokerProvider
from backend.app.services.broker.base import DisabledBrokerProvider
from backend.app.services.runtime_settings import get_broker_runtime_config


def get_broker_provider():
    provider = get_broker_runtime_config()["provider"]
    if provider == "alpaca":
        return AlpacaBrokerProvider()
    return DisabledBrokerProvider(detail="No broker provider is configured. Internal paper trading remains available.")


def get_broker_status() -> dict:
    return get_broker_provider().get_status()


def get_broker_account(refresh: bool = False) -> dict:
    return get_broker_provider().get_account(refresh=refresh)


def get_broker_positions(refresh: bool = False) -> dict:
    return get_broker_provider().get_positions(refresh=refresh)


def get_broker_orders(refresh: bool = False) -> dict:
    return get_broker_provider().get_orders(refresh=refresh)


def get_broker_summary(refresh: bool = False) -> dict:
    return get_broker_provider().get_summary(refresh=refresh)
