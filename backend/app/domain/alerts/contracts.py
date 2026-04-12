from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AlertRecord(BaseModel):
    id: int | None = None
    symbol: str | None = None
    strategy_mode: str | None = None
    alert_type: str
    severity: str = "info"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
