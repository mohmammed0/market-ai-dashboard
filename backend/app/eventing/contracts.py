"""Initial event contracts for the trading pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


EVENT_TOPIC_MARKET_QUOTE = "market.normalized.quote"
EVENT_TOPIC_FEATURE_SNAPSHOT = "feature.snapshot.updated"
EVENT_TOPIC_STRATEGY_SIGNAL = "strategy.signal.generated"
EVENT_TOPIC_RISK_DECISION = "risk.decision.made"
EVENT_TOPIC_EXECUTION_ORDER = "execution.order.created"
EVENT_TOPIC_EXECUTION_FILL = "execution.fill.received"


class EventEnvelope(BaseModel):
    topic: str
    event_id: str
    producer: str
    correlation_id: str | None = None
    payload_version: str = "v1"
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any]


class MarketQuotePayload(BaseModel):
    symbol: str
    price: float | None = None
    prev_close: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    source: str | None = None
    captured_at: datetime | None = None


class FeatureSnapshotPayload(BaseModel):
    symbol: str
    feature_set: str
    as_of: datetime
    values: dict[str, Any] = Field(default_factory=dict)


class StrategySignalPayload(BaseModel):
    symbol: str
    strategy_mode: str
    signal: str
    confidence: float | None = None
    price: float | None = None
    reasoning: str | None = None


class RiskDecisionPayload(BaseModel):
    symbol: str
    intent: str
    side: str
    approved: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    position_value: float | None = None
    risk_budget: float | None = None


class ExecutionOrderPayload(BaseModel):
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    status: str
    strategy_mode: str | None = None
    limit_price: float | None = None


class ExecutionFillPayload(BaseModel):
    client_order_id: str
    symbol: str
    side: str
    fill_price: float
    filled_quantity: float
    fee_amount: float | None = None
    slippage_adj: float | None = None
    spread_adj: float | None = None
    correlation_id: str | None = None
