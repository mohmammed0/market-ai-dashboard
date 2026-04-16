from __future__ import annotations

from pydantic import BaseModel


class ExecutionFill(BaseModel):
    fill_id: str
    order_id: str
    symbol: str
    side: str
    fill_qty: float
    fill_price: float
    fees: float = 0.0


__all__ = ["ExecutionFill"]

