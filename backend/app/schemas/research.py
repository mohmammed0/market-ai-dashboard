from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    instrument: str = Field(default="AAPL")
    start_date: str = Field(default="2024-01-01")
    end_date: str = Field(default="2026-04-02")


class ScanRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA"])
    start_date: str = Field(default="2024-01-01")
    end_date: str = Field(default="2026-04-02")


class BacktestRequest(BaseModel):
    instrument: str = Field(default="AAPL")
    start_date: str = Field(default="2024-01-01")
    end_date: str = Field(default="2026-04-02")
    hold_days: int = Field(default=10)
    min_technical_score: int = Field(default=2)
    buy_score_threshold: int = Field(default=3)
    sell_score_threshold: int = Field(default=4)


class OptimizerRequest(BaseModel):
    instrument: str = Field(default="AAPL")
    start_date: str = Field(default="2024-01-01")
    end_date: str = Field(default="2026-04-02")


class HistoryRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    start_date: str = Field(default="2024-01-01")
    end_date: str = Field(default="2026-04-02")
    interval: str = Field(default="1d")


class QuoteRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "SPY"])
