from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BrokerStatus(BaseModel):
    provider: str
    enabled: bool = False
    configured: bool = False
    sdk_installed: bool = False
    connected: bool = False
    mode: str = "disabled"
    paper: bool = True
    live_execution_enabled: bool = False
    order_submission_enabled: bool = False
    detail: str = ""


class BrokerAccount(BaseModel):
    account_id: str | None = None
    status: str | None = None
    currency: str | None = None
    equity: float = 0.0
    cash: float = 0.0
    buying_power: float = 0.0
    portfolio_value: float = 0.0
    daytrade_count: int = 0
    pattern_day_trader: bool = False
    trading_blocked: bool = False
    transfers_blocked: bool = False
    account_blocked: bool = False


class BrokerPosition(BaseModel):
    symbol: str | None = None
    side: str | None = None
    qty: float = 0.0
    avg_entry_price: float = 0.0
    market_value: float = 0.0
    cost_basis: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    change_today_pct: float = 0.0


class BrokerOrder(BaseModel):
    id: str | None = None
    client_order_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    type: str | None = None
    status: str | None = None
    qty: float = 0.0
    filled_qty: float = 0.0
    filled_avg_price: float = 0.0
    submitted_at: str | None = None
    updated_at: str | None = None


class BrokerSummary(BaseModel):
    status: BrokerStatus
    account: BrokerAccount | None = None
    positions: list[BrokerPosition] = Field(default_factory=list)
    orders: list[BrokerOrder] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
