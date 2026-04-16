from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class PositionView(BaseModel):
    symbol: str
    qty: float
    avg_price: float
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


class PortfolioSummaryView(BaseModel):
    total_market_value: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_realized_pnl: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["PositionView", "PortfolioSummaryView"]

