from __future__ import annotations

from pydantic import BaseModel, Field

class AlpacaSettingsUpdateRequest(BaseModel):
    enabled: bool = False
    provider: str = Field(default="alpaca", min_length=2, max_length=40)
    paper: bool = True
    trading_mode: str = Field(default="cash", pattern="^(cash|margin)$")
    api_key: str | None = Field(default=None, max_length=1024)
    secret_key: str | None = Field(default=None, max_length=2048)
    clear_api_key: bool = False
    clear_secret_key: bool = False
    url_override: str | None = Field(default=None, max_length=2048)
    auto_trading_enabled: bool | None = None
    order_submission_enabled: bool | None = None
    auto_trading_cycle_minutes: int | None = Field(default=None, ge=1, le=720)
    auto_trading_strategy_mode: str | None = Field(default=None, pattern="^(classic|ml|dl|ensemble)$")
    auto_trading_trade_direction: str | None = Field(default=None, pattern="^(both|long_only|short_only)$")
    auto_trading_universe_preset: str | None = Field(default=None, max_length=64)
    auto_trading_symbol_limit: int | None = Field(default=None, ge=1, le=500)
    auto_trading_use_full_portfolio: bool | None = None
    auto_trading_analysis_lookback_days: int | None = Field(default=None, ge=0, le=3650)
    auto_trading_notional_per_trade: float | None = Field(default=None, ge=0, le=100000000)
    auto_trading_quantity: float | None = Field(default=None, ge=0, le=1000000)
    auto_trading_min_signal_confidence: float | None = Field(default=None, ge=0, le=100)
    auto_trading_min_ensemble_score: float | None = Field(default=None, ge=0, le=1)
    auto_trading_min_agreement: float | None = Field(default=None, ge=0, le=1)
    auto_trading_allow_add_to_existing_longs: bool | None = None
    auto_trading_add_long_min_confidence: float | None = Field(default=None, ge=0, le=100)
    auto_trading_add_long_min_score: float | None = Field(default=None, ge=0, le=1)
    auto_trading_add_long_max_position_pct: float | None = Field(default=None, ge=0, le=100)
    auto_trading_add_long_max_adds_per_symbol_per_day: int | None = Field(default=None, ge=0, le=50)
    auto_trading_add_long_cooldown_minutes: int | None = Field(default=None, ge=0, le=1440)
    auto_trading_add_long_min_notional: float | None = Field(default=None, ge=0, le=100000000)
    auto_trading_add_long_min_shares: float | None = Field(default=None, ge=0, le=1000000)
    auto_trading_regime_enabled: bool | None = None
    auto_trading_opportunity_min_score: float | None = Field(default=None, ge=0, le=100)
    auto_trading_portfolio_max_new_positions: int | None = Field(default=None, ge=0, le=20)
    auto_trading_portfolio_cash_reserve_pct: float | None = Field(default=None, ge=0, le=95)
    auto_trading_portfolio_max_position_pct: float | None = Field(default=None, ge=0, le=100)
    auto_trading_portfolio_max_gross_exposure_pct: float | None = Field(default=None, ge=0, le=100)
    auto_trading_partial_funding_enabled: bool | None = None
    auto_trading_min_partial_funding_notional: float | None = Field(default=None, ge=0, le=100000000)
    auto_trading_min_partial_funding_ratio: float | None = Field(default=None, ge=0, le=1)
    auto_trading_partial_funding_top_rank_only: bool | None = None
    auto_trading_reduce_on_regime_defensive: bool | None = None
    auto_trading_exit_on_thesis_break: bool | None = None
    auto_trading_add_long_enabled: bool | None = None
    auto_trading_reduce_long_enabled: bool | None = None
    auto_trading_position_builder_enabled: bool | None = None
    auto_trading_execution_orchestrator_enabled: bool | None = None
    auto_trading_execution_max_submissions_per_cycle: int | None = Field(default=None, ge=1, le=50)
    auto_trading_execution_submission_spacing_seconds: int | None = Field(default=None, ge=0, le=120)
    auto_trading_execution_symbol_cooldown_seconds: int | None = Field(default=None, ge=0, le=3600)
    auto_trading_execution_require_release_before_entries: bool | None = None
    auto_trading_execution_retry_enabled: bool | None = None
    auto_trading_execution_retry_max_attempts: int | None = Field(default=None, ge=1, le=6)
    auto_trading_execution_retry_initial_backoff_seconds: int | None = Field(default=None, ge=1, le=120)
    auto_trading_execution_retry_max_backoff_seconds: int | None = Field(default=None, ge=1, le=900)
    auto_trading_execution_retry_backoff_multiplier: float | None = Field(default=None, ge=1, le=6)
    auto_trading_execution_retry_jitter_enabled: bool | None = None
    auto_trading_execution_retry_allowed_for_broker_submit: bool | None = None
    auto_trading_execution_retry_allowed_for_dependency_wait: bool | None = None
    auto_trading_execution_reconciliation_enabled: bool | None = None
    auto_trading_execution_reconciliation_window_seconds: int | None = Field(default=None, ge=5, le=300)
    auto_trading_execution_reconciliation_poll_interval_seconds: int | None = Field(default=None, ge=1, le=60)
    auto_trading_execution_reconciliation_max_polls: int | None = Field(default=None, ge=1, le=120)
    auto_trading_execution_reconciliation_stop_on_terminal: bool | None = None
    auto_trading_execution_reconciliation_update_dependent_actions: bool | None = None
