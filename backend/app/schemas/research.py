from pydantic import BaseModel, Field

from backend.app.core.date_defaults import recent_end_date_iso, recent_start_date_iso


class AnalyzeRequest(BaseModel):
    instrument: str = Field(default="AAPL")
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)


class ScanRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA"])
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)


class BacktestRequest(BaseModel):
    instrument: str = Field(default="AAPL")
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)
    hold_days: int = Field(default=10)
    min_technical_score: int = Field(default=2)
    buy_score_threshold: int = Field(default=3)
    sell_score_threshold: int = Field(default=4)


class OptimizerRequest(BaseModel):
    instrument: str = Field(default="AAPL")
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)


class HistoryRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)
    interval: str = Field(default="1d")


class QuoteRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "SPY"])
