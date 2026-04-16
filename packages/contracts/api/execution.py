from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from packages.contracts.enums import ExecutionStatus


class ExecutionOrderIntent(BaseModel):
    order_intent_id: str = Field(default_factory=lambda: str(uuid4()))
    signal_id: str | None = None
    broker: str = "simulated"
    symbol: str
    side: str
    qty: float
    order_type: str = "market"
    time_in_force: str = "day"
    client_order_id: str | None = None
    idempotency_key: str | None = None
    status: ExecutionStatus = ExecutionStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExecutionAuditView(BaseModel):
    event_type: str
    symbol: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["ExecutionOrderIntent", "ExecutionAuditView"]

