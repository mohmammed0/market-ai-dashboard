from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.engine import make_url
from sqlalchemy import select

from backend.app.core.logging_utils import get_logger, log_event
from backend.app.config import (
    ALPACA_ACCOUNT_REFRESH_SECONDS,
    AUTO_TRADING_ANALYSIS_LOOKBACK_DAYS,
    AUTO_TRADING_CYCLE_MINUTES,
    AUTO_TRADING_CYCLE_LEASE_SECONDS,
    AUTO_TRADING_DAILY_LOSS_AUTO_HALT,
    AUTO_TRADING_MIN_AGREEMENT,
    AUTO_TRADING_MIN_ENSEMBLE_SCORE,
    AUTO_TRADING_MIN_SIGNAL_CONFIDENCE,
    AUTO_TRADING_NOTIONAL_PER_TRADE,
    AUTO_TRADING_QUANTITY,
    AUTO_TRADING_STRATEGY_MODE,
    AUTO_TRADING_SYMBOL_LIMIT,
    AUTO_TRADING_TRADE_DIRECTION,
    AUTO_TRADING_UNIVERSE_PRESET,
    AUTO_TRADING_USE_FULL_PORTFOLIO,
    AUTO_TRADING_ALLOW_ADD_TO_EXISTING_LONGS,
    AUTO_TRADING_ADD_LONG_MIN_CONFIDENCE,
    AUTO_TRADING_ADD_LONG_MIN_SCORE,
    AUTO_TRADING_ADD_LONG_MAX_POSITION_PCT,
    AUTO_TRADING_ADD_LONG_MAX_ADDS_PER_SYMBOL_PER_DAY,
    AUTO_TRADING_ADD_LONG_COOLDOWN_MINUTES,
    AUTO_TRADING_ADD_LONG_MIN_NOTIONAL,
    AUTO_TRADING_ADD_LONG_MIN_SHARES,
    AUTO_TRADING_REGIME_ENABLED,
    AUTO_TRADING_OPPORTUNITY_MIN_SCORE,
    AUTO_TRADING_PORTFOLIO_MAX_NEW_POSITIONS,
    AUTO_TRADING_PORTFOLIO_CASH_RESERVE_PCT,
    AUTO_TRADING_PORTFOLIO_MAX_POSITION_PCT,
    AUTO_TRADING_PORTFOLIO_MAX_GROSS_EXPOSURE_PCT,
    AUTO_TRADING_PARTIAL_FUNDING_ENABLED,
    AUTO_TRADING_MIN_PARTIAL_FUNDING_NOTIONAL,
    AUTO_TRADING_MIN_PARTIAL_FUNDING_RATIO,
    AUTO_TRADING_PARTIAL_FUNDING_TOP_RANK_ONLY,
    AUTO_TRADING_REDUCE_ON_REGIME_DEFENSIVE,
    AUTO_TRADING_EXIT_ON_THESIS_BREAK,
    AUTO_TRADING_ADD_LONG_ENABLED,
    AUTO_TRADING_REDUCE_LONG_ENABLED,
    AUTO_TRADING_POSITION_BUILDER_ENABLED,
    AUTO_TRADING_EXECUTION_ORCHESTRATOR_ENABLED,
    AUTO_TRADING_EXECUTION_MAX_SUBMISSIONS_PER_CYCLE,
    AUTO_TRADING_EXECUTION_SUBMISSION_SPACING_SECONDS,
    AUTO_TRADING_EXECUTION_SYMBOL_COOLDOWN_SECONDS,
    AUTO_TRADING_EXECUTION_REQUIRE_RELEASE_BEFORE_ENTRIES,
    AUTO_TRADING_EXECUTION_RETRY_ENABLED,
    AUTO_TRADING_EXECUTION_RETRY_MAX_ATTEMPTS,
    AUTO_TRADING_EXECUTION_RETRY_INITIAL_BACKOFF_SECONDS,
    AUTO_TRADING_EXECUTION_RETRY_MAX_BACKOFF_SECONDS,
    AUTO_TRADING_EXECUTION_RETRY_BACKOFF_MULTIPLIER,
    AUTO_TRADING_EXECUTION_RETRY_JITTER_ENABLED,
    AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_BROKER_SUBMIT,
    AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_DEPENDENCY_WAIT,
    AUTO_TRADING_EXECUTION_RECONCILIATION_ENABLED,
    AUTO_TRADING_EXECUTION_RECONCILIATION_WINDOW_SECONDS,
    AUTO_TRADING_EXECUTION_RECONCILIATION_POLL_INTERVAL_SECONDS,
    AUTO_TRADING_EXECUTION_RECONCILIATION_MAX_POLLS,
    AUTO_TRADING_EXECUTION_RECONCILIATION_STOP_ON_TERMINAL,
    AUTO_TRADING_EXECUTION_RECONCILIATION_UPDATE_DEPENDENT_ACTIONS,
    AUTO_TRADING_MARKET_SESSION_INTELLIGENCE_ENABLED,
    AUTO_TRADING_PREOPEN_READINESS_ENABLED,
    AUTO_TRADING_PREOPEN_READINESS_START_MINUTES,
    AUTO_TRADING_PREOPEN_REFRESH_INTERVAL_SECONDS,
    AUTO_TRADING_PREMARKET_TRADING_ENABLED,
    AUTO_TRADING_QUEUED_FOR_OPEN_ENABLED,
    AUTO_TRADING_WAIT_FOR_OPEN_CONFIRMATION_ENABLED,
    AUTO_TRADING_CAPITAL_RESERVE_FOR_OPEN_PCT,
    AUTO_TRADING_MARKET_SESSION_EXTENDED_HOURS_ENABLED,
    AUTO_TRADING_KRONOS_ENABLED,
    AUTO_TRADING_KRONOS_MODEL_NAME,
    AUTO_TRADING_KRONOS_TOKENIZER_NAME,
    AUTO_TRADING_KRONOS_DEVICE_PREFERENCE,
    AUTO_TRADING_KRONOS_TIMEOUT_SECONDS,
    AUTO_TRADING_KRONOS_WARMUP_ENABLED,
    AUTH_DEFAULT_USERNAME,
    AUTO_TRADING_KRONOS_BATCH_PREOPEN_ENABLED,
    AUTO_TRADING_KRONOS_CACHE_TTL_SECONDS,
    AUTO_TRADING_KRONOS_WEIGHT,
    AUTO_TRADING_KRONOS_PREMARKET_WEIGHT,
    AUTO_TRADING_KRONOS_OPENING_WEIGHT,
    AUTO_TRADING_KRONOS_MAX_SYMBOLS_PER_BATCH,
    AUTO_TRADING_KRONOS_MIN_INPUT_QUALITY,
    AUTO_TRADING_KRONOS_PREDICTION_HORIZON,
    AUTO_TRADING_KRONOS_LOOKBACK_ROWS,
    AUTO_TRADING_KRONOS_INPUT_INTERVAL,
    DATABASE_URL,
)
from backend.app.models.runtime_settings import RuntimeSetting
from backend.app.services.cache import get_cache
from backend.app.services.storage import session_scope
from core.runtime_paths import SETTINGS_KEY_PATH, ensure_runtime_directories, sqlite_file_path

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - optional dependency at runtime
    Fernet = None
    InvalidToken = Exception


class RuntimeSettingsError(RuntimeError):
    pass


logger = get_logger(__name__)
_AUTO_TRADING_STRATEGY_MODES = {"classic", "ml", "dl", "ensemble"}
_AUTO_TRADING_TRADE_DIRECTIONS = {"both", "long_only", "short_only"}
_AUTO_TRADING_UNIVERSE_PRESETS = {
    "FOCUSED_SAMPLE",
    "NASDAQ",
    "NYSE",
    "ALL_US_EQUITIES",
    "ETF_ONLY",
    "TOP_500_MARKET_CAP",
}


@dataclass(frozen=True)
class SettingSpec:
    key: str
    env_name: str
    default: Any
    kind: str = "text"
    secret: bool = False


SETTING_SPECS: dict[str, SettingSpec] = {
    "auth.default_username": SettingSpec(
        "auth.default_username",
        "MARKET_AI_AUTH_DEFAULT_USERNAME",
        AUTH_DEFAULT_USERNAME,
    ),
    "auth.default_password_hash": SettingSpec(
        "auth.default_password_hash",
        "MARKET_AI_AUTH_DEFAULT_PASSWORD_HASH",
        "",
        secret=True,
    ),

    "broker.provider": SettingSpec("broker.provider", "MARKET_AI_BROKER_PROVIDER", "none"),
    "broker.trading_mode": SettingSpec(
        "broker.trading_mode",
        "MARKET_AI_BROKER_TRADING_MODE",
        "cash",
    ),
    "broker.order_submission_enabled": SettingSpec(
        "broker.order_submission_enabled",
        "MARKET_AI_BROKER_ORDER_SUBMISSION_ENABLED",
        False,
        kind="bool",
    ),
    "broker.live_execution_enabled": SettingSpec(
        "broker.live_execution_enabled",
        "MARKET_AI_BROKER_LIVE_EXECUTION_ENABLED",
        False,
        kind="bool",
    ),
    "alpaca.enabled": SettingSpec("alpaca.enabled", "MARKET_AI_ALPACA_ENABLED", False, kind="bool"),
    "alpaca.api_key": SettingSpec("alpaca.api_key", "ALPACA_API_KEY", "", secret=True),
    "alpaca.secret_key": SettingSpec("alpaca.secret_key", "ALPACA_SECRET_KEY", "", secret=True),
    "alpaca.paper": SettingSpec("alpaca.paper", "ALPACA_PAPER", True, kind="bool"),
    "alpaca.url_override": SettingSpec("alpaca.url_override", "ALPACA_URL_OVERRIDE", ""),
    "auto_trading.enabled": SettingSpec(
        "auto_trading.enabled",
        "MARKET_AI_AUTO_TRADING_ENABLED",
        False,
        kind="bool",
    ),
    "auto_trading.cycle_minutes": SettingSpec(
        "auto_trading.cycle_minutes",
        "MARKET_AI_AUTO_TRADING_CYCLE_MINUTES",
        AUTO_TRADING_CYCLE_MINUTES,
        kind="int",
    ),
    "auto_trading.strategy_mode": SettingSpec(
        "auto_trading.strategy_mode",
        "MARKET_AI_AUTO_TRADING_STRATEGY_MODE",
        AUTO_TRADING_STRATEGY_MODE,
    ),
    "auto_trading.trade_direction": SettingSpec(
        "auto_trading.trade_direction",
        "MARKET_AI_AUTO_TRADING_TRADE_DIRECTION",
        AUTO_TRADING_TRADE_DIRECTION,
    ),
    "auto_trading.universe_preset": SettingSpec(
        "auto_trading.universe_preset",
        "MARKET_AI_AUTO_TRADING_UNIVERSE_PRESET",
        AUTO_TRADING_UNIVERSE_PRESET,
    ),
    "auto_trading.symbol_limit": SettingSpec(
        "auto_trading.symbol_limit",
        "MARKET_AI_AUTO_TRADING_SYMBOL_LIMIT",
        AUTO_TRADING_SYMBOL_LIMIT,
        kind="int",
    ),
    "auto_trading.use_full_portfolio": SettingSpec(
        "auto_trading.use_full_portfolio",
        "MARKET_AI_AUTO_TRADING_USE_FULL_PORTFOLIO",
        AUTO_TRADING_USE_FULL_PORTFOLIO,
        kind="bool",
    ),
    "auto_trading.analysis_lookback_days": SettingSpec(
        "auto_trading.analysis_lookback_days",
        "MARKET_AI_AUTO_TRADING_ANALYSIS_LOOKBACK_DAYS",
        AUTO_TRADING_ANALYSIS_LOOKBACK_DAYS,
        kind="int",
    ),
    "auto_trading.notional_per_trade": SettingSpec(
        "auto_trading.notional_per_trade",
        "MARKET_AI_AUTO_TRADING_NOTIONAL_PER_TRADE",
        AUTO_TRADING_NOTIONAL_PER_TRADE,
        kind="float",
    ),
    "auto_trading.quantity": SettingSpec(
        "auto_trading.quantity",
        "MARKET_AI_AUTO_TRADING_QUANTITY",
        AUTO_TRADING_QUANTITY,
        kind="float",
    ),
    "auto_trading.min_signal_confidence": SettingSpec(
        "auto_trading.min_signal_confidence",
        "MARKET_AI_AUTO_TRADING_MIN_SIGNAL_CONFIDENCE",
        AUTO_TRADING_MIN_SIGNAL_CONFIDENCE,
        kind="float",
    ),
    "auto_trading.min_ensemble_score": SettingSpec(
        "auto_trading.min_ensemble_score",
        "MARKET_AI_AUTO_TRADING_MIN_ENSEMBLE_SCORE",
        AUTO_TRADING_MIN_ENSEMBLE_SCORE,
        kind="float",
    ),
    "auto_trading.min_agreement": SettingSpec(
        "auto_trading.min_agreement",
        "MARKET_AI_AUTO_TRADING_MIN_AGREEMENT",
        AUTO_TRADING_MIN_AGREEMENT,
        kind="float",
    ),
    "auto_trading.allow_add_to_existing_longs": SettingSpec(
        "auto_trading.allow_add_to_existing_longs",
        "MARKET_AI_AUTO_TRADING_ALLOW_ADD_TO_EXISTING_LONGS",
        AUTO_TRADING_ALLOW_ADD_TO_EXISTING_LONGS,
        kind="bool",
    ),
    "auto_trading.add_long_min_confidence": SettingSpec(
        "auto_trading.add_long_min_confidence",
        "MARKET_AI_AUTO_TRADING_ADD_LONG_MIN_CONFIDENCE",
        AUTO_TRADING_ADD_LONG_MIN_CONFIDENCE,
        kind="float",
    ),
    "auto_trading.add_long_min_score": SettingSpec(
        "auto_trading.add_long_min_score",
        "MARKET_AI_AUTO_TRADING_ADD_LONG_MIN_SCORE",
        AUTO_TRADING_ADD_LONG_MIN_SCORE,
        kind="float",
    ),
    "auto_trading.add_long_max_position_pct": SettingSpec(
        "auto_trading.add_long_max_position_pct",
        "MARKET_AI_AUTO_TRADING_ADD_LONG_MAX_POSITION_PCT",
        AUTO_TRADING_ADD_LONG_MAX_POSITION_PCT,
        kind="float",
    ),
    "auto_trading.add_long_max_adds_per_symbol_per_day": SettingSpec(
        "auto_trading.add_long_max_adds_per_symbol_per_day",
        "MARKET_AI_AUTO_TRADING_ADD_LONG_MAX_ADDS_PER_SYMBOL_PER_DAY",
        AUTO_TRADING_ADD_LONG_MAX_ADDS_PER_SYMBOL_PER_DAY,
        kind="int",
    ),
    "auto_trading.add_long_cooldown_minutes": SettingSpec(
        "auto_trading.add_long_cooldown_minutes",
        "MARKET_AI_AUTO_TRADING_ADD_LONG_COOLDOWN_MINUTES",
        AUTO_TRADING_ADD_LONG_COOLDOWN_MINUTES,
        kind="int",
    ),
    "auto_trading.add_long_min_notional": SettingSpec(
        "auto_trading.add_long_min_notional",
        "MARKET_AI_AUTO_TRADING_ADD_LONG_MIN_NOTIONAL",
        AUTO_TRADING_ADD_LONG_MIN_NOTIONAL,
        kind="float",
    ),
    "auto_trading.add_long_min_shares": SettingSpec(
        "auto_trading.add_long_min_shares",
        "MARKET_AI_AUTO_TRADING_ADD_LONG_MIN_SHARES",
        AUTO_TRADING_ADD_LONG_MIN_SHARES,
        kind="float",
    ),
    "auto_trading.regime_enabled": SettingSpec(
        "auto_trading.regime_enabled",
        "MARKET_AI_AUTO_TRADING_REGIME_ENABLED",
        AUTO_TRADING_REGIME_ENABLED,
        kind="bool",
    ),
    "auto_trading.opportunity_min_score": SettingSpec(
        "auto_trading.opportunity_min_score",
        "MARKET_AI_AUTO_TRADING_OPPORTUNITY_MIN_SCORE",
        AUTO_TRADING_OPPORTUNITY_MIN_SCORE,
        kind="float",
    ),
    "auto_trading.portfolio_max_new_positions": SettingSpec(
        "auto_trading.portfolio_max_new_positions",
        "MARKET_AI_AUTO_TRADING_PORTFOLIO_MAX_NEW_POSITIONS",
        AUTO_TRADING_PORTFOLIO_MAX_NEW_POSITIONS,
        kind="int",
    ),
    "auto_trading.portfolio_cash_reserve_pct": SettingSpec(
        "auto_trading.portfolio_cash_reserve_pct",
        "MARKET_AI_AUTO_TRADING_PORTFOLIO_CASH_RESERVE_PCT",
        AUTO_TRADING_PORTFOLIO_CASH_RESERVE_PCT,
        kind="float",
    ),
    "auto_trading.portfolio_max_position_pct": SettingSpec(
        "auto_trading.portfolio_max_position_pct",
        "MARKET_AI_AUTO_TRADING_PORTFOLIO_MAX_POSITION_PCT",
        AUTO_TRADING_PORTFOLIO_MAX_POSITION_PCT,
        kind="float",
    ),
    "auto_trading.portfolio_max_gross_exposure_pct": SettingSpec(
        "auto_trading.portfolio_max_gross_exposure_pct",
        "MARKET_AI_AUTO_TRADING_PORTFOLIO_MAX_GROSS_EXPOSURE_PCT",
        AUTO_TRADING_PORTFOLIO_MAX_GROSS_EXPOSURE_PCT,
        kind="float",
    ),
    "auto_trading.partial_funding_enabled": SettingSpec(
        "auto_trading.partial_funding_enabled",
        "MARKET_AI_AUTO_TRADING_PARTIAL_FUNDING_ENABLED",
        AUTO_TRADING_PARTIAL_FUNDING_ENABLED,
        kind="bool",
    ),
    "auto_trading.min_partial_funding_notional": SettingSpec(
        "auto_trading.min_partial_funding_notional",
        "MARKET_AI_AUTO_TRADING_MIN_PARTIAL_FUNDING_NOTIONAL",
        AUTO_TRADING_MIN_PARTIAL_FUNDING_NOTIONAL,
        kind="float",
    ),
    "auto_trading.min_partial_funding_ratio": SettingSpec(
        "auto_trading.min_partial_funding_ratio",
        "MARKET_AI_AUTO_TRADING_MIN_PARTIAL_FUNDING_RATIO",
        AUTO_TRADING_MIN_PARTIAL_FUNDING_RATIO,
        kind="float",
    ),
    "auto_trading.partial_funding_top_rank_only": SettingSpec(
        "auto_trading.partial_funding_top_rank_only",
        "MARKET_AI_AUTO_TRADING_PARTIAL_FUNDING_TOP_RANK_ONLY",
        AUTO_TRADING_PARTIAL_FUNDING_TOP_RANK_ONLY,
        kind="bool",
    ),
    "auto_trading.reduce_on_regime_defensive": SettingSpec(
        "auto_trading.reduce_on_regime_defensive",
        "MARKET_AI_AUTO_TRADING_REDUCE_ON_REGIME_DEFENSIVE",
        AUTO_TRADING_REDUCE_ON_REGIME_DEFENSIVE,
        kind="bool",
    ),
    "auto_trading.exit_on_thesis_break": SettingSpec(
        "auto_trading.exit_on_thesis_break",
        "MARKET_AI_AUTO_TRADING_EXIT_ON_THESIS_BREAK",
        AUTO_TRADING_EXIT_ON_THESIS_BREAK,
        kind="bool",
    ),
    "auto_trading.add_long_enabled": SettingSpec(
        "auto_trading.add_long_enabled",
        "MARKET_AI_AUTO_TRADING_ADD_LONG_ENABLED",
        AUTO_TRADING_ADD_LONG_ENABLED,
        kind="bool",
    ),
    "auto_trading.reduce_long_enabled": SettingSpec(
        "auto_trading.reduce_long_enabled",
        "MARKET_AI_AUTO_TRADING_REDUCE_LONG_ENABLED",
        AUTO_TRADING_REDUCE_LONG_ENABLED,
        kind="bool",
    ),
    "auto_trading.position_builder_enabled": SettingSpec(
        "auto_trading.position_builder_enabled",
        "MARKET_AI_AUTO_TRADING_POSITION_BUILDER_ENABLED",
        AUTO_TRADING_POSITION_BUILDER_ENABLED,
        kind="bool",
    ),
    "auto_trading.execution_orchestrator_enabled": SettingSpec(
        "auto_trading.execution_orchestrator_enabled",
        "MARKET_AI_AUTO_TRADING_EXECUTION_ORCHESTRATOR_ENABLED",
        AUTO_TRADING_EXECUTION_ORCHESTRATOR_ENABLED,
        kind="bool",
    ),
    "auto_trading.execution_max_submissions_per_cycle": SettingSpec(
        "auto_trading.execution_max_submissions_per_cycle",
        "MARKET_AI_AUTO_TRADING_EXECUTION_MAX_SUBMISSIONS_PER_CYCLE",
        AUTO_TRADING_EXECUTION_MAX_SUBMISSIONS_PER_CYCLE,
        kind="int",
    ),
    "auto_trading.execution_submission_spacing_seconds": SettingSpec(
        "auto_trading.execution_submission_spacing_seconds",
        "MARKET_AI_AUTO_TRADING_EXECUTION_SUBMISSION_SPACING_SECONDS",
        AUTO_TRADING_EXECUTION_SUBMISSION_SPACING_SECONDS,
        kind="int",
    ),
    "auto_trading.execution_symbol_cooldown_seconds": SettingSpec(
        "auto_trading.execution_symbol_cooldown_seconds",
        "MARKET_AI_AUTO_TRADING_EXECUTION_SYMBOL_COOLDOWN_SECONDS",
        AUTO_TRADING_EXECUTION_SYMBOL_COOLDOWN_SECONDS,
        kind="int",
    ),
    "auto_trading.execution_require_release_before_entries": SettingSpec(
        "auto_trading.execution_require_release_before_entries",
        "MARKET_AI_AUTO_TRADING_EXECUTION_REQUIRE_RELEASE_BEFORE_ENTRIES",
        AUTO_TRADING_EXECUTION_REQUIRE_RELEASE_BEFORE_ENTRIES,
        kind="bool",
    ),
    "auto_trading.execution_retry_enabled": SettingSpec(
        "auto_trading.execution_retry_enabled",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RETRY_ENABLED",
        AUTO_TRADING_EXECUTION_RETRY_ENABLED,
        kind="bool",
    ),
    "auto_trading.execution_retry_max_attempts": SettingSpec(
        "auto_trading.execution_retry_max_attempts",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RETRY_MAX_ATTEMPTS",
        AUTO_TRADING_EXECUTION_RETRY_MAX_ATTEMPTS,
        kind="int",
    ),
    "auto_trading.execution_retry_initial_backoff_seconds": SettingSpec(
        "auto_trading.execution_retry_initial_backoff_seconds",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RETRY_INITIAL_BACKOFF_SECONDS",
        AUTO_TRADING_EXECUTION_RETRY_INITIAL_BACKOFF_SECONDS,
        kind="int",
    ),
    "auto_trading.execution_retry_max_backoff_seconds": SettingSpec(
        "auto_trading.execution_retry_max_backoff_seconds",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RETRY_MAX_BACKOFF_SECONDS",
        AUTO_TRADING_EXECUTION_RETRY_MAX_BACKOFF_SECONDS,
        kind="int",
    ),
    "auto_trading.execution_retry_backoff_multiplier": SettingSpec(
        "auto_trading.execution_retry_backoff_multiplier",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RETRY_BACKOFF_MULTIPLIER",
        AUTO_TRADING_EXECUTION_RETRY_BACKOFF_MULTIPLIER,
        kind="float",
    ),
    "auto_trading.execution_retry_jitter_enabled": SettingSpec(
        "auto_trading.execution_retry_jitter_enabled",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RETRY_JITTER_ENABLED",
        AUTO_TRADING_EXECUTION_RETRY_JITTER_ENABLED,
        kind="bool",
    ),
    "auto_trading.execution_retry_allowed_for_broker_submit": SettingSpec(
        "auto_trading.execution_retry_allowed_for_broker_submit",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_BROKER_SUBMIT",
        AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_BROKER_SUBMIT,
        kind="bool",
    ),
    "auto_trading.execution_retry_allowed_for_dependency_wait": SettingSpec(
        "auto_trading.execution_retry_allowed_for_dependency_wait",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_DEPENDENCY_WAIT",
        AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_DEPENDENCY_WAIT,
        kind="bool",
    ),
    "auto_trading.execution_reconciliation_enabled": SettingSpec(
        "auto_trading.execution_reconciliation_enabled",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RECONCILIATION_ENABLED",
        AUTO_TRADING_EXECUTION_RECONCILIATION_ENABLED,
        kind="bool",
    ),
    "auto_trading.execution_reconciliation_window_seconds": SettingSpec(
        "auto_trading.execution_reconciliation_window_seconds",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RECONCILIATION_WINDOW_SECONDS",
        AUTO_TRADING_EXECUTION_RECONCILIATION_WINDOW_SECONDS,
        kind="int",
    ),
    "auto_trading.execution_reconciliation_poll_interval_seconds": SettingSpec(
        "auto_trading.execution_reconciliation_poll_interval_seconds",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RECONCILIATION_POLL_INTERVAL_SECONDS",
        AUTO_TRADING_EXECUTION_RECONCILIATION_POLL_INTERVAL_SECONDS,
        kind="int",
    ),
    "auto_trading.execution_reconciliation_max_polls": SettingSpec(
        "auto_trading.execution_reconciliation_max_polls",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RECONCILIATION_MAX_POLLS",
        AUTO_TRADING_EXECUTION_RECONCILIATION_MAX_POLLS,
        kind="int",
    ),
    "auto_trading.execution_reconciliation_stop_on_terminal": SettingSpec(
        "auto_trading.execution_reconciliation_stop_on_terminal",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RECONCILIATION_STOP_ON_TERMINAL",
        AUTO_TRADING_EXECUTION_RECONCILIATION_STOP_ON_TERMINAL,
        kind="bool",
    ),
    "auto_trading.execution_reconciliation_update_dependent_actions": SettingSpec(
        "auto_trading.execution_reconciliation_update_dependent_actions",
        "MARKET_AI_AUTO_TRADING_EXECUTION_RECONCILIATION_UPDATE_DEPENDENT_ACTIONS",
        AUTO_TRADING_EXECUTION_RECONCILIATION_UPDATE_DEPENDENT_ACTIONS,
        kind="bool",
    ),
    "auto_trading.rotation_cursor": SettingSpec(
        "auto_trading.rotation_cursor",
        "MARKET_AI_AUTO_TRADING_ROTATION_CURSOR",
        0,
        kind="int",
    ),
}

_ALPACA_API_VERSION_SEGMENTS = {"v1", "v2", "v2beta1"}
_ALPACA_TRADING_ENDPOINT_SEGMENTS = {
    "account",
    "orders",
    "positions",
    "clock",
    "calendar",
    "assets",
    "watchlists",
    "options",
    "corporate_actions",
}
_ALPACA_TRADING_HOSTS = {"api.alpaca.markets", "paper-api.alpaca.markets"}
_ALPACA_INVALID_TRADING_HOSTS = {
    "broker-api.alpaca.markets",
    "broker-api.sandbox.alpaca.markets",
    "data.alpaca.markets",
    "data.sandbox.alpaca.markets",
    "stream.data.alpaca.markets",
    "stream.data.sandbox.alpaca.markets",
}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    return text not in {"0", "false", "no", "off"}


def _coerce_text(value: Any, default: str = "") -> str:
    if value is None:
        return str(default)
    text = str(value).strip()
    return text or str(default)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _normalize_trading_mode(value: Any) -> str:
    normalized = _coerce_text(value, default="cash").lower()
    return "margin" if normalized == "margin" else "cash"


def _normalize_auto_trading_strategy_mode(value: Any) -> str:
    normalized = _coerce_text(value, default=AUTO_TRADING_STRATEGY_MODE).lower()
    return normalized if normalized in _AUTO_TRADING_STRATEGY_MODES else AUTO_TRADING_STRATEGY_MODE


def _normalize_auto_trading_trade_direction(value: Any) -> str:
    normalized = _coerce_text(value, default=AUTO_TRADING_TRADE_DIRECTION).lower()
    return normalized if normalized in _AUTO_TRADING_TRADE_DIRECTIONS else AUTO_TRADING_TRADE_DIRECTION


def _normalize_auto_trading_universe_preset(value: Any) -> str:
    normalized = _coerce_text(value, default=AUTO_TRADING_UNIVERSE_PRESET).upper().replace(" ", "_")
    aliases = {
        "FOCUSED": "FOCUSED_SAMPLE",
        "SAMPLE": "FOCUSED_SAMPLE",
        "ETF": "ETF_ONLY",
        "ETFS": "ETF_ONLY",
        "TOP500": "TOP_500_MARKET_CAP",
        "TOP_500": "TOP_500_MARKET_CAP",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _AUTO_TRADING_UNIVERSE_PRESETS else AUTO_TRADING_UNIVERSE_PRESET


def _normalize_alpaca_url_override(value: Any) -> str:
    text = _coerce_text(value, default="")
    if not text:
        return ""

    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    if scheme not in {"http", "https"} or not host or host in _ALPACA_INVALID_TRADING_HOSTS:
        return ""

    segments = [segment for segment in parsed.path.split("/") if segment]
    lower_segments = [segment.lower() for segment in segments]
    cut_index = None

    for index, segment in enumerate(lower_segments):
        if segment in _ALPACA_API_VERSION_SEGMENTS:
            cut_index = index
            break

    if cut_index is None and host in _ALPACA_TRADING_HOSTS:
        for index, segment in enumerate(lower_segments):
            if segment in _ALPACA_TRADING_ENDPOINT_SEGMENTS:
                cut_index = index
                break

    if cut_index is not None:
        segments = segments[:cut_index]

    normalized_path = "/" + "/".join(segments) if segments else ""
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path.rstrip("/"), "", ""))


def _serialize_value(spec: SettingSpec, value: Any) -> str:
    if spec.kind == "bool":
        return "1" if _coerce_bool(value, default=bool(spec.default)) else "0"
    if spec.kind == "int":
        return str(_coerce_int(value, int(spec.default)))
    if spec.kind == "float":
        return str(_coerce_float(value, float(spec.default)))
    return _coerce_text(value, default=str(spec.default))


def _deserialize_value(spec: SettingSpec, value: str | None) -> Any:
    if spec.kind == "bool":
        return _coerce_bool(value, default=bool(spec.default))
    if spec.kind == "int":
        return _coerce_int(str(value).strip() if value is not None else None, int(spec.default))
    if spec.kind == "float":
        return _coerce_float(str(value).strip() if value is not None else None, float(spec.default))
    return _coerce_text(value, default=str(spec.default))


def _secret_mask(value: str | None) -> str | None:
    text = _coerce_text(value, default="")
    if not text:
        return None
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def _redact_text(message: str, secrets: list[str | None]) -> str:
    result = str(message or "").strip()
    for secret in secrets:
        text = _coerce_text(secret, default="")
        if text:
            result = result.replace(text, "***")
    return result


def _describe_database_runtime(database_url: str) -> dict[str, Any]:
    sqlite_path = sqlite_file_path(database_url)
    payload: dict[str, Any] = {
        "driver": None,
        "database_name": None,
        "host": None,
        "port": None,
        "path": None if sqlite_path is None else str(sqlite_path),
        "credentials_present": False,
    }
    try:
        parsed = make_url(database_url)
    except Exception:
        return payload

    payload["driver"] = parsed.drivername
    payload["database_name"] = parsed.database
    payload["host"] = parsed.host
    payload["port"] = parsed.port
    payload["credentials_present"] = bool(parsed.username or parsed.password)
    return payload


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    if Fernet is None:
        raise RuntimeSettingsError("cryptography is not installed in the backend environment.")
    ensure_runtime_directories()
    key_path = Path(SETTINGS_KEY_PATH)
    if key_path.exists():
        key = key_path.read_bytes().strip()
    else:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        try:
            key_path.chmod(0o600)
        except Exception:
            pass
    return Fernet(key)


def _encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_secret(value: str | None) -> str:
    text = _coerce_text(value, default="")
    if not text:
        return ""
    try:
        return _fernet().decrypt(text.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeSettingsError("Stored runtime secret could not be decrypted.") from exc


def _records_by_key() -> dict[str, dict[str, Any]]:
    try:
        with session_scope() as session:
            rows = session.execute(
                select(RuntimeSetting.key, RuntimeSetting.value_text, RuntimeSetting.is_secret)
            ).all()
            return {
                row.key: {
                    "value_text": row.value_text,
                    "is_secret": bool(row.is_secret),
                }
                for row in rows
            }
    except Exception:
        return {}


def _resolve_setting(key: str, records: dict[str, dict[str, Any]] | None = None) -> tuple[Any, str]:
    spec = SETTING_SPECS[key]
    rows = records if records is not None else _records_by_key()
    record = rows.get(key)
    if record and record.get("value_text") is not None:
        raw_value = _decrypt_secret(record.get("value_text")) if spec.secret else record.get("value_text")
        return _deserialize_value(spec, raw_value), "ui_managed"
    if spec.env_name in os.environ:
        return _deserialize_value(spec, os.environ.get(spec.env_name)), "environment"
    return spec.default, "default"


def _sdk_installed(package: str) -> bool:
    try:
        __import__(package)
        return True
    except Exception:
        return False


def _build_broker_payload(records: dict[str, dict[str, Any]] | None = None, *, include_secrets: bool = False) -> dict:
    provider, provider_source = _resolve_setting("broker.provider", records)
    trading_mode, trading_mode_source = _resolve_setting("broker.trading_mode", records)
    order_submission_enabled, order_submission_source = _resolve_setting("broker.order_submission_enabled", records)
    live_execution_enabled, live_execution_source = _resolve_setting("broker.live_execution_enabled", records)
    alpaca_enabled, alpaca_enabled_source = _resolve_setting("alpaca.enabled", records)
    alpaca_api_key, alpaca_api_key_source = _resolve_setting("alpaca.api_key", records)
    alpaca_secret_key, alpaca_secret_key_source = _resolve_setting("alpaca.secret_key", records)
    alpaca_paper, alpaca_paper_source = _resolve_setting("alpaca.paper", records)
    alpaca_url_override, alpaca_url_override_source = _resolve_setting("alpaca.url_override", records)
    alpaca_url_override = _normalize_alpaca_url_override(alpaca_url_override)

    alpaca_sdk_installed = _sdk_installed("alpaca")
    alpaca_configured = bool(alpaca_api_key and alpaca_secret_key)
    provider_name = _coerce_text(provider, default="none").lower()
    normalized_trading_mode = _normalize_trading_mode(trading_mode)

    if provider_name != "alpaca":
        detail = "Broker integration is disabled."
        status = "disabled"
    elif not alpaca_enabled:
        detail = "Alpaca integration is disabled."
        status = "standby"
    elif not alpaca_sdk_installed:
        detail = "alpaca-py is not installed in the backend environment."
        status = "error"
    elif not alpaca_configured:
        detail = "Alpaca API credentials are not configured."
        status = "warning"
    else:
        detail = "Alpaca credentials are configured."
        status = "ready"

    auto_trading_enabled, auto_trading_source = _resolve_setting("auto_trading.enabled", records)
    auto_trading_cycle_minutes, auto_trading_cycle_source = _resolve_setting("auto_trading.cycle_minutes", records)
    return {
        "provider": provider_name,
        "provider_source": provider_source,
        "trading_mode": normalized_trading_mode,
        "trading_mode_source": trading_mode_source,
        "margin_enabled": normalized_trading_mode == "margin",
        "order_submission_enabled": bool(order_submission_enabled),
        "order_submission_source": order_submission_source,
        "live_execution_enabled": bool(live_execution_enabled),
        "live_execution_source": live_execution_source,
        "auto_trading_enabled": bool(auto_trading_enabled),
        "auto_trading_source": auto_trading_source,
        "auto_trading_cycle_minutes": int(auto_trading_cycle_minutes),
        "auto_trading_cycle_source": auto_trading_cycle_source,
        "alpaca": {
            "enabled": bool(alpaca_enabled),
            "enabled_source": alpaca_enabled_source,
            "configured": alpaca_configured,
            "api_key": _coerce_text(alpaca_api_key, default="") if include_secrets else None,
            "api_key_masked": _secret_mask(alpaca_api_key),
            "api_key_source": alpaca_api_key_source,
            "secret_key": _coerce_text(alpaca_secret_key, default="") if include_secrets else None,
            "secret_key_masked": _secret_mask(alpaca_secret_key),
            "secret_key_source": alpaca_secret_key_source,
            "paper": bool(alpaca_paper),
            "paper_source": alpaca_paper_source,
            "url_override": _coerce_text(alpaca_url_override, default=""),
            "url_override_source": alpaca_url_override_source,
            "sdk_installed": alpaca_sdk_installed,
            "status": status,
            "detail": detail,
            "account_refresh_seconds": ALPACA_ACCOUNT_REFRESH_SECONDS,
        },
    }


def get_runtime_settings_overview() -> dict:
    records = _records_by_key()
    database = _describe_database_runtime(DATABASE_URL)
    return {
        "database": database,
        "database_path": database.get("path"),
        "credentials_precedence": ["ui_managed", "environment", "default"],
        "key_store_path": str(SETTINGS_KEY_PATH),
        "broker": _build_broker_payload(records, include_secrets=False),
        "auto_trading": get_auto_trading_config(),
    }


def get_broker_runtime_config() -> dict:
    payload = _build_broker_payload(include_secrets=True)
    alpaca = payload["alpaca"]
    return {
        "provider": payload["provider"],
        "provider_source": payload["provider_source"],
        "trading_mode": payload["trading_mode"],
        "trading_mode_source": payload["trading_mode_source"],
        "margin_enabled": payload["margin_enabled"],
        "order_submission_enabled": payload["order_submission_enabled"],
        "order_submission_source": payload["order_submission_source"],
        "live_execution_enabled": payload["live_execution_enabled"],
        "live_execution_source": payload["live_execution_source"],
        "alpaca": {
            "enabled": alpaca["enabled"],
            "configured": alpaca["configured"],
            "api_key": alpaca["api_key"],
            "secret_key": alpaca["secret_key"],
            "paper": alpaca["paper"],
            "url_override": alpaca["url_override"],
            "sdk_installed": alpaca["sdk_installed"],
            "detail": alpaca["detail"],
        },
    }


def get_alpaca_runtime_config() -> dict:
    payload = get_broker_runtime_config()
    return {
        **payload["alpaca"],
        "provider": payload["provider"],
        "trading_mode": payload["trading_mode"],
        "margin_enabled": payload["margin_enabled"],
        "order_submission_enabled": payload["order_submission_enabled"],
        "live_execution_enabled": payload["live_execution_enabled"],
    }


def get_broker_guardrails() -> dict:
    payload = get_broker_runtime_config()
    return {
        "trading_mode": payload["trading_mode"],
        "margin_enabled": payload["margin_enabled"],
        "order_submission_enabled": payload["order_submission_enabled"],
        "live_execution_enabled": payload["live_execution_enabled"],
    }


def _upsert_setting(session, key: str, value: Any, *, secret: bool = False, delete_when_blank: bool = False) -> None:
    row = session.execute(select(RuntimeSetting).where(RuntimeSetting.key == key)).scalar_one_or_none()
    text_value = _coerce_text(value, default="")
    if delete_when_blank and not text_value:
        if row is not None:
            session.delete(row)
        return

    stored_value = _encrypt_secret(text_value) if secret and text_value else text_value
    if row is None:
        session.add(RuntimeSetting(key=key, value_text=stored_value, is_secret=secret))
        return
    row.value_text = stored_value
    row.is_secret = secret


def _delete_setting(session, key: str) -> None:
    row = session.execute(select(RuntimeSetting).where(RuntimeSetting.key == key)).scalar_one_or_none()
    if row is not None:
        session.delete(row)


def invalidate_runtime_caches() -> None:
    cache = get_cache()
    if hasattr(cache, "delete_prefix"):
        cache.delete_prefix("broker:alpaca:")


def get_runtime_setting_value(key: str) -> Any:
    if key not in SETTING_SPECS:
        raise RuntimeSettingsError(f"Unsupported runtime setting: {key}")
    value, _ = _resolve_setting(key)
    return value


def set_runtime_setting_value(key: str, value: Any) -> Any:
    spec = SETTING_SPECS.get(key)
    if spec is None:
        raise RuntimeSettingsError(f"Unsupported runtime setting: {key}")
    with session_scope() as session:
        _upsert_setting(session, key, value, secret=spec.secret, delete_when_blank=(spec.kind == "text"))
    return get_runtime_setting_value(key)


def save_alpaca_runtime_settings(
    *,
    enabled: bool,
    provider: str,
    paper: bool,
    trading_mode: str | None = None,
    api_key: str | None = None,
    secret_key: str | None = None,
    clear_api_key: bool = False,
    clear_secret_key: bool = False,
    url_override: str | None = None,
    auto_trading_enabled: bool | None = None,
    order_submission_enabled: bool | None = None,
    auto_trading_cycle_minutes: int | None = None,
    auto_trading_strategy_mode: str | None = None,
    auto_trading_trade_direction: str | None = None,
    auto_trading_universe_preset: str | None = None,
    auto_trading_symbol_limit: int | None = None,
    auto_trading_use_full_portfolio: bool | None = None,
    auto_trading_analysis_lookback_days: int | None = None,
    auto_trading_notional_per_trade: float | None = None,
    auto_trading_quantity: float | None = None,
    auto_trading_min_signal_confidence: float | None = None,
    auto_trading_min_ensemble_score: float | None = None,
    auto_trading_min_agreement: float | None = None,
    auto_trading_allow_add_to_existing_longs: bool | None = None,
    auto_trading_add_long_min_confidence: float | None = None,
    auto_trading_add_long_min_score: float | None = None,
    auto_trading_add_long_max_position_pct: float | None = None,
    auto_trading_add_long_max_adds_per_symbol_per_day: int | None = None,
    auto_trading_add_long_cooldown_minutes: int | None = None,
    auto_trading_add_long_min_notional: float | None = None,
    auto_trading_add_long_min_shares: float | None = None,
    auto_trading_regime_enabled: bool | None = None,
    auto_trading_opportunity_min_score: float | None = None,
    auto_trading_portfolio_max_new_positions: int | None = None,
    auto_trading_portfolio_cash_reserve_pct: float | None = None,
    auto_trading_portfolio_max_position_pct: float | None = None,
    auto_trading_portfolio_max_gross_exposure_pct: float | None = None,
    auto_trading_partial_funding_enabled: bool | None = None,
    auto_trading_min_partial_funding_notional: float | None = None,
    auto_trading_min_partial_funding_ratio: float | None = None,
    auto_trading_partial_funding_top_rank_only: bool | None = None,
    auto_trading_reduce_on_regime_defensive: bool | None = None,
    auto_trading_exit_on_thesis_break: bool | None = None,
    auto_trading_add_long_enabled: bool | None = None,
    auto_trading_reduce_long_enabled: bool | None = None,
    auto_trading_position_builder_enabled: bool | None = None,
    auto_trading_execution_orchestrator_enabled: bool | None = None,
    auto_trading_execution_max_submissions_per_cycle: int | None = None,
    auto_trading_execution_submission_spacing_seconds: int | None = None,
    auto_trading_execution_symbol_cooldown_seconds: int | None = None,
    auto_trading_execution_require_release_before_entries: bool | None = None,
    auto_trading_execution_retry_enabled: bool | None = None,
    auto_trading_execution_retry_max_attempts: int | None = None,
    auto_trading_execution_retry_initial_backoff_seconds: int | None = None,
    auto_trading_execution_retry_max_backoff_seconds: int | None = None,
    auto_trading_execution_retry_backoff_multiplier: float | None = None,
    auto_trading_execution_retry_jitter_enabled: bool | None = None,
    auto_trading_execution_retry_allowed_for_broker_submit: bool | None = None,
    auto_trading_execution_retry_allowed_for_dependency_wait: bool | None = None,
    auto_trading_execution_reconciliation_enabled: bool | None = None,
    auto_trading_execution_reconciliation_window_seconds: int | None = None,
    auto_trading_execution_reconciliation_poll_interval_seconds: int | None = None,
    auto_trading_execution_reconciliation_max_polls: int | None = None,
    auto_trading_execution_reconciliation_stop_on_terminal: bool | None = None,
    auto_trading_execution_reconciliation_update_dependent_actions: bool | None = None,
) -> dict:
    clean_provider = _coerce_text(provider, default="alpaca").lower()
    if clean_provider not in {"alpaca", "none"}:
        clean_provider = "alpaca"
    clean_trading_mode = _normalize_trading_mode(trading_mode)
    clean_url_override = _normalize_alpaca_url_override(url_override)
    clean_strategy_mode = _normalize_auto_trading_strategy_mode(auto_trading_strategy_mode)
    clean_trade_direction = _normalize_auto_trading_trade_direction(auto_trading_trade_direction)
    clean_universe_preset = _normalize_auto_trading_universe_preset(auto_trading_universe_preset)
    with session_scope() as session:
        _upsert_setting(session, "broker.provider", clean_provider)
        _upsert_setting(session, "broker.trading_mode", clean_trading_mode)
        _upsert_setting(session, "alpaca.enabled", enabled)
        _upsert_setting(session, "alpaca.paper", paper)
        if clear_api_key:
            _delete_setting(session, "alpaca.api_key")
        elif api_key is not None and str(api_key).strip():
            _upsert_setting(session, "alpaca.api_key", str(api_key).strip(), secret=True)
        if clear_secret_key:
            _delete_setting(session, "alpaca.secret_key")
        elif secret_key is not None and str(secret_key).strip():
            _upsert_setting(session, "alpaca.secret_key", str(secret_key).strip(), secret=True)
        if url_override is not None:
            _upsert_setting(session, "alpaca.url_override", clean_url_override, delete_when_blank=True)
        if auto_trading_enabled is not None:
            _upsert_setting(session, "auto_trading.enabled", auto_trading_enabled)
        if auto_trading_cycle_minutes is not None:
            _upsert_setting(session, "auto_trading.cycle_minutes", max(1, min(int(auto_trading_cycle_minutes), 720)))
        if auto_trading_strategy_mode is not None:
            _upsert_setting(session, "auto_trading.strategy_mode", clean_strategy_mode)
        if auto_trading_trade_direction is not None:
            _upsert_setting(session, "auto_trading.trade_direction", clean_trade_direction)
        if auto_trading_universe_preset is not None:
            _upsert_setting(session, "auto_trading.universe_preset", clean_universe_preset)
        if auto_trading_symbol_limit is not None:
            _upsert_setting(session, "auto_trading.symbol_limit", max(1, min(int(auto_trading_symbol_limit), 500)))
        if auto_trading_use_full_portfolio is not None:
            _upsert_setting(session, "auto_trading.use_full_portfolio", auto_trading_use_full_portfolio)
        if auto_trading_analysis_lookback_days is not None:
            _upsert_setting(session, "auto_trading.analysis_lookback_days", max(0, min(int(auto_trading_analysis_lookback_days), 3650)))
        if auto_trading_notional_per_trade is not None:
            _upsert_setting(session, "auto_trading.notional_per_trade", max(float(auto_trading_notional_per_trade), 0.0))
        if auto_trading_quantity is not None:
            _upsert_setting(session, "auto_trading.quantity", max(float(auto_trading_quantity), 0.0))
        if auto_trading_min_signal_confidence is not None:
            _upsert_setting(session, "auto_trading.min_signal_confidence", max(0.0, min(float(auto_trading_min_signal_confidence), 100.0)))
        if auto_trading_min_ensemble_score is not None:
            _upsert_setting(session, "auto_trading.min_ensemble_score", max(0.0, min(float(auto_trading_min_ensemble_score), 1.0)))
        if auto_trading_min_agreement is not None:
            _upsert_setting(session, "auto_trading.min_agreement", max(0.0, min(float(auto_trading_min_agreement), 1.0)))
        if auto_trading_allow_add_to_existing_longs is not None:
            _upsert_setting(session, "auto_trading.allow_add_to_existing_longs", bool(auto_trading_allow_add_to_existing_longs))
        if auto_trading_add_long_min_confidence is not None:
            _upsert_setting(session, "auto_trading.add_long_min_confidence", max(0.0, min(float(auto_trading_add_long_min_confidence), 100.0)))
        if auto_trading_add_long_min_score is not None:
            _upsert_setting(session, "auto_trading.add_long_min_score", max(0.0, min(float(auto_trading_add_long_min_score), 1.0)))
        if auto_trading_add_long_max_position_pct is not None:
            _upsert_setting(session, "auto_trading.add_long_max_position_pct", max(0.0, min(float(auto_trading_add_long_max_position_pct), 100.0)))
        if auto_trading_add_long_max_adds_per_symbol_per_day is not None:
            _upsert_setting(session, "auto_trading.add_long_max_adds_per_symbol_per_day", max(0, min(int(auto_trading_add_long_max_adds_per_symbol_per_day), 50)))
        if auto_trading_add_long_cooldown_minutes is not None:
            _upsert_setting(session, "auto_trading.add_long_cooldown_minutes", max(0, min(int(auto_trading_add_long_cooldown_minutes), 1440)))
        if auto_trading_add_long_min_notional is not None:
            _upsert_setting(session, "auto_trading.add_long_min_notional", max(float(auto_trading_add_long_min_notional), 0.0))
        if auto_trading_add_long_min_shares is not None:
            _upsert_setting(session, "auto_trading.add_long_min_shares", max(float(auto_trading_add_long_min_shares), 0.0))
        if auto_trading_regime_enabled is not None:
            _upsert_setting(session, "auto_trading.regime_enabled", bool(auto_trading_regime_enabled))
        if auto_trading_opportunity_min_score is not None:
            _upsert_setting(session, "auto_trading.opportunity_min_score", max(0.0, min(float(auto_trading_opportunity_min_score), 100.0)))
        if auto_trading_portfolio_max_new_positions is not None:
            _upsert_setting(session, "auto_trading.portfolio_max_new_positions", max(0, min(int(auto_trading_portfolio_max_new_positions), 20)))
        if auto_trading_portfolio_cash_reserve_pct is not None:
            _upsert_setting(session, "auto_trading.portfolio_cash_reserve_pct", max(0.0, min(float(auto_trading_portfolio_cash_reserve_pct), 95.0)))
        if auto_trading_portfolio_max_position_pct is not None:
            _upsert_setting(session, "auto_trading.portfolio_max_position_pct", max(0.0, min(float(auto_trading_portfolio_max_position_pct), 100.0)))
        if auto_trading_portfolio_max_gross_exposure_pct is not None:
            _upsert_setting(session, "auto_trading.portfolio_max_gross_exposure_pct", max(0.0, min(float(auto_trading_portfolio_max_gross_exposure_pct), 100.0)))
        if auto_trading_partial_funding_enabled is not None:
            _upsert_setting(session, "auto_trading.partial_funding_enabled", bool(auto_trading_partial_funding_enabled))
        if auto_trading_min_partial_funding_notional is not None:
            _upsert_setting(session, "auto_trading.min_partial_funding_notional", max(float(auto_trading_min_partial_funding_notional), 0.0))
        if auto_trading_min_partial_funding_ratio is not None:
            _upsert_setting(session, "auto_trading.min_partial_funding_ratio", max(0.0, min(float(auto_trading_min_partial_funding_ratio), 1.0)))
        if auto_trading_partial_funding_top_rank_only is not None:
            _upsert_setting(session, "auto_trading.partial_funding_top_rank_only", bool(auto_trading_partial_funding_top_rank_only))
        if auto_trading_reduce_on_regime_defensive is not None:
            _upsert_setting(session, "auto_trading.reduce_on_regime_defensive", bool(auto_trading_reduce_on_regime_defensive))
        if auto_trading_exit_on_thesis_break is not None:
            _upsert_setting(session, "auto_trading.exit_on_thesis_break", bool(auto_trading_exit_on_thesis_break))
        if auto_trading_add_long_enabled is not None:
            _upsert_setting(session, "auto_trading.add_long_enabled", bool(auto_trading_add_long_enabled))
        if auto_trading_reduce_long_enabled is not None:
            _upsert_setting(session, "auto_trading.reduce_long_enabled", bool(auto_trading_reduce_long_enabled))
        if auto_trading_position_builder_enabled is not None:
            _upsert_setting(session, "auto_trading.position_builder_enabled", bool(auto_trading_position_builder_enabled))
        if auto_trading_execution_orchestrator_enabled is not None:
            _upsert_setting(session, "auto_trading.execution_orchestrator_enabled", bool(auto_trading_execution_orchestrator_enabled))
        if auto_trading_execution_max_submissions_per_cycle is not None:
            _upsert_setting(session, "auto_trading.execution_max_submissions_per_cycle", max(1, min(int(auto_trading_execution_max_submissions_per_cycle), 50)))
        if auto_trading_execution_submission_spacing_seconds is not None:
            _upsert_setting(session, "auto_trading.execution_submission_spacing_seconds", max(0, min(int(auto_trading_execution_submission_spacing_seconds), 120)))
        if auto_trading_execution_symbol_cooldown_seconds is not None:
            _upsert_setting(session, "auto_trading.execution_symbol_cooldown_seconds", max(0, min(int(auto_trading_execution_symbol_cooldown_seconds), 3600)))
        if auto_trading_execution_require_release_before_entries is not None:
            _upsert_setting(session, "auto_trading.execution_require_release_before_entries", bool(auto_trading_execution_require_release_before_entries))
        if auto_trading_execution_retry_enabled is not None:
            _upsert_setting(session, "auto_trading.execution_retry_enabled", bool(auto_trading_execution_retry_enabled))
        if auto_trading_execution_retry_max_attempts is not None:
            _upsert_setting(session, "auto_trading.execution_retry_max_attempts", max(1, min(int(auto_trading_execution_retry_max_attempts), 6)))
        if auto_trading_execution_retry_initial_backoff_seconds is not None:
            _upsert_setting(session, "auto_trading.execution_retry_initial_backoff_seconds", max(1, min(int(auto_trading_execution_retry_initial_backoff_seconds), 120)))
        if auto_trading_execution_retry_max_backoff_seconds is not None:
            _upsert_setting(session, "auto_trading.execution_retry_max_backoff_seconds", max(1, min(int(auto_trading_execution_retry_max_backoff_seconds), 900)))
        if auto_trading_execution_retry_backoff_multiplier is not None:
            _upsert_setting(session, "auto_trading.execution_retry_backoff_multiplier", max(1.0, min(float(auto_trading_execution_retry_backoff_multiplier), 6.0)))
        if auto_trading_execution_retry_jitter_enabled is not None:
            _upsert_setting(session, "auto_trading.execution_retry_jitter_enabled", bool(auto_trading_execution_retry_jitter_enabled))
        if auto_trading_execution_retry_allowed_for_broker_submit is not None:
            _upsert_setting(session, "auto_trading.execution_retry_allowed_for_broker_submit", bool(auto_trading_execution_retry_allowed_for_broker_submit))
        if auto_trading_execution_retry_allowed_for_dependency_wait is not None:
            _upsert_setting(session, "auto_trading.execution_retry_allowed_for_dependency_wait", bool(auto_trading_execution_retry_allowed_for_dependency_wait))
        if auto_trading_execution_reconciliation_enabled is not None:
            _upsert_setting(session, "auto_trading.execution_reconciliation_enabled", bool(auto_trading_execution_reconciliation_enabled))
        if auto_trading_execution_reconciliation_window_seconds is not None:
            _upsert_setting(session, "auto_trading.execution_reconciliation_window_seconds", max(5, min(int(auto_trading_execution_reconciliation_window_seconds), 300)))
        if auto_trading_execution_reconciliation_poll_interval_seconds is not None:
            _upsert_setting(session, "auto_trading.execution_reconciliation_poll_interval_seconds", max(1, min(int(auto_trading_execution_reconciliation_poll_interval_seconds), 60)))
        if auto_trading_execution_reconciliation_max_polls is not None:
            _upsert_setting(session, "auto_trading.execution_reconciliation_max_polls", max(1, min(int(auto_trading_execution_reconciliation_max_polls), 120)))
        if auto_trading_execution_reconciliation_stop_on_terminal is not None:
            _upsert_setting(session, "auto_trading.execution_reconciliation_stop_on_terminal", bool(auto_trading_execution_reconciliation_stop_on_terminal))
        if auto_trading_execution_reconciliation_update_dependent_actions is not None:
            _upsert_setting(session, "auto_trading.execution_reconciliation_update_dependent_actions", bool(auto_trading_execution_reconciliation_update_dependent_actions))
        if order_submission_enabled is not None:
            _upsert_setting(session, "broker.order_submission_enabled", order_submission_enabled)
    invalidate_runtime_caches()
    try:
        from backend.app.services.scheduler_runtime import sync_auto_trading_schedule

        sync_auto_trading_schedule()
    except Exception:
        pass
    full_overview = get_runtime_settings_overview()
    overview = full_overview.get("broker", {})
    auto_trading_overview = full_overview.get("auto_trading", {})
    alpaca_overview = overview.get("alpaca", {}) if isinstance(overview, dict) else {}
    log_event(
        logger,
        logging.INFO,
        "runtime_settings.alpaca.saved",
        provider=overview.get("provider"),
        trading_mode=overview.get("trading_mode"),
        enabled=alpaca_overview.get("enabled"),
        paper=alpaca_overview.get("paper"),
        api_key_updated=bool(api_key),
        secret_key_updated=bool(secret_key),
        api_key_cleared=bool(clear_api_key),
        secret_key_cleared=bool(clear_secret_key),
        auto_trading_cycle_minutes=overview.get("auto_trading_cycle_minutes"),
        auto_trading_strategy_mode=auto_trading_overview.get("strategy_mode"),
        auto_trading_trade_direction=auto_trading_overview.get("trade_direction"),
    )
    return overview


def test_alpaca_runtime_settings(*, paper_override: bool | None = None) -> dict:
    payload = get_alpaca_runtime_config()
    if paper_override is not None:
        payload = {**payload, "paper": bool(paper_override)}
    mode = "paper" if payload["paper"] else "live"
    secrets = [payload["api_key"], payload["secret_key"]]
    if payload["provider"] != "alpaca":
        result = {"ok": False, "detail": "Broker provider is disabled.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="provider_disabled", mode=mode)
        return result
    if not payload["enabled"]:
        result = {"ok": False, "detail": "Alpaca integration is disabled.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="disabled", mode=mode)
        return result
    if not payload["configured"]:
        result = {"ok": False, "detail": "Alpaca API credentials are not configured.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="missing_keys", mode=mode)
        return result
    if not payload["sdk_installed"]:
        result = {"ok": False, "detail": "alpaca-py is not installed.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="sdk_missing", mode=mode)
        return result

    try:
        from alpaca.trading.client import TradingClient
    except Exception:
        result = {"ok": False, "detail": "alpaca-py is not installed.", "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="sdk_missing", mode=mode)
        return result

    try:
        kwargs = {"paper": payload["paper"]}
        if payload["url_override"]:
            kwargs["url_override"] = payload["url_override"]
        client = TradingClient(payload["api_key"], payload["secret_key"], **kwargs)
        account = client.get_account()
        result = {
            "ok": True,
            "detail": f"Connected to Alpaca {mode} account.",
            "mode": mode,
            "account_id": str(getattr(account, "id", "") or ""),
            "account_status": str(getattr(account, "status", "") or ""),
        }
        log_event(logger, logging.INFO, "runtime_settings.alpaca.test", ok=True, mode=mode, account_status=result["account_status"])
        return result
    except Exception as exc:  # pragma: no cover - external service
        detail = _redact_text(str(exc) or "Alpaca connection test failed.", secrets)
        result = {"ok": False, "detail": detail, "mode": mode}
        log_event(logger, logging.WARNING, "runtime_settings.alpaca.test", ok=False, reason="connection_failed", mode=mode, detail=detail)
        return result


def get_auto_trading_config() -> dict:
    """Get auto-trading configuration from runtime settings."""
    auto_enabled, auto_source = _resolve_setting("auto_trading.enabled")
    cycle_minutes, cycle_source = _resolve_setting("auto_trading.cycle_minutes")
    strategy_mode, strategy_mode_source = _resolve_setting("auto_trading.strategy_mode")
    trade_direction, trade_direction_source = _resolve_setting("auto_trading.trade_direction")
    universe_preset, universe_preset_source = _resolve_setting("auto_trading.universe_preset")
    symbol_limit, symbol_limit_source = _resolve_setting("auto_trading.symbol_limit")
    use_full_portfolio, use_full_portfolio_source = _resolve_setting("auto_trading.use_full_portfolio")
    analysis_lookback_days, analysis_lookback_days_source = _resolve_setting("auto_trading.analysis_lookback_days")
    notional_per_trade, notional_per_trade_source = _resolve_setting("auto_trading.notional_per_trade")
    quantity, quantity_source = _resolve_setting("auto_trading.quantity")
    min_signal_confidence, min_signal_confidence_source = _resolve_setting("auto_trading.min_signal_confidence")
    min_ensemble_score, min_ensemble_score_source = _resolve_setting("auto_trading.min_ensemble_score")
    min_agreement, min_agreement_source = _resolve_setting("auto_trading.min_agreement")
    allow_add_to_existing_longs, allow_add_to_existing_longs_source = _resolve_setting("auto_trading.allow_add_to_existing_longs")
    add_long_min_confidence, add_long_min_confidence_source = _resolve_setting("auto_trading.add_long_min_confidence")
    add_long_min_score, add_long_min_score_source = _resolve_setting("auto_trading.add_long_min_score")
    add_long_max_position_pct, add_long_max_position_pct_source = _resolve_setting("auto_trading.add_long_max_position_pct")
    add_long_max_adds_per_symbol_per_day, add_long_max_adds_per_symbol_per_day_source = _resolve_setting("auto_trading.add_long_max_adds_per_symbol_per_day")
    add_long_cooldown_minutes, add_long_cooldown_minutes_source = _resolve_setting("auto_trading.add_long_cooldown_minutes")
    add_long_min_notional, add_long_min_notional_source = _resolve_setting("auto_trading.add_long_min_notional")
    add_long_min_shares, add_long_min_shares_source = _resolve_setting("auto_trading.add_long_min_shares")
    regime_enabled, regime_enabled_source = _resolve_setting("auto_trading.regime_enabled")
    opportunity_min_score, opportunity_min_score_source = _resolve_setting("auto_trading.opportunity_min_score")
    portfolio_max_new_positions, portfolio_max_new_positions_source = _resolve_setting("auto_trading.portfolio_max_new_positions")
    portfolio_cash_reserve_pct, portfolio_cash_reserve_pct_source = _resolve_setting("auto_trading.portfolio_cash_reserve_pct")
    portfolio_max_position_pct, portfolio_max_position_pct_source = _resolve_setting("auto_trading.portfolio_max_position_pct")
    portfolio_max_gross_exposure_pct, portfolio_max_gross_exposure_pct_source = _resolve_setting("auto_trading.portfolio_max_gross_exposure_pct")
    partial_funding_enabled, partial_funding_enabled_source = _resolve_setting("auto_trading.partial_funding_enabled")
    min_partial_funding_notional, min_partial_funding_notional_source = _resolve_setting("auto_trading.min_partial_funding_notional")
    min_partial_funding_ratio, min_partial_funding_ratio_source = _resolve_setting("auto_trading.min_partial_funding_ratio")
    partial_funding_top_rank_only, partial_funding_top_rank_only_source = _resolve_setting("auto_trading.partial_funding_top_rank_only")
    reduce_on_regime_defensive, reduce_on_regime_defensive_source = _resolve_setting("auto_trading.reduce_on_regime_defensive")
    exit_on_thesis_break, exit_on_thesis_break_source = _resolve_setting("auto_trading.exit_on_thesis_break")
    add_long_enabled, add_long_enabled_source = _resolve_setting("auto_trading.add_long_enabled")
    reduce_long_enabled, reduce_long_enabled_source = _resolve_setting("auto_trading.reduce_long_enabled")
    position_builder_enabled, position_builder_enabled_source = _resolve_setting("auto_trading.position_builder_enabled")
    execution_orchestrator_enabled, execution_orchestrator_enabled_source = _resolve_setting("auto_trading.execution_orchestrator_enabled")
    execution_max_submissions_per_cycle, execution_max_submissions_per_cycle_source = _resolve_setting("auto_trading.execution_max_submissions_per_cycle")
    execution_submission_spacing_seconds, execution_submission_spacing_seconds_source = _resolve_setting("auto_trading.execution_submission_spacing_seconds")
    execution_symbol_cooldown_seconds, execution_symbol_cooldown_seconds_source = _resolve_setting("auto_trading.execution_symbol_cooldown_seconds")
    execution_require_release_before_entries, execution_require_release_before_entries_source = _resolve_setting("auto_trading.execution_require_release_before_entries")
    execution_retry_enabled, execution_retry_enabled_source = _resolve_setting("auto_trading.execution_retry_enabled")
    execution_retry_max_attempts, execution_retry_max_attempts_source = _resolve_setting("auto_trading.execution_retry_max_attempts")
    execution_retry_initial_backoff_seconds, execution_retry_initial_backoff_seconds_source = _resolve_setting("auto_trading.execution_retry_initial_backoff_seconds")
    execution_retry_max_backoff_seconds, execution_retry_max_backoff_seconds_source = _resolve_setting("auto_trading.execution_retry_max_backoff_seconds")
    execution_retry_backoff_multiplier, execution_retry_backoff_multiplier_source = _resolve_setting("auto_trading.execution_retry_backoff_multiplier")
    execution_retry_jitter_enabled, execution_retry_jitter_enabled_source = _resolve_setting("auto_trading.execution_retry_jitter_enabled")
    execution_retry_allowed_for_broker_submit, execution_retry_allowed_for_broker_submit_source = _resolve_setting("auto_trading.execution_retry_allowed_for_broker_submit")
    execution_retry_allowed_for_dependency_wait, execution_retry_allowed_for_dependency_wait_source = _resolve_setting("auto_trading.execution_retry_allowed_for_dependency_wait")
    execution_reconciliation_enabled, execution_reconciliation_enabled_source = _resolve_setting("auto_trading.execution_reconciliation_enabled")
    execution_reconciliation_window_seconds, execution_reconciliation_window_seconds_source = _resolve_setting("auto_trading.execution_reconciliation_window_seconds")
    execution_reconciliation_poll_interval_seconds, execution_reconciliation_poll_interval_seconds_source = _resolve_setting("auto_trading.execution_reconciliation_poll_interval_seconds")
    execution_reconciliation_max_polls, execution_reconciliation_max_polls_source = _resolve_setting("auto_trading.execution_reconciliation_max_polls")
    execution_reconciliation_stop_on_terminal, execution_reconciliation_stop_on_terminal_source = _resolve_setting("auto_trading.execution_reconciliation_stop_on_terminal")
    execution_reconciliation_update_dependent_actions, execution_reconciliation_update_dependent_actions_source = _resolve_setting("auto_trading.execution_reconciliation_update_dependent_actions")
    order_sub, order_sub_source = _resolve_setting("broker.order_submission_enabled")
    alpaca_config = get_alpaca_runtime_config()
    return {
        "auto_trading_enabled": bool(auto_enabled),
        "auto_trading_source": auto_source,
        "cycle_minutes": int(cycle_minutes),
        "cycle_minutes_source": cycle_source,
        "cycle_lease_seconds": int(AUTO_TRADING_CYCLE_LEASE_SECONDS),
        "strategy_mode": _normalize_auto_trading_strategy_mode(strategy_mode),
        "strategy_mode_source": strategy_mode_source,
        "trade_direction": _normalize_auto_trading_trade_direction(trade_direction),
        "trade_direction_source": trade_direction_source,
        "universe_preset": _normalize_auto_trading_universe_preset(universe_preset),
        "universe_preset_source": universe_preset_source,
        "symbol_limit": max(_coerce_int(symbol_limit, AUTO_TRADING_SYMBOL_LIMIT), 1),
        "symbol_limit_source": symbol_limit_source,
        "use_full_portfolio": bool(use_full_portfolio),
        "use_full_portfolio_source": use_full_portfolio_source,
        "analysis_lookback_days": max(_coerce_int(analysis_lookback_days, AUTO_TRADING_ANALYSIS_LOOKBACK_DAYS), 0),
        "analysis_lookback_days_source": analysis_lookback_days_source,
        "notional_per_trade": max(_coerce_float(notional_per_trade, AUTO_TRADING_NOTIONAL_PER_TRADE), 0.0),
        "notional_per_trade_source": notional_per_trade_source,
        "quantity": max(_coerce_float(quantity, AUTO_TRADING_QUANTITY), 0.0),
        "quantity_source": quantity_source,
        "min_signal_confidence": max(_coerce_float(min_signal_confidence, AUTO_TRADING_MIN_SIGNAL_CONFIDENCE), 0.0),
        "min_signal_confidence_source": min_signal_confidence_source,
        "min_ensemble_score": max(_coerce_float(min_ensemble_score, AUTO_TRADING_MIN_ENSEMBLE_SCORE), 0.0),
        "min_ensemble_score_source": min_ensemble_score_source,
        "min_agreement": max(_coerce_float(min_agreement, AUTO_TRADING_MIN_AGREEMENT), 0.0),
        "min_agreement_source": min_agreement_source,
        "allow_add_to_existing_longs": bool(allow_add_to_existing_longs),
        "allow_add_to_existing_longs_source": allow_add_to_existing_longs_source,
        "add_long_min_confidence": max(_coerce_float(add_long_min_confidence, AUTO_TRADING_ADD_LONG_MIN_CONFIDENCE), 0.0),
        "add_long_min_confidence_source": add_long_min_confidence_source,
        "add_long_min_score": max(_coerce_float(add_long_min_score, AUTO_TRADING_ADD_LONG_MIN_SCORE), 0.0),
        "add_long_min_score_source": add_long_min_score_source,
        "add_long_max_position_pct": max(_coerce_float(add_long_max_position_pct, AUTO_TRADING_ADD_LONG_MAX_POSITION_PCT), 0.0),
        "add_long_max_position_pct_source": add_long_max_position_pct_source,
        "add_long_max_adds_per_symbol_per_day": max(_coerce_int(add_long_max_adds_per_symbol_per_day, AUTO_TRADING_ADD_LONG_MAX_ADDS_PER_SYMBOL_PER_DAY), 0),
        "add_long_max_adds_per_symbol_per_day_source": add_long_max_adds_per_symbol_per_day_source,
        "add_long_cooldown_minutes": max(_coerce_int(add_long_cooldown_minutes, AUTO_TRADING_ADD_LONG_COOLDOWN_MINUTES), 0),
        "add_long_cooldown_minutes_source": add_long_cooldown_minutes_source,
        "add_long_min_notional": max(_coerce_float(add_long_min_notional, AUTO_TRADING_ADD_LONG_MIN_NOTIONAL), 0.0),
        "add_long_min_notional_source": add_long_min_notional_source,
        "add_long_min_shares": max(_coerce_float(add_long_min_shares, AUTO_TRADING_ADD_LONG_MIN_SHARES), 0.0),
        "add_long_min_shares_source": add_long_min_shares_source,
        "regime_enabled": bool(regime_enabled),
        "regime_enabled_source": regime_enabled_source,
        "opportunity_min_score": max(_coerce_float(opportunity_min_score, AUTO_TRADING_OPPORTUNITY_MIN_SCORE), 0.0),
        "opportunity_min_score_source": opportunity_min_score_source,
        "portfolio_max_new_positions": max(_coerce_int(portfolio_max_new_positions, AUTO_TRADING_PORTFOLIO_MAX_NEW_POSITIONS), 0),
        "portfolio_max_new_positions_source": portfolio_max_new_positions_source,
        "portfolio_cash_reserve_pct": max(_coerce_float(portfolio_cash_reserve_pct, AUTO_TRADING_PORTFOLIO_CASH_RESERVE_PCT), 0.0),
        "portfolio_cash_reserve_pct_source": portfolio_cash_reserve_pct_source,
        "portfolio_max_position_pct": max(_coerce_float(portfolio_max_position_pct, AUTO_TRADING_PORTFOLIO_MAX_POSITION_PCT), 0.0),
        "portfolio_max_position_pct_source": portfolio_max_position_pct_source,
        "portfolio_max_gross_exposure_pct": max(_coerce_float(portfolio_max_gross_exposure_pct, AUTO_TRADING_PORTFOLIO_MAX_GROSS_EXPOSURE_PCT), 0.0),
        "portfolio_max_gross_exposure_pct_source": portfolio_max_gross_exposure_pct_source,
        "partial_funding_enabled": bool(partial_funding_enabled),
        "partial_funding_enabled_source": partial_funding_enabled_source,
        "min_partial_funding_notional": max(_coerce_float(min_partial_funding_notional, AUTO_TRADING_MIN_PARTIAL_FUNDING_NOTIONAL), 0.0),
        "min_partial_funding_notional_source": min_partial_funding_notional_source,
        "min_partial_funding_ratio": min(max(_coerce_float(min_partial_funding_ratio, AUTO_TRADING_MIN_PARTIAL_FUNDING_RATIO), 0.0), 1.0),
        "min_partial_funding_ratio_source": min_partial_funding_ratio_source,
        "partial_funding_top_rank_only": bool(partial_funding_top_rank_only),
        "partial_funding_top_rank_only_source": partial_funding_top_rank_only_source,
        "reduce_on_regime_defensive": bool(reduce_on_regime_defensive),
        "reduce_on_regime_defensive_source": reduce_on_regime_defensive_source,
        "exit_on_thesis_break": bool(exit_on_thesis_break),
        "exit_on_thesis_break_source": exit_on_thesis_break_source,
        "add_long_enabled": bool(add_long_enabled),
        "add_long_enabled_source": add_long_enabled_source,
        "reduce_long_enabled": bool(reduce_long_enabled),
        "reduce_long_enabled_source": reduce_long_enabled_source,
        "position_builder_enabled": bool(position_builder_enabled),
        "position_builder_enabled_source": position_builder_enabled_source,
        "execution_orchestrator_enabled": bool(execution_orchestrator_enabled),
        "execution_orchestrator_enabled_source": execution_orchestrator_enabled_source,
        "execution_max_submissions_per_cycle": max(_coerce_int(execution_max_submissions_per_cycle, AUTO_TRADING_EXECUTION_MAX_SUBMISSIONS_PER_CYCLE), 1),
        "execution_max_submissions_per_cycle_source": execution_max_submissions_per_cycle_source,
        "execution_submission_spacing_seconds": max(_coerce_int(execution_submission_spacing_seconds, AUTO_TRADING_EXECUTION_SUBMISSION_SPACING_SECONDS), 0),
        "execution_submission_spacing_seconds_source": execution_submission_spacing_seconds_source,
        "execution_symbol_cooldown_seconds": max(_coerce_int(execution_symbol_cooldown_seconds, AUTO_TRADING_EXECUTION_SYMBOL_COOLDOWN_SECONDS), 0),
        "execution_symbol_cooldown_seconds_source": execution_symbol_cooldown_seconds_source,
        "execution_require_release_before_entries": bool(execution_require_release_before_entries),
        "execution_require_release_before_entries_source": execution_require_release_before_entries_source,
        "execution_retry_enabled": bool(execution_retry_enabled),
        "execution_retry_enabled_source": execution_retry_enabled_source,
        "execution_retry_max_attempts": max(_coerce_int(execution_retry_max_attempts, AUTO_TRADING_EXECUTION_RETRY_MAX_ATTEMPTS), 1),
        "execution_retry_max_attempts_source": execution_retry_max_attempts_source,
        "execution_retry_initial_backoff_seconds": max(_coerce_int(execution_retry_initial_backoff_seconds, AUTO_TRADING_EXECUTION_RETRY_INITIAL_BACKOFF_SECONDS), 1),
        "execution_retry_initial_backoff_seconds_source": execution_retry_initial_backoff_seconds_source,
        "execution_retry_max_backoff_seconds": max(_coerce_int(execution_retry_max_backoff_seconds, AUTO_TRADING_EXECUTION_RETRY_MAX_BACKOFF_SECONDS), 1),
        "execution_retry_max_backoff_seconds_source": execution_retry_max_backoff_seconds_source,
        "execution_retry_backoff_multiplier": max(_coerce_float(execution_retry_backoff_multiplier, AUTO_TRADING_EXECUTION_RETRY_BACKOFF_MULTIPLIER), 1.0),
        "execution_retry_backoff_multiplier_source": execution_retry_backoff_multiplier_source,
        "execution_retry_jitter_enabled": bool(execution_retry_jitter_enabled),
        "execution_retry_jitter_enabled_source": execution_retry_jitter_enabled_source,
        "execution_retry_allowed_for_broker_submit": bool(execution_retry_allowed_for_broker_submit),
        "execution_retry_allowed_for_broker_submit_source": execution_retry_allowed_for_broker_submit_source,
        "execution_retry_allowed_for_dependency_wait": bool(execution_retry_allowed_for_dependency_wait),
        "execution_retry_allowed_for_dependency_wait_source": execution_retry_allowed_for_dependency_wait_source,
        "execution_reconciliation_enabled": bool(execution_reconciliation_enabled),
        "execution_reconciliation_enabled_source": execution_reconciliation_enabled_source,
        "execution_reconciliation_window_seconds": max(_coerce_int(execution_reconciliation_window_seconds, AUTO_TRADING_EXECUTION_RECONCILIATION_WINDOW_SECONDS), 5),
        "execution_reconciliation_window_seconds_source": execution_reconciliation_window_seconds_source,
        "execution_reconciliation_poll_interval_seconds": max(_coerce_int(execution_reconciliation_poll_interval_seconds, AUTO_TRADING_EXECUTION_RECONCILIATION_POLL_INTERVAL_SECONDS), 1),
        "execution_reconciliation_poll_interval_seconds_source": execution_reconciliation_poll_interval_seconds_source,
        "execution_reconciliation_max_polls": max(_coerce_int(execution_reconciliation_max_polls, AUTO_TRADING_EXECUTION_RECONCILIATION_MAX_POLLS), 1),
        "execution_reconciliation_max_polls_source": execution_reconciliation_max_polls_source,
        "execution_reconciliation_stop_on_terminal": bool(execution_reconciliation_stop_on_terminal),
        "execution_reconciliation_stop_on_terminal_source": execution_reconciliation_stop_on_terminal_source,
        "execution_reconciliation_update_dependent_actions": bool(execution_reconciliation_update_dependent_actions),
        "execution_reconciliation_update_dependent_actions_source": execution_reconciliation_update_dependent_actions_source,
        "market_session_intelligence_enabled": bool(AUTO_TRADING_MARKET_SESSION_INTELLIGENCE_ENABLED),
        "market_session_intelligence_enabled_source": "env",
        "preopen_readiness_enabled": bool(AUTO_TRADING_PREOPEN_READINESS_ENABLED),
        "preopen_readiness_enabled_source": "env",
        "preopen_readiness_start_minutes": int(AUTO_TRADING_PREOPEN_READINESS_START_MINUTES),
        "preopen_readiness_start_minutes_source": "env",
        "preopen_refresh_interval_seconds": int(AUTO_TRADING_PREOPEN_REFRESH_INTERVAL_SECONDS),
        "preopen_refresh_interval_seconds_source": "env",
        "premarket_trading_enabled": bool(AUTO_TRADING_PREMARKET_TRADING_ENABLED),
        "premarket_trading_enabled_source": "env",
        "queued_for_open_enabled": bool(AUTO_TRADING_QUEUED_FOR_OPEN_ENABLED),
        "queued_for_open_enabled_source": "env",
        "wait_for_open_confirmation_enabled": bool(AUTO_TRADING_WAIT_FOR_OPEN_CONFIRMATION_ENABLED),
        "wait_for_open_confirmation_enabled_source": "env",
        "capital_reserve_for_open_pct": max(float(AUTO_TRADING_CAPITAL_RESERVE_FOR_OPEN_PCT), 0.0),
        "capital_reserve_for_open_pct_source": "env",
        "market_session_extended_hours_enabled": bool(AUTO_TRADING_MARKET_SESSION_EXTENDED_HOURS_ENABLED),
        "market_session_extended_hours_enabled_source": "env",
        "kronos_enabled": bool(AUTO_TRADING_KRONOS_ENABLED),
        "kronos_enabled_source": "env",
        "kronos_model_name": str(AUTO_TRADING_KRONOS_MODEL_NAME),
        "kronos_model_name_source": "env",
        "kronos_tokenizer_name": str(AUTO_TRADING_KRONOS_TOKENIZER_NAME),
        "kronos_tokenizer_name_source": "env",
        "kronos_device_preference": str(AUTO_TRADING_KRONOS_DEVICE_PREFERENCE),
        "kronos_device_preference_source": "env",
        "kronos_timeout_seconds": int(AUTO_TRADING_KRONOS_TIMEOUT_SECONDS),
        "kronos_timeout_seconds_source": "env",
        "kronos_warmup_enabled": bool(AUTO_TRADING_KRONOS_WARMUP_ENABLED),
        "kronos_warmup_enabled_source": "env",
        "kronos_batch_preopen_enabled": bool(AUTO_TRADING_KRONOS_BATCH_PREOPEN_ENABLED),
        "kronos_batch_preopen_enabled_source": "env",
        "kronos_cache_ttl_seconds": int(AUTO_TRADING_KRONOS_CACHE_TTL_SECONDS),
        "kronos_cache_ttl_seconds_source": "env",
        "kronos_weight": max(float(AUTO_TRADING_KRONOS_WEIGHT), 0.0),
        "kronos_weight_source": "env",
        "kronos_premarket_weight": max(float(AUTO_TRADING_KRONOS_PREMARKET_WEIGHT), 0.0),
        "kronos_premarket_weight_source": "env",
        "kronos_opening_weight": max(float(AUTO_TRADING_KRONOS_OPENING_WEIGHT), 0.0),
        "kronos_opening_weight_source": "env",
        "kronos_max_symbols_per_batch": max(int(AUTO_TRADING_KRONOS_MAX_SYMBOLS_PER_BATCH), 1),
        "kronos_max_symbols_per_batch_source": "env",
        "kronos_min_input_quality": max(float(AUTO_TRADING_KRONOS_MIN_INPUT_QUALITY), 0.0),
        "kronos_min_input_quality_source": "env",
        "kronos_prediction_horizon": max(int(AUTO_TRADING_KRONOS_PREDICTION_HORIZON), 2),
        "kronos_prediction_horizon_source": "env",
        "kronos_lookback_rows": max(int(AUTO_TRADING_KRONOS_LOOKBACK_ROWS), 80),
        "kronos_lookback_rows_source": "env",
        "kronos_input_interval": str(AUTO_TRADING_KRONOS_INPUT_INTERVAL),
        "kronos_input_interval_source": "env",
        "daily_loss_auto_halt_enabled": bool(AUTO_TRADING_DAILY_LOSS_AUTO_HALT),
        "trading_mode": alpaca_config.get("trading_mode", "cash"),
        "margin_enabled": alpaca_config.get("margin_enabled", False),
        "order_submission_enabled": bool(order_sub),
        "order_submission_source": order_sub_source,
        "alpaca_enabled": alpaca_config.get("enabled", False),
        "alpaca_configured": alpaca_config.get("configured", False),
        "alpaca_paper": alpaca_config.get("paper", True),
        "ready": bool(auto_enabled) and bool(order_sub) and alpaca_config.get("enabled", False) and alpaca_config.get("configured", False),
    }


def is_auto_trading_enabled() -> bool:
    """Quick check: is auto-trading fully enabled and configured?"""
    config = get_auto_trading_config()
    return config["ready"]
