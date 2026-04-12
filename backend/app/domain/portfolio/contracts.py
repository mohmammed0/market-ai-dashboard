from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PortfolioPosition(BaseModel):
    portfolio_source: Literal["internal_paper", "broker_paper", "broker_live"]
    symbol: str
    side: str
    quantity: float = 0.0
    current_price: float | None = None
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    strategy_mode: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_bucket: str | None = None
    weight_pct: float = 0.0
    updated_at: datetime | None = None


class PortfolioSourceSummary(BaseModel):
    source: str
    positions: int = 0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0


class PortfolioSnapshot(BaseModel):
    generated_at: datetime
    positions: list[PortfolioPosition] = Field(default_factory=list)
    sources: list[PortfolioSourceSummary] = Field(default_factory=list)
    total_market_value: float = 0.0
    total_unrealized_pnl: float = 0.0
