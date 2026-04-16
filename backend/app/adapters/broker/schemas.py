from __future__ import annotations

from pydantic import BaseModel


class BrokerAccountSnapshot(BaseModel):
    provider: str
    connected: bool = False
    buying_power: float | None = None
    equity: float | None = None
    cash: float | None = None


class BrokerPositionSnapshot(BaseModel):
    symbol: str
    qty: float
    market_value: float | None = None
    unrealized_pnl: float | None = None


class BrokerOrderSnapshot(BaseModel):
    symbol: str
    side: str
    qty: float
    status: str
    order_type: str = "market"


__all__ = ["BrokerAccountSnapshot", "BrokerPositionSnapshot", "BrokerOrderSnapshot"]

