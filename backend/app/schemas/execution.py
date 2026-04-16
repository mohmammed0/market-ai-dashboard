from pydantic import BaseModel, Field
from backend.app.core.date_defaults import recent_end_date_iso, recent_start_date_iso


class PaperSignalRefreshRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "SPY"])
    mode: str = Field(default="classic")
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)
    auto_execute: bool = Field(default=True)
    quantity: float = Field(default=1.0)
    idempotency_key: str | None = Field(
        default=None,
        description=(
            "Optional caller-supplied idempotency key. "
            "If the same key has already been processed, the request is "
            "returned deduplicated without re-executing any trades."
        ),
    )


class RiskPlanRequest(BaseModel):
    entry_price: float = Field(default=100.0)
    stop_loss_price: float | None = Field(default=None)
    take_profit_price: float | None = Field(default=None)
    portfolio_value: float = Field(default=100000.0)
    risk_per_trade_pct: float = Field(default=1.0)
    max_daily_loss_pct: float = Field(default=2.5)
    atr_pct: float | None = Field(default=None)


class JournalEntryRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    strategy_mode: str | None = Field(default="classic")
    paper_trade_id: int | None = Field(default=None)
    entry_reason: str | None = Field(default=None)
    exit_reason: str | None = Field(default=None)
    thesis: str | None = Field(default=None)
    risk_plan: str | None = Field(default=None)
    post_trade_review: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    result_classification: str | None = Field(default=None)
    analysis_snapshot: dict = Field(default_factory=dict)
