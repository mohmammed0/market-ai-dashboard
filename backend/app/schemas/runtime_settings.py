from __future__ import annotations

from pydantic import BaseModel, Field

class AlpacaSettingsUpdateRequest(BaseModel):
    enabled: bool = False
    provider: str = Field(default="alpaca", min_length=2, max_length=40)
    paper: bool = True
    api_key: str | None = Field(default=None, max_length=1024)
    secret_key: str | None = Field(default=None, max_length=2048)
    clear_api_key: bool = False
    clear_secret_key: bool = False
    url_override: str | None = Field(default=None, max_length=2048)
    auto_trading_enabled: bool | None = None
    order_submission_enabled: bool | None = None
    auto_trading_cycle_minutes: int | None = Field(default=None, ge=1, le=720)
