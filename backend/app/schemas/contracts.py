from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.portfolio.contracts import PortfolioSnapshotV1


class AuthStatus(BaseModel):
    auth_enabled: bool
    detail: str
    warnings: list[str] = Field(default_factory=list)


class AIProviderStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool | None = None
    status: str = "unknown"
    model: str | None = None
    base_url: str | None = None
    timeout_seconds: float | None = None
    context_length: int | None = None
    detail: str | None = None
    server_reachable: bool | None = None
    model_loaded: bool | None = None


class AICompatibilityStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool | None = None
    status: str = "standby"
    detail: str | None = None


class AIStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    active_provider: str
    effective_status: str = "unavailable"
    effective_provider: str | None = None
    ollama: AIProviderStatus = Field(default_factory=AIProviderStatus)
    openai: AICompatibilityStatus = Field(default_factory=AICompatibilityStatus)


class SymbolSignalResponse(BaseModel):
    symbol: str
    mode: str = "ensemble"
    signal: str = "HOLD"
    confidence: float = 0.0
    score: float = 0.0
    price: float | None = None
    reasoning: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class DashboardLiteResponse(BaseModel):
    generated_at: datetime
    ai_status: AIStatus
    portfolio_snapshot: PortfolioSnapshotV1
    market_overview: dict[str, Any] = Field(default_factory=dict)
    news: dict[str, Any] = Field(default_factory=dict)
    signals: dict[str, Any] = Field(default_factory=dict)
    auto_trading: dict[str, Any] = Field(default_factory=dict)
    automation: dict[str, Any] = Field(default_factory=dict)
    telegram: dict[str, Any] = Field(default_factory=dict)


class DashboardWidgetResponse(BaseModel):
    widget: str
    generated_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)
