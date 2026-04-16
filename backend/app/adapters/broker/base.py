from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class BrokerOrderIntent(BaseModel):
    symbol: str
    qty: float
    side: str
    order_type: str = "market"
    time_in_force: str = "day"
    limit_price: float | None = None


class BrokerAdapter(Protocol):
    def get_account(self, refresh: bool = False) -> dict: ...
    def get_positions(self, refresh: bool = False) -> dict: ...
    def get_orders(self, refresh: bool = False) -> dict: ...
    def submit_order(self, intent: BrokerOrderIntent) -> dict: ...
    def cancel_order(self, broker_order_id: str) -> dict: ...
    def reconcile(self) -> dict: ...


__all__ = ["BrokerAdapter", "BrokerOrderIntent"]

