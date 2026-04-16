from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.app.core.date_defaults import recent_end_date_iso, recent_start_date_iso


class TrainMLRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "SPY"])
    start_date: str = Field(default="2020-01-01")
    end_date: str = Field(default="2026-04-02")
    horizon_days: int = Field(default=5)
    buy_threshold: float = Field(default=0.02)
    sell_threshold: float = Field(default=-0.02)
    run_optuna: bool = Field(default=False)
    trial_count: int = Field(default=10)


class TrainDLRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "SPY"])
    start_date: str = Field(default="2020-01-01")
    end_date: str = Field(default="2026-04-02")
    sequence_length: int = Field(default=20)
    horizon_days: int = Field(default=5)
    buy_threshold: float = Field(default=0.02)
    sell_threshold: float = Field(default=-0.02)
    epochs: int = Field(default=8)
    hidden_size: int = Field(default=48)
    learning_rate: float = Field(default=0.001)


class InferenceRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)
    include_dl: bool = Field(default=False)
    include_ensemble: bool = Field(default=True)
    run_id: str | None = Field(default=None)


class BatchInferenceRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "NVDA", "SPY"])
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)
    include_dl: bool = Field(default=False)
    include_ensemble: bool = Field(default=True)


class ModelBacktestRequest(BaseModel):
    instrument: str = Field(default="AAPL")
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)
    hold_days: int = Field(default=10)
    mode: str = Field(default="ml")


class AINewsAnalyzeRequest(BaseModel):
    symbol: str | None = Field(default=None)
    headline: str | None = Field(default=None)
    article_text: str | None = Field(default=None)
    items: list[str] = Field(default_factory=list)
    market_context: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_content(self):
        has_headline = bool(str(self.headline or "").strip())
        has_article = bool(str(self.article_text or "").strip())
        has_items = any(str(item or "").strip() for item in self.items)
        if not (has_headline or has_article or has_items):
            raise ValueError("Provide headline, article_text, or at least one item.")
        return self


class AINewsAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentiment: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float = Field(ge=0, le=100)
    impact_horizon: Literal["INTRADAY", "SHORT_TERM", "MEDIUM_TERM", "LONG_TERM"]
    summary: str
    bullish_factors: list[str] = Field(default_factory=list)
    bearish_factors: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    catalysts: list[str] = Field(default_factory=list)
    affected_tickers: list[str] = Field(default_factory=list)
    analyst_note: str
