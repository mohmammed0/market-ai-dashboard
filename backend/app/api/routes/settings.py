from fastapi import APIRouter, HTTPException

from backend.app.schemas.runtime_settings import AlpacaSettingsUpdateRequest
from backend.app.services.runtime_control import get_runtime_control_plane
from backend.app.services.runtime_settings import (
    get_runtime_settings_overview,
    RuntimeSettingsError,
    save_alpaca_runtime_settings,
    test_alpaca_runtime_settings,
)


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/runtime")
def runtime_settings():
    try:
        payload = get_runtime_settings_overview()
        payload["control_plane"] = get_runtime_control_plane()
        return payload
    except RuntimeSettingsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/runtime/alpaca")
def update_alpaca_settings(payload: AlpacaSettingsUpdateRequest):
    try:
        settings = save_alpaca_runtime_settings(
            enabled=payload.enabled,
            provider=payload.provider,
            trading_mode=payload.trading_mode,
            api_key=payload.api_key,
            secret_key=payload.secret_key,
            clear_api_key=payload.clear_api_key,
            clear_secret_key=payload.clear_secret_key,
            url_override=payload.url_override,
            auto_trading_enabled=payload.auto_trading_enabled,
            order_submission_enabled=payload.order_submission_enabled,
            auto_trading_cycle_minutes=payload.auto_trading_cycle_minutes,
            auto_trading_strategy_mode=payload.auto_trading_strategy_mode,
            auto_trading_trade_direction=payload.auto_trading_trade_direction,
            auto_trading_universe_preset=payload.auto_trading_universe_preset,
            auto_trading_symbol_limit=payload.auto_trading_symbol_limit,
            auto_trading_use_full_portfolio=payload.auto_trading_use_full_portfolio,
            auto_trading_analysis_lookback_days=payload.auto_trading_analysis_lookback_days,
            auto_trading_notional_per_trade=payload.auto_trading_notional_per_trade,
            auto_trading_quantity=payload.auto_trading_quantity,
            auto_trading_min_signal_confidence=payload.auto_trading_min_signal_confidence,
            auto_trading_min_ensemble_score=payload.auto_trading_min_ensemble_score,
            auto_trading_min_agreement=payload.auto_trading_min_agreement,
            auto_trading_allow_add_to_existing_longs=payload.auto_trading_allow_add_to_existing_longs,
            auto_trading_add_long_min_confidence=payload.auto_trading_add_long_min_confidence,
            auto_trading_add_long_min_score=payload.auto_trading_add_long_min_score,
            auto_trading_add_long_max_position_pct=payload.auto_trading_add_long_max_position_pct,
            auto_trading_add_long_max_adds_per_symbol_per_day=payload.auto_trading_add_long_max_adds_per_symbol_per_day,
            auto_trading_add_long_cooldown_minutes=payload.auto_trading_add_long_cooldown_minutes,
            auto_trading_add_long_min_notional=payload.auto_trading_add_long_min_notional,
            auto_trading_add_long_min_shares=payload.auto_trading_add_long_min_shares,
            auto_trading_regime_enabled=payload.auto_trading_regime_enabled,
            auto_trading_opportunity_min_score=payload.auto_trading_opportunity_min_score,
            auto_trading_portfolio_max_new_positions=payload.auto_trading_portfolio_max_new_positions,
            auto_trading_portfolio_cash_reserve_pct=payload.auto_trading_portfolio_cash_reserve_pct,
            auto_trading_portfolio_max_position_pct=payload.auto_trading_portfolio_max_position_pct,
            auto_trading_portfolio_max_gross_exposure_pct=payload.auto_trading_portfolio_max_gross_exposure_pct,
            auto_trading_partial_funding_enabled=payload.auto_trading_partial_funding_enabled,
            auto_trading_min_partial_funding_notional=payload.auto_trading_min_partial_funding_notional,
            auto_trading_min_partial_funding_ratio=payload.auto_trading_min_partial_funding_ratio,
            auto_trading_partial_funding_top_rank_only=payload.auto_trading_partial_funding_top_rank_only,
            auto_trading_reduce_on_regime_defensive=payload.auto_trading_reduce_on_regime_defensive,
            auto_trading_exit_on_thesis_break=payload.auto_trading_exit_on_thesis_break,
            auto_trading_add_long_enabled=payload.auto_trading_add_long_enabled,
            auto_trading_reduce_long_enabled=payload.auto_trading_reduce_long_enabled,
            auto_trading_position_builder_enabled=payload.auto_trading_position_builder_enabled,
            auto_trading_execution_orchestrator_enabled=payload.auto_trading_execution_orchestrator_enabled,
            auto_trading_execution_max_submissions_per_cycle=payload.auto_trading_execution_max_submissions_per_cycle,
            auto_trading_execution_submission_spacing_seconds=payload.auto_trading_execution_submission_spacing_seconds,
            auto_trading_execution_symbol_cooldown_seconds=payload.auto_trading_execution_symbol_cooldown_seconds,
            auto_trading_execution_require_release_before_entries=payload.auto_trading_execution_require_release_before_entries,
            auto_trading_execution_retry_enabled=payload.auto_trading_execution_retry_enabled,
            auto_trading_execution_retry_max_attempts=payload.auto_trading_execution_retry_max_attempts,
            auto_trading_execution_retry_initial_backoff_seconds=payload.auto_trading_execution_retry_initial_backoff_seconds,
            auto_trading_execution_retry_max_backoff_seconds=payload.auto_trading_execution_retry_max_backoff_seconds,
            auto_trading_execution_retry_backoff_multiplier=payload.auto_trading_execution_retry_backoff_multiplier,
            auto_trading_execution_retry_jitter_enabled=payload.auto_trading_execution_retry_jitter_enabled,
            auto_trading_execution_retry_allowed_for_broker_submit=payload.auto_trading_execution_retry_allowed_for_broker_submit,
            auto_trading_execution_retry_allowed_for_dependency_wait=payload.auto_trading_execution_retry_allowed_for_dependency_wait,
            auto_trading_execution_reconciliation_enabled=payload.auto_trading_execution_reconciliation_enabled,
            auto_trading_execution_reconciliation_window_seconds=payload.auto_trading_execution_reconciliation_window_seconds,
            auto_trading_execution_reconciliation_poll_interval_seconds=payload.auto_trading_execution_reconciliation_poll_interval_seconds,
            auto_trading_execution_reconciliation_max_polls=payload.auto_trading_execution_reconciliation_max_polls,
            auto_trading_execution_reconciliation_stop_on_terminal=payload.auto_trading_execution_reconciliation_stop_on_terminal,
            auto_trading_execution_reconciliation_update_dependent_actions=payload.auto_trading_execution_reconciliation_update_dependent_actions,
        )
        return {
            "saved": True,
            "detail": "Alpaca runtime settings saved.",
            "settings": settings,
        }
    except RuntimeSettingsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/runtime/alpaca/test")
def test_alpaca_settings():
    try:
        return test_alpaca_runtime_settings()
    except RuntimeSettingsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/runtime/alpaca/test-live")
def test_alpaca_settings_live():
    try:
        result = test_alpaca_runtime_settings()
        result["requested_mode"] = "live"
        return result
    except RuntimeSettingsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/runtime/auto-trading")
def get_auto_trading_status():
    """Get current auto-trading configuration status."""
    from backend.app.services.runtime_settings import get_auto_trading_config
    try:
        return get_auto_trading_config()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
