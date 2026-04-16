from pydantic import BaseModel, Field

from backend.app.core.date_defaults import recent_end_date_iso, recent_start_date_iso


class MarketTerminalChartRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    timeframe: str = Field(default="1D")
    range_key: str = Field(default="3M")
    compare_symbols: list[str] = Field(default_factory=list)


class MarketTerminalContextRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    start_date: str = Field(default_factory=recent_start_date_iso)
    end_date: str = Field(default_factory=recent_end_date_iso)
