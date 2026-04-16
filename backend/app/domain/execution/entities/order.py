from __future__ import annotations

from pydantic import BaseModel

from packages.contracts.enums import ExecutionStatus


class ExecutionOrder(BaseModel):
    order_id: str
    symbol: str
    side: str
    qty: float
    status: ExecutionStatus
    broker_order_id: str | None = None


__all__ = ["ExecutionOrder"]

