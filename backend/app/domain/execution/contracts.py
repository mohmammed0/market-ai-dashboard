from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SignalSnapshot(BaseModel):
    symbol: str
    strategy_mode: str
    signal: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(default=0.0, ge=0.0)
    price: float = Field(default=0.0, ge=0.0)
    reasoning: str = ""
    analysis_payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionCommand(BaseModel):
    symbol: str
    strategy_mode: str
    quantity: float = Field(default=1.0, gt=0.0)
    source: str = "internal_simulator"
    auto_execute: bool = True
    correlation_id: str | None = None


class TradeIntent(BaseModel):
    intent: Literal["OPEN_LONG", "OPEN_SHORT", "CLOSE_LONG", "CLOSE_SHORT", "NONE"]
    symbol: str
    strategy_mode: str
    side: Literal["LONG", "SHORT"] | None = None
    quantity: float = Field(default=0.0, ge=0.0)
    execution_price: float = Field(default=0.0, ge=0.0)
    reason: str = ""


class PositionState(BaseModel):
    id: int | None = None
    symbol: str
    strategy_mode: str
    side: Literal["LONG", "SHORT"]
    quantity: float
    avg_entry_price: float
    current_price: float | None = None
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    status: str = "OPEN"
    stop_loss_price: float | None = None
    trailing_stop_pct: float | None = None
    trailing_stop_price: float | None = None
    high_water_mark: float | None = None
    opened_at: datetime | None = None
    updated_at: datetime | None = None


class ExecutionEventRecord(BaseModel):
    event_type: str
    source: str = "internal_simulator"
    portfolio_source: str = "internal_paper"
    symbol: str | None = None
    strategy_mode: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TradeRecord(BaseModel):
    id: int | None = None
    symbol: str
    strategy_mode: str
    action: str
    side: str
    quantity: float
    price: float
    realized_pnl: float | None = None
    notes: str | None = None
    created_at: datetime | None = None


class SignalRecord(BaseModel):
    id: int | None = None
    symbol: str
    strategy_mode: str
    signal: str
    confidence: float = 0.0
    price: float | None = None
    reasoning: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class PaperOrderRecord(BaseModel):
    id: int | None = None
    client_order_id: str
    symbol: str
    strategy_mode: str | None = None
    side: Literal["BUY", "SELL"]
    order_type: str = "market"
    quantity: float
    limit_price: float | None = None
    status: str = "OPEN"
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
