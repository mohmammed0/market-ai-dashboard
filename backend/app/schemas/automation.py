from pydantic import BaseModel, Field
from backend.app.core.date_defaults import recent_end_date_iso, recent_start_date_iso


class StrategyEvaluationRequest(BaseModel):
    instrument: str = Field(default="AAPL")
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)
    hold_days: int = Field(default=10)
    include_modes: list[str] = Field(default_factory=lambda: ["classic", "vectorbt", "ml", "dl", "ensemble"])
    windows: int = Field(default=3)


class AutomationRunRequest(BaseModel):
    job_name: str = Field(default="market_cycle")
    dry_run: bool = Field(default=True)
    preset: str = Field(default="ALL_US_EQUITIES")


class SmartWatchlistRequest(BaseModel):
    preset: str = Field(default="ALL_US_EQUITIES")
    limit: int = Field(default=24)


class EventCalendarRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "SPY"])
    limit: int = Field(default=20)
