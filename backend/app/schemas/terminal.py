from pydantic import BaseModel, Field


class MarketTerminalChartRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    timeframe: str = Field(default="1D")
    range_key: str = Field(default="3M")
    compare_symbols: list[str] = Field(default_factory=list)


class MarketTerminalContextRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    start_date: str = Field(default="2024-01-01")
    end_date: str = Field(default="2026-04-02")
