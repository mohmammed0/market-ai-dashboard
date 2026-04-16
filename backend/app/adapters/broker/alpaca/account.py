from __future__ import annotations

from backend.app.adapters.broker.alpaca.client import get_alpaca_provider


def get_account_snapshot(refresh: bool = False) -> dict:
    return get_alpaca_provider().get_account(refresh=refresh)


__all__ = ["get_account_snapshot"]

