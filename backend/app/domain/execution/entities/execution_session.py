from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ExecutionSession(BaseModel):
    correlation_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = "control_plane"


__all__ = ["ExecutionSession"]

