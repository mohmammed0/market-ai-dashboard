from __future__ import annotations

from pydantic import BaseModel, Field


class OpenAISettingsUpdateRequest(BaseModel):
    enabled: bool = False
    model: str = Field(default="gpt-5.4-mini", min_length=1, max_length=120)
    api_key: str | None = Field(default=None, max_length=4096)
    clear_api_key: bool = False


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
