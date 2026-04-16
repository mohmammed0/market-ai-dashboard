from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    event_version: str = "1"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    producer: str
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


__all__ = ["EventEnvelope"]

