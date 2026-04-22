from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


class PortfolioViewSummary(BaseModel):
    active_source: Literal["internal_paper", "broker_paper", "broker_live"] = "broker_live"
    provider: str = "broker"
    connected: bool = False
    mode: str = "live"
    open_positions: int = 0
    open_orders: int = 0
    total_market_value: float = 0.0
    invested_cost: float = 0.0
    cash_balance: float = 0.0
    total_equity: float = 0.0
    portfolio_value: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_realized_pnl: float = 0.0
    total_trades: int = 0
    starting_cash: float = 0.0
    win_rate_pct: float | None = None


class PortfolioViewPosition(BaseModel):
    portfolio_source: str = "broker_live"
    symbol: str
    side: str
    quantity: float = 0.0
    qty: float = 0.0
    avg_entry_price: float | None = None
    current_price: float | None = None
    market_value: float = 0.0
    cost_basis: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl_pct: float | None = None
    change_today_pct: float | None = None
    stop_loss_price: float | None = None
    trailing_stop_pct: float | None = None
    trailing_stop_price: float | None = None
    high_water_mark: float | None = None
    strategy_mode: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap_bucket: str | None = None
    weight_pct: float = 0.0
    updated_at: datetime | None = None


class PortfolioViewOrder(BaseModel):
    id: str | int | None = None
    client_order_id: str | None = None
    portfolio_source: str = "broker_live"
    symbol: str = ""
    side: str = ""
    order_type: str | None = None
    type: str | None = None
    status: str = ""
    quantity: float = 0.0
    qty: float = 0.0
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    limit_price: float | None = None
    submitted_at: str | None = None
    updated_at: str | None = None
    notes: str | None = None
    raw_status: str | None = None


class PortfolioViewTrade(BaseModel):
    id: str | int | None = None
    portfolio_source: str = "broker_live"
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    realized_pnl: float = 0.0
    status: str | None = None
    created_at: str | None = None
    notes: str | None = None


class PortfolioSnapshotPayload(BaseModel):
    generated_at: datetime
    active_source: Literal["internal_paper", "broker_paper", "broker_live"] = "broker_live"
    broker_connected: bool = False
    summary: PortfolioViewSummary
    positions: list[PortfolioViewPosition] = Field(default_factory=list)
    items: list[PortfolioViewPosition] = Field(default_factory=list)
    orders: list[PortfolioViewOrder] = Field(default_factory=list)
    open_orders: list[PortfolioViewOrder] = Field(default_factory=list)
    trades: list[PortfolioViewTrade] = Field(default_factory=list)
    broker_status: dict[str, Any] | None = None
    broker_account: dict[str, Any] | None = None
    source_summaries: list[PortfolioSourceSummary] = Field(default_factory=list)
    canonical_snapshot: PortfolioSnapshot


class PortfolioSnapshotV1(PortfolioSnapshotPayload):
    contract_version: Literal["v1"] = "v1"
    source_type: Literal["broker", "internal"] = "broker"
    source_label: str = "Broker Live"
