from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import threading
import time
from uuid import uuid4
import logging
import os
import random

from backend.app.application.broker.service import get_broker_summary
from backend.app.config import (
    AUTO_TRADING_ADD_LONG_COOLDOWN_MINUTES,
    AUTO_TRADING_ADD_LONG_MAX_ADDS_PER_SYMBOL_PER_DAY,
    AUTO_TRADING_ADD_LONG_MAX_POSITION_PCT,
    AUTO_TRADING_ADD_LONG_MIN_CONFIDENCE,
    AUTO_TRADING_ADD_LONG_MIN_NOTIONAL,
    AUTO_TRADING_ADD_LONG_MIN_SCORE,
    AUTO_TRADING_ADD_LONG_MIN_SHARES,
    AUTO_TRADING_ALLOW_ADD_TO_EXISTING_LONGS,
    LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
)
from backend.app.core.date_defaults import analysis_window_iso
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.domain.alerts.contracts import AlertRecord
from backend.app.domain.execution.contracts import (
    ExecutionCommand,
    ExecutionEventRecord,
    PaperOrderRecord,
    PositionState,
    SignalRecord,
    SignalSnapshot,
    TradeIntent,
    TradeRecord,
)
from backend.app.domain.platform.contracts import ExecutionConfirmResult, ExecutionPreview
from backend.app.domain.execution.services.order_state_machine import transition_execution_status
from backend.app.events.publisher import publish_event
from backend.app.observability.metrics import emit_counter
from backend.app.observability.tracing import build_trace_context
from backend.app.models import PaperTrade
from backend.app.risk.service import assess_execution_guardrails
from backend.app.repositories.execution import ExecutionRepository
from backend.app.repositories.platform_events import PlatformEventRepository
from backend.app.services.execution_halt import is_halted, get_halt_status
from backend.app.services.market_data import fetch_quote_snapshots
from backend.app.services.auto_trade_policy import (
    is_auto_executable_signal as _policy_is_auto_executable_signal,
    resolve_auto_trade_gate_config as _policy_resolve_auto_trade_gate_config,
)
from backend.app.services.paper_fill_engine import compute_fill
from backend.app.services.runtime_settings import get_auto_trading_config, get_broker_guardrails
from backend.app.services.signal_runtime import build_smart_analysis, extract_signal_view
from backend.app.services.storage import session_scope
from packages.contracts.events.topics import (
    EXECUTION_FILL_RECEIVED,
    EXECUTION_ORDER_ACKNOWLEDGED,
    EXECUTION_ORDER_CANCELED,
    EXECUTION_ORDER_INTENT_CREATED,
    EXECUTION_ORDER_SUBMITTED,
    PORTFOLIO_SNAPSHOT_UPDATED,
    RISK_SIGNAL_ACCEPTED,
    RISK_SIGNAL_REJECTED,
    STRATEGY_SIGNAL_PROPOSED,
)
from packages.contracts.enums import ExecutionStatus

def _is_us_equities_market_open() -> bool:
    try:
        from zoneinfo import ZoneInfo
    except ImportError:  # pragma: no cover
        from backports.zoneinfo import ZoneInfo

    now_dt = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))
    if now_dt.weekday() >= 5:
        return False
    market_open = now_dt.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_dt.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_dt <= market_close


# Broker integration for live order submission
_RETRYABLE_BROKER_ERROR_MARKERS = {
    "timeout",
    "timed out",
    "temporary",
    "temporarily",
    "try again",
    "unavailable",
    "connection",
    "network",
    "rate limit",
    "too many requests",
    "429",
    "502",
    "503",
    "504",
}

_PERMANENT_BROKER_ERROR_MARKERS = {
    "insufficient",
    "invalid",
    "forbidden",
    "unauthorized",
    "rejected",
    "notional",
    "buying power",
    "duplicate",
}

_NON_RETRY_SKIP_REASONS = {
    "broker_not_ready",
}


def _retry_classification_from_payload(payload: dict | None) -> tuple[bool, str | None, bool]:
    body = payload if isinstance(payload, dict) else {}
    reason = str(
        body.get("reason")
        or body.get("error")
        or body.get("message")
        or body.get("detail")
        or ""
    ).strip()
    lowered = reason.lower()
    skip_reason = str(body.get("reason") or "").strip().lower()
    if skip_reason in _NON_RETRY_SKIP_REASONS:
        return False, "non_retry_skip_reason", True
    if lowered and any(marker in lowered for marker in _PERMANENT_BROKER_ERROR_MARKERS):
        return False, "permanent_failure", True
    if lowered and any(marker in lowered for marker in _RETRYABLE_BROKER_ERROR_MARKERS):
        return True, "transient_broker_error", False
    status = str(body.get("status") or "").strip().lower()
    if status in {"error", "failed"} and not body.get("ok"):
        return True, "temporary_submit_failure", False
    return False, None, False


def _compute_retry_backoff_seconds(*, attempt: int, initial_seconds: int, max_seconds: int, multiplier: float) -> int:
    exponent = max(int(attempt) - 1, 0)
    value = float(initial_seconds) * (float(multiplier) ** exponent)
    return max(1, min(int(round(value)), int(max_seconds)))


def _submit_to_broker(symbol: str, qty: float, side: str, order_type: str = "market", estimated_price: float | None = None) -> dict | None:
    """Submit order to broker (Alpaca) with conservative retry/backoff for transient failures."""
    try:
        from backend.app.adapters.broker.base import BrokerOrderIntent
        from backend.app.domain.execution.services.broker_router import route_execution_intent
        from backend.app.services.runtime_settings import get_auto_trading_config

        config = get_auto_trading_config()
        retry_enabled = bool(config.get("execution_retry_enabled", True))
        retry_max_attempts = max(int(config.get("execution_retry_max_attempts", 2) or 2), 1)
        retry_initial_backoff_seconds = max(int(config.get("execution_retry_initial_backoff_seconds", 2) or 2), 1)
        retry_max_backoff_seconds = max(int(config.get("execution_retry_max_backoff_seconds", 20) or 20), 1)
        retry_backoff_multiplier = max(float(config.get("execution_retry_backoff_multiplier", 2.0) or 2.0), 1.0)
        retry_jitter_enabled = bool(config.get("execution_retry_jitter_enabled", True))
        retry_allowed_for_submit = bool(config.get("execution_retry_allowed_for_broker_submit", True))

        attempted_at = datetime.utcnow().isoformat()
        base_payload = {
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "retry_enabled": retry_enabled,
            "retry_max_attempts": retry_max_attempts,
            "retry_backoff_strategy": "exponential_jitter" if retry_jitter_enabled else "exponential",
            "broker_submission_attempted_at": attempted_at,
            "broker_submit_attempt_count": 0,
            "retry_attempt_count": 0,
            "retry_eligible": False,
            "retry_reason": None,
            "retry_exhausted": False,
            "permanent_failure": False,
            "backoff_seconds": 0,
            "retry_next_attempt_at": None,
            "last_submit_error": None,
        }

        if not config.get("ready", False):
            return {
                **base_payload,
                "ok": False,
                "skipped": True,
                "reason": "broker_not_ready",
                "permanent_failure": True,
            }

        last_result: dict | None = None
        current_attempt = 0
        allowed_attempts = retry_max_attempts if (retry_enabled and retry_allowed_for_submit) else 1

        while current_attempt < allowed_attempts:
            current_attempt += 1
            try:
                result = route_execution_intent(
                    BrokerOrderIntent(
                        symbol=symbol,
                        qty=qty,
                        side=side,
                        order_type=order_type,
                    ),
                    broker="alpaca",
                ) or {}
            except Exception as exc:
                result = {"ok": False, "status": "error", "error": str(exc), "reason": "submit_exception"}

            result = dict(result)
            result.setdefault("symbol", symbol)
            result.setdefault("qty", qty)
            result.setdefault("side", side)
            result["broker_submit_attempt_count"] = current_attempt
            result["retry_attempt_count"] = max(current_attempt - 1, 0)
            result["broker_submission_attempted_at"] = attempted_at
            result["retry_max_attempts"] = allowed_attempts
            result["retry_backoff_strategy"] = base_payload["retry_backoff_strategy"]

            ok = bool(result.get("ok")) or str(result.get("status") or "").strip().lower() not in {"", "error", "failed"}
            if ok:
                result["retry_eligible"] = False
                result["retry_reason"] = None
                result["retry_exhausted"] = False
                result["permanent_failure"] = False
                result["backoff_seconds"] = 0
                result["retry_next_attempt_at"] = None
                # Send Telegram notification
                _notify_trade(symbol, qty, side, result.get("order", {}))
                return result

            retry_eligible, retry_reason, permanent_failure = _retry_classification_from_payload(result)
            result["retry_eligible"] = bool(retry_enabled and retry_allowed_for_submit and retry_eligible and not permanent_failure)
            result["retry_reason"] = retry_reason
            result["permanent_failure"] = bool(permanent_failure)
            result["last_submit_error"] = str(
                result.get("error")
                or result.get("reason")
                or result.get("message")
                or "broker_submit_failed"
            )

            last_result = result

            if not result["retry_eligible"] or current_attempt >= allowed_attempts:
                result["retry_exhausted"] = bool(result["retry_eligible"] and current_attempt >= allowed_attempts)
                result["retry_next_attempt_at"] = None
                result["backoff_seconds"] = 0
                return result

            backoff_seconds = _compute_retry_backoff_seconds(
                attempt=current_attempt,
                initial_seconds=retry_initial_backoff_seconds,
                max_seconds=retry_max_backoff_seconds,
                multiplier=retry_backoff_multiplier,
            )
            jitter_seconds = random.uniform(0.0, min(1.5, backoff_seconds / 2.0)) if retry_jitter_enabled else 0.0
            sleep_seconds = backoff_seconds + jitter_seconds
            next_attempt_at = datetime.utcnow() + timedelta(seconds=sleep_seconds)
            result["backoff_seconds"] = round(sleep_seconds, 3)
            result["retry_next_attempt_at"] = next_attempt_at.isoformat()

            log_event(
                logger,
                logging.WARNING,
                "execution.broker_submit.retry_scheduled",
                symbol=symbol,
                side=side,
                qty=qty,
                attempt=current_attempt,
                retry_reason=retry_reason,
                backoff_seconds=round(sleep_seconds, 3),
            )
            time.sleep(max(sleep_seconds, 0.0))

        if last_result is not None:
            return last_result
        return {
            **base_payload,
            "ok": False,
            "reason": "broker_submit_unknown_failure",
            "permanent_failure": True,
        }
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "execution.broker_submit.failed",
            symbol=symbol,
            side=side,
            qty=qty,
            error=str(exc),
        )
        return {
            "ok": False,
            "error": str(exc),
            "symbol": symbol,
            "qty": qty,
            "side": side,
            "retry_eligible": False,
            "retry_reason": "submit_exception",
            "retry_attempt_count": 0,
            "retry_exhausted": False,
            "permanent_failure": True,
            "backoff_seconds": 0,
            "retry_next_attempt_at": None,
            "broker_submission_attempted_at": datetime.utcnow().isoformat(),
            "broker_submit_attempt_count": 1,
        }


def _notify_trade(symbol: str, qty: float, side: str, order: dict):
    """Send Telegram notification for executed trade."""
    try:
        from core.telegram_notifier import send_telegram_message, is_telegram_configured
        if not is_telegram_configured():
            return
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        mode = order.get("mode", "live")
        msg = (
            f"{emoji} <b>تنفيذ {side.upper()}</b>\n"
            f"📊 السهم: <b>{symbol}</b>\n"
            f"📦 الكمية: {qty}\n"
            f"💰 الوضع: {mode}\n"
            f"🆔 Order: {order.get('id', 'N/A')}"
        )
        send_telegram_message(msg)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# In-memory preview store (TTL = 5 minutes)
# ---------------------------------------------------------------------------
_PREVIEW_TTL_SECONDS: int = 300
_preview_store: dict[str, dict] = {}  # preview_id -> {preview, params, expires_at}
_preview_lock = threading.Lock()

logger = get_logger(__name__)


class ExecutionHaltedError(RuntimeError):
    """Raised when an execution attempt is blocked by the kill switch."""
    status_code = 503


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _build_quote_lookup(symbols) -> dict[str, dict]:
    normalized_symbols = [
        str(symbol or "").strip().upper()
        for symbol in (symbols or [])
        if str(symbol or "").strip()
    ]
    if not normalized_symbols:
        return {}
    snapshot = fetch_quote_snapshots(normalized_symbols)
    return {
        str(item.get("symbol") or "").strip().upper(): item
        for item in snapshot.get("items", [])
        if item.get("symbol")
    }


def _resolve_analysis_concurrency(symbol_count: int) -> int:
    import os

    try:
        configured = int(os.environ.get("MARKET_AI_ANALYSIS_CONCURRENCY", "1"))
    except Exception:
        configured = 1
    return max(1, min(configured, max(int(symbol_count or 0), 1), 8))


def _analyze_symbol_payload(
    symbol: str,
    strategy_mode: str,
    start_date: str,
    end_date: str,
    quote_lookup: dict[str, dict] | None = None,
) -> dict:
    include_dl = LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL and str(strategy_mode or "").strip().lower() in {"ensemble", "dl"}
    result = build_smart_analysis(symbol, start_date, end_date, include_dl=include_dl, include_ensemble=True)
    if "error" in result:
        return {
            "symbol": symbol,
            "result": result,
            "signal_snapshot": None,
            "error": result.get("error"),
        }

    signal_snapshot = _build_signal_snapshot(symbol, strategy_mode, result, start_date, end_date, quote_lookup=quote_lookup)
    return {
        "symbol": symbol,
        "result": result,
        "signal_snapshot": signal_snapshot,
        "error": None,
    }


def _collect_symbol_analyses(
    symbols: list[str],
    strategy_mode: str,
    start_date: str,
    end_date: str,
    quote_lookup: dict[str, dict] | None = None,
) -> tuple[list[dict], int]:
    concurrency = _resolve_analysis_concurrency(len(symbols))
    if concurrency <= 1 or len(symbols) <= 1:
        return [
            _analyze_symbol_payload(
                symbol,
                strategy_mode,
                start_date,
                end_date,
                quote_lookup=quote_lookup,
            )
            for symbol in symbols
        ], 1

    ordered_results: list[dict | None] = [None] * len(symbols)
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="signal-analysis") as executor:
        future_map = {
            executor.submit(
                _analyze_symbol_payload,
                symbol,
                strategy_mode,
                start_date,
                end_date,
                quote_lookup,
            ): (index, symbol)
            for index, symbol in enumerate(symbols)
        }
        for future in as_completed(future_map):
            index, symbol = future_map[future]
            try:
                ordered_results[index] = future.result()
            except Exception as exc:
                ordered_results[index] = {
                    "symbol": symbol,
                    "result": {"error": str(exc)},
                    "signal_snapshot": None,
                    "error": str(exc),
                }

    return [item for item in ordered_results if item is not None], concurrency


def _latest_price(symbol: str, fallback_price=None, quote_lookup: dict[str, dict] | None = None):
    normalized_symbol = str(symbol or "").strip().upper()
    if quote_lookup is not None:
        quote_payload = quote_lookup.get(normalized_symbol)
        if quote_payload is not None:
            return _safe_float(quote_payload.get("price"), fallback_price), quote_payload
        return _safe_float(fallback_price, 0.0), None
    snapshot = fetch_quote_snapshots([normalized_symbol])
    items = snapshot.get("items", [])
    if items:
        return _safe_float(items[0].get("price"), fallback_price), items[0]
    return _safe_float(fallback_price, 0.0), None


def _build_signal_snapshot(symbol: str, strategy_mode: str, result: dict, start_date: str, end_date: str, quote_lookup: dict[str, dict] | None = None) -> SignalSnapshot:
    signal_view = extract_signal_view({**result, "start_date": start_date, "end_date": end_date}, mode=strategy_mode)
    latest_price, quote_payload = _latest_price(symbol, signal_view.get("price"), quote_lookup=quote_lookup)
    return SignalSnapshot(
        symbol=symbol,
        strategy_mode=strategy_mode,
        signal=str(signal_view.get("signal", "HOLD")).upper(),
        confidence=_safe_float(signal_view.get("confidence"), 0.0),
        price=latest_price,
        reasoning=str(signal_view.get("reasoning") or ""),
        analysis_payload={"analysis": result, "quote": quote_payload, "signal_view": signal_view},
    )


def _resolve_auto_trade_gate_config(auto_trading_config: dict | None = None) -> dict:
    return _policy_resolve_auto_trade_gate_config(auto_trading_config)


def _is_auto_executable_signal(signal_snapshot: SignalSnapshot, auto_trading_config: dict | None = None) -> bool:
    return _policy_is_auto_executable_signal(signal_snapshot, auto_trading_config)


def _extract_analysis_score(signal_snapshot: SignalSnapshot) -> tuple[float, bool]:
    payload = signal_snapshot.analysis_payload if isinstance(signal_snapshot.analysis_payload, dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    ensemble = analysis.get("ensemble_output") if isinstance(analysis.get("ensemble_output"), dict) else {}
    raw_score = None
    if isinstance(ensemble, dict):
        raw_score = ensemble.get("ensemble_score")
    if raw_score is None and isinstance(analysis, dict):
        raw_score = analysis.get("ensemble_score") or analysis.get("score")
    if raw_score is None:
        return (0.0, False)
    return (abs(_safe_float(raw_score, 0.0)), True)


def _resolve_add_long_config(auto_trading_config: dict | None = None) -> dict:
    payload = auto_trading_config if isinstance(auto_trading_config, dict) else {}
    return {
        "allow": bool(payload.get("allow_add_to_existing_longs", AUTO_TRADING_ALLOW_ADD_TO_EXISTING_LONGS)),
        "min_confidence": max(_safe_float(payload.get("add_long_min_confidence", AUTO_TRADING_ADD_LONG_MIN_CONFIDENCE), AUTO_TRADING_ADD_LONG_MIN_CONFIDENCE), 0.0),
        "min_score": max(_safe_float(payload.get("add_long_min_score", AUTO_TRADING_ADD_LONG_MIN_SCORE), AUTO_TRADING_ADD_LONG_MIN_SCORE), 0.0),
        "max_position_pct": max(_safe_float(payload.get("add_long_max_position_pct", AUTO_TRADING_ADD_LONG_MAX_POSITION_PCT), AUTO_TRADING_ADD_LONG_MAX_POSITION_PCT), 0.0),
        "max_adds_per_day": max(int(_safe_float(payload.get("add_long_max_adds_per_symbol_per_day", AUTO_TRADING_ADD_LONG_MAX_ADDS_PER_SYMBOL_PER_DAY), AUTO_TRADING_ADD_LONG_MAX_ADDS_PER_SYMBOL_PER_DAY)), 0),
        "cooldown_minutes": max(int(_safe_float(payload.get("add_long_cooldown_minutes", AUTO_TRADING_ADD_LONG_COOLDOWN_MINUTES), AUTO_TRADING_ADD_LONG_COOLDOWN_MINUTES)), 0),
        "min_notional": max(_safe_float(payload.get("add_long_min_notional", AUTO_TRADING_ADD_LONG_MIN_NOTIONAL), AUTO_TRADING_ADD_LONG_MIN_NOTIONAL), 0.0),
        "min_shares": max(_safe_float(payload.get("add_long_min_shares", AUTO_TRADING_ADD_LONG_MIN_SHARES), AUTO_TRADING_ADD_LONG_MIN_SHARES), 0.0),
    }


def _recent_long_trade_activity(symbol: str, strategy_mode: str) -> tuple[int, datetime | None]:
    now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_mode = str(strategy_mode or "classic").strip().lower()

    try:
        with session_scope() as session:
            adds_today = int(
                session.query(PaperTrade)
                .filter(
                    PaperTrade.symbol == normalized_symbol,
                    PaperTrade.strategy_mode == normalized_mode,
                    PaperTrade.side == "LONG",
                    PaperTrade.action == "ADD",
                    PaperTrade.created_at >= day_start,
                    PaperTrade.created_at < day_end,
                )
                .count()
            )
            latest_row = (
                session.query(PaperTrade.created_at)
                .filter(
                    PaperTrade.symbol == normalized_symbol,
                    PaperTrade.strategy_mode == normalized_mode,
                    PaperTrade.side == "LONG",
                    PaperTrade.action.in_(["OPEN", "ADD"]),
                )
                .order_by(PaperTrade.created_at.desc())
                .first()
            )
        return adds_today, (latest_row[0] if latest_row else None)
    except Exception:
        return 0, None


def _map_add_guardrail_block_code(guardrails: dict) -> tuple[str, str]:
    reasons = guardrails.get("blocking_reasons") or []
    reason_text = " ".join(str(item or "") for item in reasons)
    if guardrails.get("blocked_reason"):
        reason_text = f"{reason_text} {guardrails.get('blocked_reason')}".strip()
    lowered = reason_text.lower()

    if "cash" in lowered or "available" in lowered or "insufficient" in lowered:
        return "add_blocked_by_cash", reason_text or "Insufficient cash to add to existing long."
    if "market" in lowered and "closed" in lowered:
        return "add_blocked_by_market_hours", reason_text or "Market/session guardrail blocked add order."
    return "add_blocked_by_risk", reason_text or "Risk guardrail blocked add order."


def _build_add_long_decision(
    *,
    current_position: PositionState,
    signal_snapshot: SignalSnapshot,
    quantity: float,
    auto_trading_config: dict | None,
) -> dict:
    add_cfg = _resolve_add_long_config(auto_trading_config)
    symbol = signal_snapshot.symbol
    strategy_mode = signal_snapshot.strategy_mode
    price = max(_safe_float(signal_snapshot.price, 0.0), 0.0)
    confidence = max(_safe_float(signal_snapshot.confidence, 0.0), 0.0)
    score_abs, score_present = _extract_analysis_score(signal_snapshot)

    current_qty = max(_safe_float(current_position.quantity, 0.0), 0.0)
    summary = {}
    try:
        portfolio_payload = get_internal_portfolio(limit=500)
        summary = portfolio_payload.get("summary", {}) if isinstance(portfolio_payload, dict) else {}
    except Exception:
        summary = {}

    portfolio_value = max(
        _safe_float(summary.get("total_equity") or summary.get("portfolio_value"), 0.0),
        0.0,
    )
    available_cash = max(_safe_float(summary.get("cash_balance"), 0.0), 0.0)
    current_position_value = max(current_qty * price, 0.0)
    current_position_pct = round((current_position_value / portfolio_value) * 100.0, 4) if portfolio_value > 0 else 0.0

    base_notional = max(
        _safe_float((auto_trading_config or {}).get("notional_per_trade"), 0.0),
        0.0,
    )
    max_position_pct = max(_safe_float(add_cfg.get("max_position_pct"), AUTO_TRADING_ADD_LONG_MAX_POSITION_PCT), 0.0)
    if portfolio_value > 0 and base_notional > 0:
        base_target_pct = min((base_notional / portfolio_value) * 100.0, max_position_pct)
    elif max_position_pct > 0:
        base_target_pct = max_position_pct * 0.45
    else:
        base_target_pct = 0.0

    min_conf = max(_safe_float(add_cfg.get("min_confidence"), 0.0), 0.0)
    min_score = max(_safe_float(add_cfg.get("min_score"), 0.0), 0.0)

    conf_span = max(100.0 - min_conf, 1.0)
    conf_factor = min(max((confidence - min_conf) / conf_span, 0.0), 1.0)
    if score_present:
        score_span = max(1.0 - min_score, 1e-6)
        score_factor = min(max((score_abs - min_score) / score_span, 0.0), 1.0)
    else:
        score_factor = conf_factor
    conviction = max(conf_factor, score_factor)

    dynamic_target_pct = max_position_pct * (0.45 + 0.55 * conviction) if max_position_pct > 0 else 0.0
    target_position_pct = min(max_position_pct, max(base_target_pct, dynamic_target_pct)) if max_position_pct > 0 else base_target_pct
    target_position_value = (portfolio_value * target_position_pct / 100.0) if portfolio_value > 0 else max(base_notional, quantity * price, current_position_value)
    addable_value = max(target_position_value - current_position_value, 0.0)

    context = {
        "current_position_value": round(current_position_value, 4),
        "current_position_pct": round(current_position_pct, 4),
        "target_position_value": round(target_position_value, 4),
        "target_position_pct": round(target_position_pct, 4),
        "addable_value": round(addable_value, 4),
        "analysis_score": round(score_abs, 4),
        "confidence": round(confidence, 4),
        "portfolio_value": round(portfolio_value, 4),
        "available_cash": round(available_cash, 4),
        "proposed_add_qty": 0.0,
        "add_block_reason": None,
    }

    def _blocked(code: str, detail: str) -> dict:
        context["add_block_reason"] = code
        return {
            "intent": "NONE",
            "quantity": 0.0,
            "reason_code": code,
            "reason": detail,
            "metadata": dict(context),
        }

    if not add_cfg.get("allow", True):
        return _blocked("existing_long_position_no_add", "Adding to existing LONG positions is disabled by runtime settings.")
    if price <= 0:
        return _blocked("add_price_unavailable", "ADD_LONG skipped because price is unavailable.")

    if confidence < min_conf or (score_present and score_abs < min_score):
        return _blocked(
            "insufficient_add_conviction",
            f"ADD_LONG skipped because conviction is below threshold (confidence={confidence:.2f}, score={score_abs:.4f}).",
        )

    if addable_value <= 1e-6:
        return _blocked("at_target_position_size", "ADD_LONG skipped because current position is already at or above target size.")

    min_notional = max(_safe_float(add_cfg.get("min_notional"), 0.0), 0.0)
    if min_notional > 0 and addable_value < min_notional:
        return _blocked("add_qty_below_minimum", "ADD_LONG skipped because addable value is below minimum notional threshold.")

    max_adds_per_day = max(int(add_cfg.get("max_adds_per_day", 0) or 0), 0)
    adds_today, latest_long_trade_at = _recent_long_trade_activity(symbol, strategy_mode)
    context["adds_today"] = adds_today
    context["latest_long_trade_at"] = latest_long_trade_at.isoformat() if latest_long_trade_at else None

    if max_adds_per_day > 0 and adds_today >= max_adds_per_day:
        return _blocked("add_daily_limit_reached", f"ADD_LONG skipped because daily add limit reached ({adds_today}/{max_adds_per_day}).")

    cooldown_minutes = max(int(add_cfg.get("cooldown_minutes", 0) or 0), 0)
    if cooldown_minutes > 0 and latest_long_trade_at is not None:
        elapsed_seconds = max((datetime.utcnow() - latest_long_trade_at).total_seconds(), 0.0)
        elapsed_minutes = elapsed_seconds / 60.0
        if elapsed_minutes < cooldown_minutes:
            remaining = max(cooldown_minutes - elapsed_minutes, 0.0)
            context["cooldown_remaining_minutes"] = round(remaining, 2)
            return _blocked("add_cooldown_active", f"ADD_LONG cooldown active; {remaining:.1f} minutes remaining.")

    trading_mode = str((auto_trading_config or {}).get("trading_mode") or _current_trading_mode()).strip().lower()
    margin_enabled = trading_mode == "margin"
    context["trading_mode"] = "margin" if margin_enabled else "cash"

    if margin_enabled:
        effective_add_value = max(addable_value, 0.0)
        if available_cash <= 0:
            context["cash_warning"] = "margin_buying_power_required"
    else:
        cash_buffered = max(available_cash * 0.995, 0.0)
        if cash_buffered <= 0:
            return _blocked("add_blocked_by_cash", "ADD_LONG skipped because available cash is zero.")

        effective_add_value = min(addable_value, cash_buffered)
        if effective_add_value <= 0:
            return _blocked("add_blocked_by_cash", "ADD_LONG skipped because available cash leaves no add capacity.")

    raw_qty = effective_add_value / price if price > 0 else 0.0
    proposed_qty = float(int(raw_qty))
    min_shares = max(_safe_float(add_cfg.get("min_shares"), 0.0), 0.0)
    if min_shares > 0 and proposed_qty < min_shares:
        context["proposed_add_qty"] = round(proposed_qty, 4)
        return _blocked("add_qty_below_minimum", "ADD_LONG skipped because calculated add quantity is below minimum shares.")

    proposed_notional = proposed_qty * price
    if min_notional > 0 and proposed_notional < min_notional:
        context["proposed_add_qty"] = round(proposed_qty, 4)
        return _blocked("add_qty_below_minimum", "ADD_LONG skipped because calculated notional is below minimum threshold.")

    if proposed_qty <= 0:
        return _blocked("add_qty_below_minimum", "ADD_LONG skipped because calculated quantity is zero.")

    guardrails = assess_execution_guardrails(
        intent="ADD_LONG",
        side="BUY",
        symbol=symbol,
        quantity=proposed_qty,
        price=price,
        available_cash=available_cash,
        current_side=current_position.side,
        current_quantity=current_position.quantity,
        trading_mode=_current_trading_mode(),
    )
    if not bool(guardrails.get("allowed", False)):
        code, detail = _map_add_guardrail_block_code(guardrails)
        return _blocked(code, detail)

    context["proposed_add_qty"] = round(proposed_qty, 4)
    context["add_block_reason"] = "add_long_allowed"
    return {
        "intent": "ADD_LONG",
        "quantity": round(proposed_qty, 4),
        "reason_code": "add_long_allowed",
        "reason": (
            f"ADD_LONG approved: current={current_position_pct:.2f}% target={target_position_pct:.2f}% "
            f"addable=${addable_value:.2f} qty={proposed_qty:.0f}."
        ),
        "metadata": context,
    }


def _build_trade_intents(
    current_position: PositionState | None,
    signal_snapshot: SignalSnapshot,
    quantity: float,
    auto_trading_config: dict | None = None,
) -> list[TradeIntent]:
    quantity = max(_safe_float(quantity, 1.0), 1.0)
    signal = signal_snapshot.signal
    price = signal_snapshot.price
    symbol = signal_snapshot.symbol
    strategy_mode = signal_snapshot.strategy_mode
    intents: list[TradeIntent] = []
    margin_enabled = _is_margin_trading_enabled()
    trade_direction = _resolve_auto_trade_gate_config(auto_trading_config)["trade_direction"]
    allow_long_entries = trade_direction in {"both", "long_only"}
    allow_short_entries = trade_direction in {"both", "short_only"}

    if signal == "BUY":
        if current_position and current_position.side == "SHORT":
            intents.append(TradeIntent(intent="CLOSE_SHORT", symbol=symbol, strategy_mode=strategy_mode, side="SHORT", quantity=current_position.quantity, execution_price=price, reason="Signal BUY closed short"))

        if allow_long_entries and current_position and current_position.side == "LONG":
            add_plan = _build_add_long_decision(
                current_position=current_position,
                signal_snapshot=signal_snapshot,
                quantity=quantity,
                auto_trading_config=auto_trading_config,
            )
            if add_plan.get("intent") == "ADD_LONG":
                intents.append(
                    TradeIntent(
                        intent="ADD_LONG",
                        symbol=symbol,
                        strategy_mode=strategy_mode,
                        side="LONG",
                        quantity=max(_safe_float(add_plan.get("quantity"), 0.0), 0.0),
                        execution_price=price,
                        reason=str(add_plan.get("reason") or "ADD_LONG approved"),
                        metadata=add_plan.get("metadata") if isinstance(add_plan.get("metadata"), dict) else {},
                    )
                )
            else:
                intents.append(
                    TradeIntent(
                        intent="NONE",
                        symbol=symbol,
                        strategy_mode=strategy_mode,
                        quantity=0.0,
                        execution_price=price,
                        reason=str(add_plan.get("reason") or "Signal BUY on existing LONG produced no add action."),
                        metadata=add_plan.get("metadata") if isinstance(add_plan.get("metadata"), dict) else {},
                    )
                )
        elif allow_long_entries and (not current_position or current_position.side != "LONG"):
            intents.append(TradeIntent(intent="OPEN_LONG", symbol=symbol, strategy_mode=strategy_mode, side="LONG", quantity=quantity, execution_price=price, reason="Signal BUY opened long"))
        elif not intents:
            intents.append(TradeIntent(intent="NONE", symbol=symbol, strategy_mode=strategy_mode, quantity=0.0, execution_price=price, reason="Signal BUY ignored because short-only mode blocks new long entries"))
    elif signal == "SELL":
        if current_position and current_position.side == "LONG":
            intents.append(TradeIntent(intent="CLOSE_LONG", symbol=symbol, strategy_mode=strategy_mode, side="LONG", quantity=current_position.quantity, execution_price=price, reason="Signal SELL closed long"))
        if allow_short_entries and margin_enabled and (not current_position or current_position.side != "SHORT"):
            intents.append(TradeIntent(intent="OPEN_SHORT", symbol=symbol, strategy_mode=strategy_mode, side="SHORT", quantity=quantity, execution_price=price, reason="Signal SELL opened short in margin mode"))
        elif not intents:
            reason = "Signal SELL ignored because no long position is open"
            if not allow_short_entries:
                reason = "Signal SELL ignored because long-only mode blocks new short entries"
            elif not margin_enabled:
                reason = "Signal SELL ignored because margin mode is disabled and no long position is open"
            intents.append(TradeIntent(intent="NONE", symbol=symbol, strategy_mode=strategy_mode, quantity=0.0, execution_price=price, reason=reason))
    else:
        intents.append(TradeIntent(intent="NONE", symbol=symbol, strategy_mode=strategy_mode, quantity=0.0, execution_price=price, reason="Signal HOLD generated no execution intent"))
    return intents


def _build_trade_intents_from_decision(
    current_position: PositionState | None,
    signal_snapshot: SignalSnapshot,
    fallback_quantity: float,
    decision_override: dict | None,
    auto_trading_config: dict | None = None,
) -> list[TradeIntent]:
    override = decision_override if isinstance(decision_override, dict) else {}
    requested_action = str(override.get("requested_execution_action") or "").strip().upper()
    requested_qty = max(_safe_float(override.get("approved_order_qty"), _safe_float(override.get("proposed_order_qty"), 0.0)), 0.0)
    quantity = requested_qty if requested_qty > 0 else max(_safe_float(fallback_quantity, 1.0), 1.0)
    priority_band = str(override.get("execution_priority_band") or "deferred").strip().lower() or "deferred"
    metadata = {
        "requested_execution_action": requested_action or None,
        "decision_outcome_code": str(override.get("decision_outcome_code") or "").strip().lower() or None,
        "decision_outcome_detail": str(override.get("decision_outcome_detail") or "").strip() or None,
        "target_position_pct": _safe_float(override.get("target_position_pct"), 0.0),
        "current_position_pct": _safe_float(override.get("current_position_pct"), 0.0),
        "desired_delta_pct": _safe_float(override.get("desired_delta_pct"), 0.0),
        "opportunity_score": _safe_float(override.get("opportunity_score"), 0.0),
        "conviction_tier": str(override.get("conviction_tier") or "").strip().lower() or None,
        "execution_priority_band": priority_band,
        "execution_priority": str(override.get("execution_priority") or ("high" if priority_band in {"critical", "high"} else "normal" if priority_band == "normal" else "low")).strip().lower(),
        "order_style_preference": str(override.get("order_style_preference") or "market").strip().lower(),
        "execution_skip_reason": str(override.get("execution_skip_reason") or "").strip().lower() or None,
        "funded_partially": bool(override.get("funded_partially", False)),
        "funding_status": str(override.get("funding_status") or "").strip().lower() or None,
        "funding_ratio": _safe_float(override.get("funding_ratio"), 0.0),
        "partial_funding_reason": str(override.get("partial_funding_reason") or "").strip() or None,
        "requested_order_qty": _safe_float(override.get("requested_order_qty"), 0.0),
        "approved_order_qty": _safe_float(override.get("approved_order_qty"), 0.0),
    }
    symbol = signal_snapshot.symbol
    strategy_mode = signal_snapshot.strategy_mode
    price = signal_snapshot.price

    if requested_action in {"", "HOLD", "NONE"}:
        reason = str(override.get("decision_outcome_detail") or "Portfolio allocator selected HOLD.")
        return [
            TradeIntent(
                intent="NONE",
                symbol=symbol,
                strategy_mode=strategy_mode,
                quantity=0.0,
                execution_price=price,
                reason=reason,
                metadata=metadata,
            )
        ]

    if requested_action == "OPEN_LONG":
        if current_position and current_position.side == "LONG":
            requested_action = "ADD_LONG"
        elif current_position and current_position.side == "SHORT":
            return [
                TradeIntent(
                    intent="CLOSE_SHORT",
                    symbol=symbol,
                    strategy_mode=strategy_mode,
                    side="SHORT",
                    quantity=float(current_position.quantity or 0.0),
                    execution_price=price,
                    reason=str(override.get("decision_outcome_detail") or "Portfolio allocator closes SHORT before LONG entry."),
                    metadata=metadata,
                ),
                TradeIntent(
                    intent="OPEN_LONG",
                    symbol=symbol,
                    strategy_mode=strategy_mode,
                    side="LONG",
                    quantity=max(quantity, 1.0),
                    execution_price=price,
                    reason=str(override.get("decision_outcome_detail") or "Portfolio allocator approved OPEN_LONG."),
                    metadata=metadata,
                ),
            ]

    if requested_action == "ADD_LONG":
        if not current_position or current_position.side != "LONG":
            requested_action = "OPEN_LONG"

    if requested_action in {"OPEN_LONG", "ADD_LONG"}:
        return [
            TradeIntent(
                intent=requested_action,
                symbol=symbol,
                strategy_mode=strategy_mode,
                side="LONG",
                quantity=max(quantity, 1.0),
                execution_price=price,
                reason=str(override.get("decision_outcome_detail") or f"Portfolio allocator approved {requested_action}."),
                metadata=metadata,
            )
        ]

    if requested_action in {"REDUCE_LONG", "EXIT_LONG"}:
        if not current_position or current_position.side != "LONG":
            return [
                TradeIntent(
                    intent="NONE",
                    symbol=symbol,
                    strategy_mode=strategy_mode,
                    quantity=0.0,
                    execution_price=price,
                    reason="Requested long reduction/exit but no open LONG position exists.",
                    metadata=metadata,
                )
            ]
        current_qty = max(_safe_float(current_position.quantity, 0.0), 0.0)
        if current_qty <= 0:
            return [
                TradeIntent(
                    intent="NONE",
                    symbol=symbol,
                    strategy_mode=strategy_mode,
                    quantity=0.0,
                    execution_price=price,
                    reason="Requested long reduction/exit but current quantity is zero.",
                    metadata=metadata,
                )
            ]

        close_qty = current_qty if requested_action == "EXIT_LONG" else min(max(quantity, 1.0), current_qty)
        return [
            TradeIntent(
                intent="CLOSE_LONG",
                symbol=symbol,
                strategy_mode=strategy_mode,
                side="LONG",
                quantity=round(close_qty, 4),
                execution_price=price,
                reason=str(override.get("decision_outcome_detail") or f"Portfolio allocator approved {requested_action}."),
                metadata={
                    **metadata,
                    "requested_execution_action": requested_action,
                },
            )
        ]

    return [
        TradeIntent(
            intent="NONE",
            symbol=symbol,
            strategy_mode=strategy_mode,
            quantity=0.0,
            execution_price=price,
            reason=f"Unsupported portfolio decision action: {requested_action}",
            metadata=metadata,
        )
    ]


def _get_internal_cash_balance() -> float:
    portfolio = get_internal_portfolio(limit=500)
    summary = portfolio.get("summary", {}) if isinstance(portfolio, dict) else {}
    return max(_safe_float(summary.get("cash_balance"), 0.0), 0.0)


def _current_trading_mode() -> str:
    guardrails = get_broker_guardrails()
    return "margin" if str(guardrails.get("trading_mode") or "").strip().lower() == "margin" else "cash"


def _is_margin_trading_enabled() -> bool:
    return _current_trading_mode() == "margin"


def _derive_order_intent(
    *,
    side: str,
    quantity: float,
    current_position: PositionState | None = None,
) -> str:
    normalized_side = str(side or "").strip().upper()
    qty = max(_safe_float(quantity, 0.0), 0.0)
    margin_enabled = _is_margin_trading_enabled()

    if normalized_side == "BUY":
        if current_position and current_position.side == "SHORT" and qty <= float(current_position.quantity or 0.0) + 1e-9:
            return "CLOSE_SHORT"
        return "OPEN_LONG"

    if current_position and current_position.side == "LONG" and qty <= float(current_position.quantity or 0.0) + 1e-9:
        return "CLOSE_LONG"
    return "OPEN_SHORT" if margin_enabled else "CLOSE_LONG"


def _assess_order_guardrails(
    *,
    side: str,
    symbol: str,
    quantity: float,
    estimated_price: float,
    fee_amount: float = 0.0,
    current_position: PositionState | None = None,
) -> dict:
    normalized_side = str(side or "").strip().upper()
    available_cash = None
    if normalized_side == "BUY":
        available_cash = _get_internal_cash_balance()
    intent = _derive_order_intent(side=normalized_side, quantity=quantity, current_position=current_position)

    return assess_execution_guardrails(
        intent=intent,
        side=side,
        symbol=symbol,
        quantity=quantity,
        price=estimated_price,
        fee_amount=fee_amount,
        available_cash=available_cash,
        current_side=None if current_position is None else current_position.side,
        current_quantity=None if current_position is None else current_position.quantity,
        trading_mode=_current_trading_mode(),
    )


def _paper_status_to_execution_state(status: str | None) -> ExecutionStatus:
    normalized = str(status or "").strip().upper()
    mapping = {
        "OPEN": ExecutionStatus.SUBMITTED,
        "PARTIAL_FILL": ExecutionStatus.PARTIALLY_FILLED,
        "FILLED": ExecutionStatus.FILLED,
        "CANCELED": ExecutionStatus.CANCELED,
        "REJECTED": ExecutionStatus.REJECTED,
    }
    return mapping.get(normalized, ExecutionStatus.SUBMITTED)


def _execution_state_to_paper_status(state: ExecutionStatus) -> str:
    mapping = {
        ExecutionStatus.SUBMITTED: "OPEN",
        ExecutionStatus.ACKNOWLEDGED: "OPEN",
        ExecutionStatus.PARTIALLY_FILLED: "PARTIAL_FILL",
        ExecutionStatus.FILLED: "FILLED",
        ExecutionStatus.CANCELED: "CANCELED",
        ExecutionStatus.REJECTED: "REJECTED",
    }
    return mapping.get(state, "OPEN")


def _build_create_order_state_path(*, order_fills_immediately: bool, is_partial_fill: bool) -> tuple[ExecutionStatus, list[str]]:
    state = ExecutionStatus.DRAFT
    path = [state.value]
    for target in (ExecutionStatus.RISK_PENDING, ExecutionStatus.APPROVED, ExecutionStatus.SUBMITTING, ExecutionStatus.SUBMITTED):
        state = transition_execution_status(state, target)
        path.append(state.value)
    if order_fills_immediately:
        state = transition_execution_status(state, ExecutionStatus.ACKNOWLEDGED)
        path.append(state.value)
        final_target = ExecutionStatus.PARTIALLY_FILLED if is_partial_fill else ExecutionStatus.FILLED
        state = transition_execution_status(state, final_target)
        path.append(state.value)
    return state, path


def _validate_cash_only_order(
    *,
    side: str,
    symbol: str,
    quantity: float,
    estimated_price: float,
    fee_amount: float = 0.0,
    current_position: PositionState | None = None,
) -> tuple[bool, str | None]:
    decision = _assess_order_guardrails(
        side=side,
        symbol=symbol,
        quantity=quantity,
        estimated_price=estimated_price,
        fee_amount=fee_amount,
        current_position=current_position,
    )
    cash_check = decision.get("cash_check") or {}
    return bool(cash_check.get("allowed", False)), cash_check.get("blocked_reason")


def _record_signal_alerts(repo: ExecutionRepository, strategy_mode: str, signal_snapshot: SignalSnapshot, previous_signal: SignalRecord | None) -> None:
    if signal_snapshot.signal == "BUY" and (previous_signal is None or previous_signal.signal != "BUY"):
        repo.append_alert(AlertRecord(symbol=signal_snapshot.symbol, strategy_mode=strategy_mode, alert_type="new_buy_signal", severity="info", message=f"{signal_snapshot.symbol} generated a new BUY signal in {strategy_mode}", payload=signal_snapshot.model_dump()))
    if signal_snapshot.signal == "SELL" and (previous_signal is None or previous_signal.signal != "SELL"):
        repo.append_alert(AlertRecord(symbol=signal_snapshot.symbol, strategy_mode=strategy_mode, alert_type="new_sell_signal", severity="info", message=f"{signal_snapshot.symbol} generated a new SELL signal in {strategy_mode}", payload=signal_snapshot.model_dump()))
    if previous_signal is not None and abs(_safe_float(previous_signal.confidence) - signal_snapshot.confidence) >= 15:
        repo.append_alert(AlertRecord(symbol=signal_snapshot.symbol, strategy_mode=strategy_mode, alert_type="confidence_change", severity="warning", message=f"{signal_snapshot.symbol} confidence changed materially in {strategy_mode}", payload={"previous_confidence": previous_signal.confidence, "current_confidence": signal_snapshot.confidence}))


def _build_signal_id(symbol: str, strategy_mode: str, correlation_id: str | None) -> str:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_mode = str(strategy_mode or "classic").strip().lower()
    correlation = str(correlation_id or uuid4().hex[:12]).strip()
    return f"sig-{normalized_symbol}-{normalized_mode}-{correlation}"


def _build_order_intent_id(symbol: str, side: str, correlation_id: str | None) -> str:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_side = str(side or "").strip().upper()
    correlation = str(correlation_id or uuid4().hex[:12]).strip()
    return f"oi-{normalized_symbol}-{normalized_side}-{correlation}-{uuid4().hex[:8]}"


def _build_internal_portfolio_snapshot_from_repo(repo: ExecutionRepository, limit: int = 500) -> dict:
    import os

    items = [position.model_dump(mode="json") for position in repo.list_open_positions()[:limit]]
    all_trades = [row.model_dump(mode="json") for row in repo.list_trades(limit=10000)]
    long_market_value = round(sum(_safe_float(item.get("market_value")) for item in items if str(item.get("side") or "").upper() == "LONG"), 4)
    short_market_value = round(sum(_safe_float(item.get("market_value")) for item in items if str(item.get("side") or "").upper() == "SHORT"), 4)
    total_market_value = round(long_market_value + short_market_value, 4)
    net_market_value = round(long_market_value - short_market_value, 4)
    total_unrealized = round(sum(_safe_float(item.get("unrealized_pnl")) for item in items), 4)
    total_realized = round(sum(_safe_float(item.get("realized_pnl")) for item in items), 4)
    long_cost = round(
        sum(_safe_float(item.get("avg_entry_price")) * _safe_float(item.get("quantity")) for item in items if str(item.get("side") or "").upper() == "LONG"),
        4,
    )
    short_proceeds = round(
        sum(_safe_float(item.get("avg_entry_price")) * _safe_float(item.get("quantity")) for item in items if str(item.get("side") or "").upper() == "SHORT"),
        4,
    )
    starting_cash = _safe_float(os.environ.get("MARKET_AI_PAPER_STARTING_CASH"), default=100_000.0)
    cash_balance = round(starting_cash + total_realized - long_cost + short_proceeds, 4)
    total_equity = round(cash_balance + net_market_value, 4)
    close_trades = [t for t in all_trades if (t.get("action") or "").upper() in {"CLOSE", "CLOSE_LONG", "CLOSE_SHORT", "EXIT"}]
    wins = sum(1 for t in close_trades if _safe_float(t.get("realized_pnl")) > 0)
    win_rate = round((wins / len(close_trades) * 100.0), 2) if close_trades else None
    return {
        "items": items,
        "positions": items,
        "summary": {
            "open_positions": len(items),
            "total_market_value": total_market_value,
            "long_market_value": long_market_value,
            "short_market_value": short_market_value,
            "net_market_value": net_market_value,
            "portfolio_value": total_equity,
            "starting_cash": starting_cash,
            "cash_balance": cash_balance,
            "invested_cost": long_cost,
            "short_sale_proceeds": short_proceeds,
            "total_equity": total_equity,
            "total_unrealized_pnl": total_unrealized,
            "total_realized_pnl": total_realized,
            "total_trades": len(all_trades),
            "win_rate_pct": win_rate if win_rate is not None else "-",
        },
    }


def _record_risk_decision_event(
    session,
    *,
    signal_id: str | None,
    symbol: str,
    intent: str,
    side: str,
    decision: str,
    approved_qty: float | None,
    reason_codes: list[str] | None,
    risk_snapshot: dict,
    correlation_id: str | None,
) -> None:
    if hasattr(session, "add"):
        platform_repo = PlatformEventRepository(session)
        platform_repo.append_risk_decision(
            signal_id=signal_id,
            symbol=symbol,
            intent=intent,
            side=side,
            decision=decision,
            approved_qty=approved_qty,
            reason_codes=reason_codes,
            risk_snapshot=risk_snapshot,
            correlation_id=correlation_id,
        )
    publish_event(
        event_type=RISK_SIGNAL_ACCEPTED if str(decision).lower() == "accepted" else RISK_SIGNAL_REJECTED,
        producer="execution_service",
        payload={
            "signal_id": signal_id,
            "symbol": symbol,
            "intent": intent,
            "side": side,
            "decision": decision,
            "approved_qty": approved_qty,
            "reason_codes": reason_codes or [],
            "risk_snapshot": risk_snapshot,
        },
        correlation_id=correlation_id,
    )
    emit_counter(
        "risk_decisions_total",
        decision=str(decision).lower(),
        intent=intent,
        symbol=symbol,
    )


def _record_order_event(
    session,
    *,
    order_intent_id: str | None,
    client_order_id: str | None,
    symbol: str,
    event_type: str,
    correlation_id: str | None,
    payload: dict,
) -> None:
    envelope = publish_event(
        event_type=event_type,
        producer="execution_service",
        payload=payload,
        correlation_id=correlation_id,
    )
    if hasattr(session, "add"):
        PlatformEventRepository(session).append_order_event(
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            event_version=envelope.event_version,
            producer=envelope.producer,
            correlation_id=envelope.correlation_id,
            payload=envelope.payload,
            order_intent_id=order_intent_id,
            client_order_id=client_order_id,
            symbol=symbol,
        )
    emit_counter(
        "execution_order_events_total",
        event_type=event_type,
        symbol=symbol,
    )


def _record_portfolio_snapshot_event(repo: ExecutionRepository, *, correlation_id: str | None, snapshot_type: str) -> None:
    snapshot = _build_internal_portfolio_snapshot_from_repo(repo)
    if hasattr(repo.session, "add"):
        PlatformEventRepository(repo.session).append_portfolio_snapshot(
            snapshot_type=snapshot_type,
            active_source="broker_live",
            correlation_id=correlation_id,
            summary=snapshot.get("summary") or {},
            positions=snapshot.get("positions") or [],
        )
    publish_event(
        event_type=PORTFOLIO_SNAPSHOT_UPDATED,
        producer="execution_service",
        payload={
            "snapshot_type": snapshot_type,
            "active_source": "broker_live",
            "summary": snapshot.get("summary") or {},
            "positions": snapshot.get("positions") or [],
        },
        correlation_id=correlation_id,
    )
    emit_counter("portfolio_snapshots_total", snapshot_type=snapshot_type, source="broker_live")


def _apply_trade_intent(
    repo: ExecutionRepository,
    current_row,
    intent: TradeIntent,
    correlation_id: str | None = None,
    signal_id: str | None = None,
) -> None:
    """Apply a single trade intent with execution-owned guardrails.

    Guardrails are evaluated here so that every call site — including future
    callers — automatically gets deterministic cash-only and risk protection
    without needing to remember to call another service first.
    """
    if intent.intent == "NONE":
        repo.append_audit_event(ExecutionEventRecord(
            event_type="execution_intent_skipped",
            symbol=intent.symbol,
            strategy_mode=intent.strategy_mode,
            correlation_id=correlation_id,
            payload={"intent": intent.intent, "reason": intent.reason, "intent_metadata": intent.metadata if isinstance(intent.metadata, dict) else {}},
        ))
        return

    # ------------------------------------------------------------------
    # Paper fill simulation — slippage, spread, fee, partial fill
    # OPEN_LONG / CLOSE_SHORT are buy-side; OPEN_SHORT / CLOSE_LONG are sell-side.
    # ------------------------------------------------------------------
    fill_side = "BUY" if intent.intent in {"OPEN_LONG", "ADD_LONG", "CLOSE_SHORT"} else "SELL"
    fill = compute_fill(
        side=fill_side,
        quantity=intent.quantity,
        reference_price=intent.execution_price,
        order_type="market",
    )
    fill_price = fill.fill_price
    fill_qty = fill.filled_quantity
    fill_notes = f"{intent.reason} | {fill.to_notes_str()}"
    fill_audit = fill.to_audit_dict()
    # ------------------------------------------------------------------

    current_position = None if current_row is None else PositionState(
        id=current_row.id,
        symbol=current_row.symbol,
        strategy_mode=current_row.strategy_mode,
        side=current_row.side,
        quantity=current_row.quantity,
        avg_entry_price=current_row.avg_entry_price,
        current_price=current_row.current_price,
        market_value=current_row.market_value or 0.0,
        unrealized_pnl=current_row.unrealized_pnl or 0.0,
        realized_pnl=current_row.realized_pnl or 0.0,
        status=current_row.status,
        opened_at=current_row.opened_at,
        updated_at=current_row.updated_at,
    )

    guardrails = assess_execution_guardrails(
        intent=intent.intent,
        side=fill_side,
        symbol=intent.symbol,
        quantity=fill_qty if fill_qty > 0 else intent.quantity,
        price=fill_price if fill_price > 0 else intent.execution_price,
        fee_amount=fill.fee_amount,
        available_cash=_get_internal_cash_balance(),
        current_side=None if current_position is None else current_position.side,
        current_quantity=None if current_position is None else current_position.quantity,
        trading_mode=_current_trading_mode(),
    )
    risk_snapshot = {
        "fill": fill_audit,
        "guardrails": guardrails,
        "price": fill_price if fill_price > 0 else intent.execution_price,
        "quantity": fill_qty if fill_qty > 0 else intent.quantity,
    }
    if not guardrails["allowed"]:
        _record_risk_decision_event(
            repo.session,
            signal_id=signal_id,
            symbol=intent.symbol,
            intent=intent.intent,
            side=fill_side,
            decision="rejected",
            approved_qty=None,
            reason_codes=guardrails.get("blocking_reasons", []),
            risk_snapshot=risk_snapshot,
            correlation_id=correlation_id,
        )
        repo.append_audit_event(ExecutionEventRecord(
            event_type="execution_guardrails_blocked",
            symbol=intent.symbol,
            strategy_mode=intent.strategy_mode,
            correlation_id=correlation_id,
            payload={
                "intent": intent.intent,
                "intent_metadata": intent.metadata if isinstance(intent.metadata, dict) else {},
                "blocked_reason": guardrails["blocked_reason"],
                "blocking_reasons": guardrails.get("blocking_reasons", []),
                "warnings": guardrails.get("warnings", []),
                "risk_check": guardrails.get("risk_check"),
                "cash_check": guardrails.get("cash_check"),
                "price": fill_price if fill_price > 0 else intent.execution_price,
                "quantity": fill_qty if fill_qty > 0 else intent.quantity,
                "fill": fill_audit,
            },
        ))
        log_event(
            logger,
            logging.WARNING,
            "execution.guardrails.blocked",
            symbol=intent.symbol,
            intent=intent.intent,
            reason=guardrails["blocked_reason"],
            correlation_id=correlation_id,
        )
        return

    approved_qty = fill_qty if fill_qty > 0 else intent.quantity
    order_intent_id = _build_order_intent_id(intent.symbol, fill_side, correlation_id)
    client_order_id = f"auto-{uuid4().hex[:12]}"
    platform_repo = PlatformEventRepository(repo.session)
    _record_risk_decision_event(
        repo.session,
        signal_id=signal_id,
        symbol=intent.symbol,
        intent=intent.intent,
        side=fill_side,
        decision="accepted",
        approved_qty=approved_qty,
        reason_codes=[],
        risk_snapshot=risk_snapshot,
        correlation_id=correlation_id,
    )
    if hasattr(repo.session, "add"):
        platform_repo.append_order_intent(
            order_intent_id=order_intent_id,
            signal_id=signal_id,
            broker="alpaca",
            symbol=intent.symbol,
            side=fill_side,
            qty=approved_qty,
            order_type="market",
            time_in_force="day",
            client_order_id=client_order_id,
            idempotency_key=f"{correlation_id}:{intent.symbol}:{intent.intent}",
            status=ExecutionStatus.SUBMITTED.value,
            correlation_id=correlation_id,
            payload={
                "intent": intent.intent,
                "strategy_mode": intent.strategy_mode,
                "reason": intent.reason,
                "intent_metadata": intent.metadata if isinstance(intent.metadata, dict) else {},
                "fill_preview": fill_audit,
            },
        )
    _record_order_event(
        repo.session,
        order_intent_id=order_intent_id,
        client_order_id=client_order_id,
        symbol=intent.symbol,
        event_type=EXECUTION_ORDER_INTENT_CREATED,
        correlation_id=correlation_id,
        payload={
            "order_intent_id": order_intent_id,
            "signal_id": signal_id,
            "symbol": intent.symbol,
            "side": fill_side,
            "qty": approved_qty,
            "order_type": "market",
            "strategy_mode": intent.strategy_mode,
            "intent": intent.intent,
            "intent_metadata": intent.metadata if isinstance(intent.metadata, dict) else {},
        },
    )

    if intent.intent in {"CLOSE_LONG", "CLOSE_SHORT"} and current_row is not None:
        current_qty = max(_safe_float(getattr(current_row, "quantity", 0.0), 0.0), 0.0)
        close_qty = fill_qty if fill_qty > 0 else current_qty
        close_qty = min(max(close_qty, 0.0), current_qty)
        sign = 1 if current_row.side == "LONG" else -1
        gross_pnl = round((fill_price - float(current_row.avg_entry_price or 0.0)) * close_qty * sign, 4)
        # Fees reduce realized P&L on close
        realized = round(gross_pnl - fill.fee_amount, 4)

        remaining_qty = round(max(current_qty - close_qty, 0.0), 4)
        is_partial_close = remaining_qty > 1e-9
        if is_partial_close:
            existing_realized = _safe_float(getattr(current_row, "realized_pnl", 0.0), 0.0)
            repo.upsert_position(
                symbol=current_row.symbol,
                strategy_mode=current_row.strategy_mode,
                side=current_row.side,
                quantity=remaining_qty,
                avg_entry_price=_safe_float(getattr(current_row, "avg_entry_price", fill_price), fill_price),
                current_price=fill_price,
                market_value=round(fill_price * remaining_qty, 4),
                unrealized_pnl=0.0,
                realized_pnl=round(existing_realized + realized, 4),
                status="OPEN",
                stop_loss_price=getattr(current_row, "stop_loss_price", None),
                trailing_stop_pct=getattr(current_row, "trailing_stop_pct", None),
                trailing_stop_price=getattr(current_row, "trailing_stop_price", None),
                high_water_mark=getattr(current_row, "high_water_mark", None),
            )
        else:
            repo.close_position(current_row, current_price=fill_price, realized_pnl=realized)

        requested_action = str((intent.metadata or {}).get("requested_execution_action") or "").strip().upper()
        trade_action = "CLOSE"
        if is_partial_close and requested_action in {"REDUCE_LONG"}:
            trade_action = "REDUCE"
        elif is_partial_close and current_row.side == "SHORT":
            trade_action = "COVER"

        repo.append_trade(TradeRecord(
            symbol=intent.symbol, strategy_mode=intent.strategy_mode,
            action=trade_action, side=current_row.side, quantity=close_qty,
            price=fill_price, realized_pnl=realized, notes=fill_notes,
        ))
        # Submit SELL to Alpaca broker
        broker_side = "SELL" if intent.intent == "CLOSE_LONG" else "BUY"
        broker_result = _submit_to_broker(intent.symbol, close_qty, broker_side, estimated_price=fill_price)
        broker_info = broker_result if broker_result else {"skipped": True}
        _record_order_event(
            repo.session,
            order_intent_id=order_intent_id,
            client_order_id=client_order_id,
            symbol=intent.symbol,
            event_type=EXECUTION_ORDER_SUBMITTED,
            correlation_id=correlation_id,
            payload={
                "order_intent_id": order_intent_id,
                "client_order_id": client_order_id,
                "symbol": intent.symbol,
                "side": broker_side,
                "qty": close_qty,
                "broker": broker_info,
                "execution_state": ExecutionStatus.SUBMITTED.value,
                "intent_metadata": intent.metadata if isinstance(intent.metadata, dict) else {},
            },
        )
        _record_order_event(
            repo.session,
            order_intent_id=order_intent_id,
            client_order_id=client_order_id,
            symbol=intent.symbol,
            event_type=EXECUTION_FILL_RECEIVED,
            correlation_id=correlation_id,
            payload={
                "order_intent_id": order_intent_id,
                "client_order_id": client_order_id,
                "symbol": intent.symbol,
                "side": broker_side,
                "fill": fill_audit,
                "realized_pnl": realized,
                "broker": broker_info,
                "intent_metadata": intent.metadata if isinstance(intent.metadata, dict) else {},
            },
        )
        audit_event_type = intent.intent.lower()
        if is_partial_close and requested_action == "REDUCE_LONG" and intent.intent == "CLOSE_LONG":
            audit_event_type = "reduce_long"
        elif requested_action == "EXIT_LONG" and intent.intent == "CLOSE_LONG":
            audit_event_type = "exit_long"

        repo.append_audit_event(ExecutionEventRecord(
            event_type=audit_event_type, symbol=intent.symbol,
            strategy_mode=intent.strategy_mode, correlation_id=correlation_id,
            payload={
                "price": fill_price,
                "quantity": close_qty,
                "remaining_qty": remaining_qty,
                "partial": bool(is_partial_close),
                "realized_pnl": realized,
                "fill": fill_audit,
                "broker": broker_info,
                "intent": intent.intent,
                "intent_metadata": intent.metadata if isinstance(intent.metadata, dict) else {},
            },
        ))
        _record_portfolio_snapshot_event(
            repo,
            correlation_id=correlation_id,
            snapshot_type="execution_reduce" if is_partial_close else "execution_close",
        )
    elif intent.intent in {"OPEN_LONG", "ADD_LONG"}:
        from backend.app.services.risk_engine import DEFAULT_TRAILING_STOP_PCT

        is_add_long = bool(intent.intent == "ADD_LONG" and current_row is not None and str(getattr(current_row, "side", "")).upper() == "LONG")
        existing_qty = max(_safe_float(getattr(current_row, "quantity", 0.0), 0.0), 0.0) if is_add_long else 0.0
        existing_avg = max(_safe_float(getattr(current_row, "avg_entry_price", 0.0), 0.0), 0.0) if is_add_long else 0.0
        realized_pnl = _safe_float(getattr(current_row, "realized_pnl", 0.0), 0.0) if is_add_long else 0.0

        total_qty = fill_qty if not is_add_long else round(existing_qty + fill_qty, 4)
        if is_add_long and total_qty > 0:
            avg_entry_price = round(((existing_qty * existing_avg) + (fill_qty * fill_price)) / total_qty, 6)
        else:
            avg_entry_price = fill_price

        existing_trailing_pct = _safe_float(getattr(current_row, "trailing_stop_pct", 0.0), 0.0) if is_add_long else 0.0
        trailing_pct = existing_trailing_pct if existing_trailing_pct > 0 else DEFAULT_TRAILING_STOP_PCT
        existing_hwm = _safe_float(getattr(current_row, "high_water_mark", 0.0), 0.0) if is_add_long else 0.0
        high_water_mark = max(existing_hwm, fill_price) if is_add_long else fill_price
        trailing_stop = round(high_water_mark * (1 - trailing_pct / 100.0), 4)

        existing_stop_loss = _safe_float(getattr(current_row, "stop_loss_price", 0.0), 0.0) if is_add_long else 0.0
        stop_loss_price = round(existing_stop_loss, 4) if existing_stop_loss > 0 else trailing_stop

        repo.upsert_position(
            symbol=intent.symbol,
            strategy_mode=intent.strategy_mode,
            side="LONG",
            quantity=total_qty,
            avg_entry_price=avg_entry_price,
            current_price=fill_price,
            market_value=round(fill_price * total_qty, 4),
            unrealized_pnl=0.0,
            realized_pnl=realized_pnl,
            status="OPEN",
            trailing_stop_pct=trailing_pct,
            trailing_stop_price=trailing_stop,
            high_water_mark=high_water_mark,
            stop_loss_price=stop_loss_price,
        )
        repo.append_trade(
            TradeRecord(
                symbol=intent.symbol,
                strategy_mode=intent.strategy_mode,
                action="ADD" if is_add_long else "OPEN",
                side="LONG",
                quantity=fill_qty,
                price=fill_price,
                realized_pnl=0.0,
                notes=fill_notes,
            )
        )

        broker_result = _submit_to_broker(intent.symbol, fill_qty, "BUY", estimated_price=fill_price)
        broker_info = broker_result if broker_result else {"skipped": True}
        _record_order_event(
            repo.session,
            order_intent_id=order_intent_id,
            client_order_id=client_order_id,
            symbol=intent.symbol,
            event_type=EXECUTION_ORDER_SUBMITTED,
            correlation_id=correlation_id,
            payload={
                "order_intent_id": order_intent_id,
                "client_order_id": client_order_id,
                "symbol": intent.symbol,
                "side": "BUY",
                "qty": fill_qty,
                "broker": broker_info,
                "execution_state": ExecutionStatus.SUBMITTED.value,
            },
        )
        _record_order_event(
            repo.session,
            order_intent_id=order_intent_id,
            client_order_id=client_order_id,
            symbol=intent.symbol,
            event_type=EXECUTION_FILL_RECEIVED,
            correlation_id=correlation_id,
            payload={
                "order_intent_id": order_intent_id,
                "client_order_id": client_order_id,
                "symbol": intent.symbol,
                "side": "BUY",
                "fill": fill_audit,
                "broker": broker_info,
            },
        )
        repo.append_audit_event(
            ExecutionEventRecord(
                event_type="add_long" if is_add_long else "open_long",
                symbol=intent.symbol,
                strategy_mode=intent.strategy_mode,
                correlation_id=correlation_id,
                payload={
                    "price": fill_price,
                    "quantity": fill_qty,
                    "position_total_qty": total_qty,
                    "position_avg_entry_price": avg_entry_price,
                    "fill": fill_audit,
                    "broker": broker_info,
                    "intent": intent.intent,
                    "intent_metadata": intent.metadata if isinstance(intent.metadata, dict) else {},
                },
            )
        )
        _record_portfolio_snapshot_event(
            repo,
            correlation_id=correlation_id,
            snapshot_type="execution_add_long" if is_add_long else "execution_open",
        )
    elif intent.intent == "OPEN_SHORT":
        if not _is_margin_trading_enabled():
            _record_risk_decision_event(
                repo.session,
                signal_id=signal_id,
                symbol=intent.symbol,
                intent=intent.intent,
                side=fill_side,
                decision="rejected",
                approved_qty=None,
                reason_codes=["short_open_blocked"],
                risk_snapshot={"reason": "Cash-only execution blocks opening short positions."},
                correlation_id=correlation_id,
            )
            repo.append_audit_event(ExecutionEventRecord(
                event_type="short_open_blocked",
                symbol=intent.symbol,
                strategy_mode=intent.strategy_mode,
                correlation_id=correlation_id,
                payload={"reason": "Cash-only execution blocks opening short positions."},
            ))
            return

        from backend.app.services.risk_engine import DEFAULT_TRAILING_STOP_PCT

        trailing_pct = DEFAULT_TRAILING_STOP_PCT
        trailing_stop = round(fill_price * (1 + trailing_pct / 100.0), 4)
        repo.upsert_position(
            symbol=intent.symbol, strategy_mode=intent.strategy_mode,
            side="SHORT", quantity=fill_qty, avg_entry_price=fill_price,
            current_price=fill_price, market_value=round(fill_price * fill_qty, 4),
            unrealized_pnl=0.0, realized_pnl=0.0, status="OPEN",
            trailing_stop_pct=trailing_pct, trailing_stop_price=trailing_stop,
            high_water_mark=fill_price, stop_loss_price=trailing_stop,
        )
        repo.append_trade(TradeRecord(
            symbol=intent.symbol, strategy_mode=intent.strategy_mode,
            action="OPEN", side="SHORT", quantity=fill_qty,
            price=fill_price, realized_pnl=0.0, notes=fill_notes,
        ))
        broker_result = _submit_to_broker(intent.symbol, fill_qty, "SELL", estimated_price=fill_price)
        broker_info = broker_result if broker_result else {"skipped": True}
        _record_order_event(
            repo.session,
            order_intent_id=order_intent_id,
            client_order_id=client_order_id,
            symbol=intent.symbol,
            event_type=EXECUTION_ORDER_SUBMITTED,
            correlation_id=correlation_id,
            payload={
                "order_intent_id": order_intent_id,
                "client_order_id": client_order_id,
                "symbol": intent.symbol,
                "side": "SELL",
                "qty": fill_qty,
                "broker": broker_info,
                "execution_state": ExecutionStatus.SUBMITTED.value,
            },
        )
        _record_order_event(
            repo.session,
            order_intent_id=order_intent_id,
            client_order_id=client_order_id,
            symbol=intent.symbol,
            event_type=EXECUTION_FILL_RECEIVED,
            correlation_id=correlation_id,
            payload={
                "order_intent_id": order_intent_id,
                "client_order_id": client_order_id,
                "symbol": intent.symbol,
                "side": "SELL",
                "fill": fill_audit,
                "broker": broker_info,
            },
        )
        repo.append_audit_event(ExecutionEventRecord(
            event_type="open_short", symbol=intent.symbol,
            strategy_mode=intent.strategy_mode, correlation_id=correlation_id,
            payload={"price": fill_price, "quantity": fill_qty, "fill": fill_audit, "broker": broker_info},
        ))
        _record_portfolio_snapshot_event(repo, correlation_id=correlation_id, snapshot_type="execution_open_short")


def refresh_signals(
    symbols,
    mode="classic",
    start_date=None,
    end_date=None,
    auto_execute=True,
    quantity=1.0,
    quantity_map: dict[str, float] | None = None,
    decision_overrides: dict[str, dict] | None = None,
    idempotency_key: str | None = None,
):
    resolved_start_date, resolved_end_date = analysis_window_iso(start_date, end_date)
    normalized_symbols = []
    for symbol in symbols or []:
        normalized_symbol = str(symbol or "").strip().upper()
        if normalized_symbol and normalized_symbol not in normalized_symbols:
            normalized_symbols.append(normalized_symbol)

    # Use the caller-supplied idempotency key as the correlation_id when given;
    # otherwise generate a fresh one.
    correlation_id = str(idempotency_key).strip() if idempotency_key else f"signal-refresh-{uuid4().hex[:12]}"

    # --- kill switch ---------------------------------------------------------
    if is_halted():
        with session_scope() as session:
            repo = ExecutionRepository(session)
            repo.append_audit_event(ExecutionEventRecord(
                event_type="halt_blocked_refresh",
                correlation_id=correlation_id,
                payload={
                    "symbols": normalized_symbols,
                    "mode": mode,
                    "auto_execute": auto_execute,
                    "start_date": resolved_start_date,
                    "end_date": resolved_end_date,
                },
            ))
        log_event(logger, logging.WARNING, "execution.refresh.halted", correlation_id=correlation_id, symbols=len(normalized_symbols))
        return {"halted": True, "correlation_id": correlation_id, "items": [], "portfolio": {}, "alerts": {}, "signals": {}}
    # -------------------------------------------------------------------------

    # --- idempotency check ---------------------------------------------------
    if idempotency_key:
        with session_scope() as session:
            repo = ExecutionRepository(session)
            if repo.has_audit_event("refresh_completed", correlation_id):
                log_event(logger, logging.INFO, "execution.refresh.deduplicated", correlation_id=correlation_id)
                return {
                    "deduplicated": True,
                    "idempotency_key": idempotency_key,
                    "correlation_id": correlation_id,
                    "items": [],
                    "portfolio": get_internal_portfolio(limit=500),
                    "alerts": get_alert_history(limit=20),
                    "signals": get_signal_history(limit=20),
                }
    # -------------------------------------------------------------------------

    items = []
    try:
        auto_trading_runtime = get_auto_trading_config() if auto_execute else {}
    except Exception:
        auto_trading_runtime = {}
    auto_trade_gate_config = _resolve_auto_trade_gate_config(auto_trading_runtime)
    quote_lookup = _build_quote_lookup(normalized_symbols)
    analyzed_symbols, analysis_concurrency = _collect_symbol_analyses(
        normalized_symbols,
        mode,
        resolved_start_date,
        resolved_end_date,
        quote_lookup=quote_lookup,
    )
    log_event(
        logger,
        logging.INFO,
        "execution.refresh.started",
        strategy_mode=mode,
        symbols=len(normalized_symbols),
        auto_execute=auto_execute,
        correlation_id=correlation_id,
        analysis_concurrency=analysis_concurrency,
    )

    normalized_quantity_map = {
        str(symbol or "").strip().upper(): max(_safe_float(value, quantity), 0.0)
        for symbol, value in (quantity_map or {}).items()
        if str(symbol or "").strip()
    }
    normalized_decision_overrides = {
        str(symbol or "").strip().upper(): payload
        for symbol, payload in (decision_overrides or {}).items()
        if str(symbol or "").strip() and isinstance(payload, dict)
    }

    for analyzed in analyzed_symbols:
        normalized_symbol = analyzed["symbol"]
        result = analyzed["result"] or {}
        signal_snapshot = analyzed["signal_snapshot"]
        try:
            with session_scope() as session:
                repo = ExecutionRepository(session)

                if analyzed.get("error") or "error" in result:
                    error_message = analyzed.get("error") or result.get("error") or "signal refresh error"
                    repo.append_alert(AlertRecord(symbol=normalized_symbol, strategy_mode=mode, alert_type="model_status", severity="warning", message=error_message, payload=result))
                    repo.append_audit_event(ExecutionEventRecord(event_type="signal_refresh_error", symbol=normalized_symbol, strategy_mode=mode, correlation_id=correlation_id, payload={"error": error_message, **result}))
                    items.append({"symbol": normalized_symbol, "strategy_mode": mode, "error": error_message})
                    continue

                signal_id = _build_signal_id(normalized_symbol, mode, correlation_id)
                previous_signal = repo.latest_signal(normalized_symbol, mode)
                repo.append_signal(SignalRecord(symbol=normalized_symbol, strategy_mode=mode, signal=signal_snapshot.signal, confidence=signal_snapshot.confidence, price=signal_snapshot.price, reasoning=signal_snapshot.reasoning, payload=signal_snapshot.analysis_payload))
                _record_signal_alerts(repo, mode, signal_snapshot, previous_signal)
                repo.append_audit_event(ExecutionEventRecord(event_type="signal_recorded", symbol=normalized_symbol, strategy_mode=mode, correlation_id=correlation_id, payload=signal_snapshot.model_dump()))
                publish_event(
                    event_type=STRATEGY_SIGNAL_PROPOSED,
                    producer="execution_service",
                    payload={
                        "signal_id": signal_id,
                        "symbol": normalized_symbol,
                        "strategy_mode": mode,
                        **signal_snapshot.model_dump(mode="json"),
                    },
                    correlation_id=correlation_id,
                )
                emit_counter("strategy_signals_total", strategy_mode=mode, signal=signal_snapshot.signal, symbol=normalized_symbol)

                mode_output = result.get(f"{mode}_output") if mode in {"ml", "dl"} else result.get("ensemble_output") if mode == "ensemble" else None
                if isinstance(mode_output, dict) and mode_output.get("error"):
                    repo.append_alert(AlertRecord(symbol=normalized_symbol, strategy_mode=mode, alert_type="model_status", severity="warning", message=f"{normalized_symbol} {mode} output degraded", payload=mode_output))

                decision_override = normalized_decision_overrides.get(normalized_symbol, {})
                requested_action_override = str(decision_override.get("requested_execution_action") or "").strip().upper()
                override_requires_execution = requested_action_override in {"OPEN_LONG", "ADD_LONG", "REDUCE_LONG", "EXIT_LONG"}
                should_auto_execute = auto_execute and (signal_snapshot.signal in {"BUY", "SELL"} or override_requires_execution)
                passed_signal_gate = _is_auto_executable_signal(signal_snapshot, auto_trading_runtime)

                if should_auto_execute and (override_requires_execution or passed_signal_gate):
                    effective_quantity = normalized_quantity_map.get(normalized_symbol, quantity)
                    command = ExecutionCommand(
                        symbol=normalized_symbol,
                        strategy_mode=mode,
                        quantity=effective_quantity,
                        auto_execute=auto_execute,
                        correlation_id=correlation_id,
                    )
                    current_row = repo.get_open_position_row(normalized_symbol, mode)
                    current_position = None if current_row is None else PositionState(id=current_row.id, symbol=current_row.symbol, strategy_mode=current_row.strategy_mode, side=current_row.side, quantity=current_row.quantity, avg_entry_price=current_row.avg_entry_price, current_price=current_row.current_price, market_value=current_row.market_value or 0.0, unrealized_pnl=current_row.unrealized_pnl or 0.0, realized_pnl=current_row.realized_pnl or 0.0, status=current_row.status, opened_at=current_row.opened_at, updated_at=current_row.updated_at)

                    if decision_override:
                        intents = _build_trade_intents_from_decision(
                            current_position,
                            signal_snapshot,
                            command.quantity,
                            decision_override,
                            auto_trading_runtime,
                        )
                    else:
                        intents = _build_trade_intents(current_position, signal_snapshot, command.quantity, auto_trading_runtime)

                    for intent in intents:
                        _apply_trade_intent(repo, current_row, intent, correlation_id=correlation_id, signal_id=signal_id)
                        if intent.intent.startswith("CLOSE"):
                            current_row = None
                elif should_auto_execute:
                    repo.append_alert(
                        AlertRecord(
                            symbol=normalized_symbol,
                            strategy_mode=mode,
                            alert_type="auto_trade_skipped_low_strength",
                            severity="info",
                            message=(
                                f"{normalized_symbol} auto-execution skipped: signal strength below gate "
                                f"(min_conf={auto_trade_gate_config['min_signal_confidence']}, "
                                f"min_score={auto_trade_gate_config['min_ensemble_score']}, "
                                f"min_agreement={auto_trade_gate_config['min_agreement']})."
                            ),
                            payload={
                                "signal": signal_snapshot.signal,
                                "confidence": signal_snapshot.confidence,
                                "trade_direction": auto_trade_gate_config["trade_direction"],
                                "analysis": signal_snapshot.analysis_payload.get("analysis")
                                if isinstance(signal_snapshot.analysis_payload, dict)
                                else None,
                            },
                        )
                    )

                item_payload = {
                    "symbol": normalized_symbol,
                    "strategy_mode": mode,
                    "signal": signal_snapshot.signal,
                    "confidence": signal_snapshot.confidence,
                    "price": signal_snapshot.price,
                    "reasoning": signal_snapshot.reasoning,
                }
                if decision_override:
                    item_payload.update(
                        {
                            "portfolio_brain_requested_action": decision_override.get("requested_execution_action"),
                            "portfolio_brain_decision_code": decision_override.get("decision_outcome_code"),
                            "portfolio_brain_decision_detail": decision_override.get("decision_outcome_detail"),
                            "target_position_pct": decision_override.get("target_position_pct"),
                            "current_position_pct": decision_override.get("current_position_pct"),
                            "desired_delta_pct": decision_override.get("desired_delta_pct"),
                            "opportunity_score": decision_override.get("opportunity_score"),
                            "conviction_tier": decision_override.get("conviction_tier"),
                            "execution_priority": decision_override.get("execution_priority"),
                            "execution_priority_band": decision_override.get("execution_priority_band"),
                            "funded_partially": decision_override.get("funded_partially"),
                            "funding_status": decision_override.get("funding_status"),
                            "funding_ratio": decision_override.get("funding_ratio"),
                            "partial_funding_reason": decision_override.get("partial_funding_reason"),
                            "requested_order_qty": decision_override.get("requested_order_qty"),
                            "approved_order_qty": decision_override.get("approved_order_qty"),
                            "approved_position_pct": decision_override.get("approved_position_pct"),
                            "order_style_preference": decision_override.get("order_style_preference"),
                            "execution_skip_reason": decision_override.get("execution_skip_reason"),
                            "proposed_order_qty": decision_override.get("proposed_order_qty"),
                        }
                    )
                items.append(item_payload)
        except Exception as exc:
            log_event(logger, logging.WARNING, "execution.refresh.symbol_failed", symbol=normalized_symbol, strategy_mode=mode, error=str(exc), correlation_id=correlation_id)
            with session_scope() as session:
                repo = ExecutionRepository(session)
                repo.append_alert(AlertRecord(symbol=normalized_symbol, strategy_mode=mode, alert_type="model_status", severity="warning", message=f"{normalized_symbol} signal refresh failed", payload={"error": str(exc)}))
                repo.append_audit_event(ExecutionEventRecord(event_type="signal_refresh_exception", symbol=normalized_symbol, strategy_mode=mode, correlation_id=correlation_id, payload={"error": str(exc)}))
            items.append({"symbol": normalized_symbol, "strategy_mode": mode, "error": str(exc)})

    with session_scope() as session:
        repo = ExecutionRepository(session)
        repo.append_audit_event(ExecutionEventRecord(
            event_type="refresh_completed",
            correlation_id=correlation_id,
            payload={
                "symbols": normalized_symbols,
                "mode": mode,
                "start_date": resolved_start_date,
                "end_date": resolved_end_date,
                "results": len(items),
                "analysis_concurrency": analysis_concurrency,
            },
        ))

    portfolio = get_internal_portfolio(limit=500)
    alerts = get_alert_history(limit=20)
    signals = get_signal_history(limit=20)

    log_event(logger, logging.INFO, "execution.refresh.completed", strategy_mode=mode, results=len(items), correlation_id=correlation_id)
    return {"items": items, "portfolio": portfolio, "alerts": alerts, "signals": signals, "correlation_id": correlation_id}


def _broker_active_source(broker: dict) -> str:
    return "broker_live"


def _broker_environment_label(broker: dict) -> str:
    return "external_live"


def _normalize_broker_order_record(item: dict, *, broker_source: str, broker_environment: str) -> dict:
    raw_status = str(item.get("status") or "").strip()
    order_type = str(item.get("type") or item.get("order_type") or "MARKET").strip().upper()
    quantity = _safe_float(item.get("qty"), _safe_float(item.get("quantity"), 0.0))
    filled_qty = _safe_float(item.get("filled_qty"), 0.0)
    filled_avg_price = _safe_float(item.get("filled_avg_price"), 0.0) or None
    limit_price = _safe_float(item.get("limit_price"), 0.0) or None
    return {
        "id": item.get("id"),
        "client_order_id": item.get("client_order_id"),
        "portfolio_source": broker_source,
        "symbol": str(item.get("symbol") or "").strip().upper(),
        "side": str(item.get("side") or "").strip().upper(),
        "order_type": order_type,
        "type": order_type,
        "status": raw_status.upper() or "UNKNOWN",
        "quantity": quantity,
        "qty": quantity,
        "filled_qty": filled_qty,
        "fill_price": filled_avg_price,
        "filled_avg_price": filled_avg_price,
        "limit_price": limit_price,
        "submitted_at": item.get("submitted_at"),
        "updated_at": item.get("updated_at"),
        "notes": f"Broker-managed order from the external {broker_environment} account.",
        "raw_status": raw_status.lower() or None,
        "execution_source": "broker",
        "order_source": "broker",
        "broker_environment": broker_environment,
        "broker_execution_mode": "broker_managed",
        "internal_paper_enabled": False,
    }


def _build_broker_managed_trade_items(broker: dict, *, limit: int = 100) -> list[dict]:
    broker_source = _broker_active_source(broker)
    broker_environment = _broker_environment_label(broker)
    items: list[dict] = []
    for order in list(broker.get("orders") or []):
        normalized = _normalize_broker_order_record(
            order,
            broker_source=broker_source,
            broker_environment=broker_environment,
        )
        raw_status = str(normalized.get("raw_status") or "").lower()
        if raw_status not in {"filled", "partially_filled"} and float(normalized.get("filled_qty") or 0.0) <= 0:
            continue
        items.append(
            {
                "id": normalized.get("id"),
                "portfolio_source": broker_source,
                "symbol": normalized.get("symbol"),
                "side": normalized.get("side"),
                "quantity": float(normalized.get("filled_qty") or normalized.get("qty") or 0.0),
                "price": normalized.get("filled_avg_price") or 0.0,
                "realized_pnl": 0.0,
                "status": normalized.get("status"),
                "created_at": normalized.get("updated_at") or normalized.get("submitted_at"),
                "notes": f"Broker-managed fill from the external {broker_environment} account.",
                "trade_source": "broker",
                "broker_environment": broker_environment,
                "internal_paper_enabled": False,
            }
        )
    items.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return items[:limit]


def get_internal_portfolio(limit: int = 500) -> dict:
    broker = get_broker_summary(refresh=False)
    broker_source = _broker_active_source(broker)
    broker_environment = _broker_environment_label(broker)
    account = broker.get("account") or {}
    positions: list[dict] = []
    for index, item in enumerate(list(broker.get("positions") or [])[:limit], start=1):
        qty = abs(_safe_float(item.get("qty"), 0.0))
        side = str(item.get("side") or "").strip().upper() or "LONG"
        if qty <= 0 or side not in {"LONG", "SHORT"}:
            continue
        current_price = _safe_float(item.get("current_price"), _safe_float(item.get("avg_entry_price"), 0.0))
        positions.append(
            {
                "id": f"broker-position-{index}",
                "portfolio_source": broker_source,
                "symbol": str(item.get("symbol") or "").strip().upper(),
                "strategy_mode": "broker",
                "side": side,
                "quantity": qty,
                "avg_entry_price": _safe_float(item.get("avg_entry_price"), 0.0),
                "current_price": current_price,
                "market_value": abs(_safe_float(item.get("market_value"), current_price * qty)),
                "unrealized_pnl": _safe_float(item.get("unrealized_pnl"), 0.0),
                "realized_pnl": 0.0,
                "status": "OPEN",
                "stop_loss_price": None,
                "trailing_stop_pct": None,
                "trailing_stop_price": None,
                "high_water_mark": None,
                "opened_at": None,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )
    trade_items = _build_broker_managed_trade_items(broker, limit=200)
    total_market_value = round(sum(float(item.get("market_value") or 0.0) for item in positions), 4)
    total_unrealized_pnl = round(sum(float(item.get("unrealized_pnl") or 0.0) for item in positions), 4)
    cash_balance = round(_safe_float(account.get("cash"), 0.0), 4)
    total_equity = round(
        _safe_float(account.get("equity"), _safe_float(account.get("portfolio_value"), cash_balance + total_market_value)),
        4,
    )
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "active_source": broker_source,
        "broker_managed_only": True,
        "internal_paper_enabled": False,
        "account_source": "broker",
        "position_source": "broker",
        "order_source": "broker",
        "execution_source": "broker",
        "broker_execution_mode": "broker_managed",
        "broker_environment": broker_environment,
        "items": positions,
        "positions": positions,
        "count": len(positions),
        "summary": {
            "active_source": broker_source,
            "provider": broker.get("provider", "none"),
            "connected": bool(broker.get("connected")),
            "mode": broker.get("mode", "live"),
            "open_positions": len(positions),
            "open_orders": len(
                [
                    order
                    for order in list(broker.get("orders") or [])
                    if str(order.get("status") or "").strip().lower()
                    not in {"filled", "canceled", "cancelled", "expired", "rejected", "replaced", "suspended"}
                ]
            ),
            "total_market_value": total_market_value,
            "invested_cost": round(sum(_safe_float(item.get("cost_basis"), 0.0) for item in broker.get("positions") or []), 4),
            "cash_balance": cash_balance,
            "total_equity": total_equity,
            "portfolio_value": round(_safe_float(account.get("portfolio_value"), total_equity), 4),
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_realized_pnl": 0.0,
            "total_trades": len(trade_items),
            "starting_cash": total_equity,
            "win_rate_pct": None,
        },
    }


def sync_internal_positions_from_broker(strategy_mode: str = "classic") -> dict:
    """Compatibility shim for legacy callers.

    Internal paper positions are no longer synchronized or treated as the
    authoritative portfolio. The broker account is the only source of truth.
    """
    normalized_mode = str(strategy_mode or "classic").strip().lower() or "classic"
    broker = get_broker_summary(refresh=True)
    broker_positions = list(broker.get("positions") or [])
    short_symbols = [
        str(item.get("symbol") or "").strip().upper()
        for item in broker_positions
        if str(item.get("side") or "").strip().upper() == "SHORT"
    ]
    with session_scope() as session:
        repo = ExecutionRepository(session)
        repo.append_audit_event(
            ExecutionEventRecord(
                event_type="broker_positions_sync_deprecated",
                source="broker_sync",
                portfolio_source=_broker_active_source(broker),
                strategy_mode=normalized_mode,
                payload={
                    "broker_provider": broker.get("provider"),
                    "positions": len(broker_positions),
                    "short_symbols": short_symbols,
                    "internal_paper_enabled": False,
                    "detail": "Broker-managed positions are authoritative; internal sync is disabled.",
                },
            )
        )
    return {
        "ok": True,
        "strategy_mode": normalized_mode,
        "positions": len(broker_positions),
        "short_positions": len(short_symbols),
        "short_symbols": short_symbols,
        "closed_positions": 0,
        "closed_symbols": [],
        "sync_mode": "broker_managed_noop",
        "internal_paper_enabled": False,
    }


def _parse_fill_details_from_notes(notes: str | None) -> dict | None:
    """Extract structured fill details from the pipe-delimited notes string.

    Notes format (from paper_fill_engine):
      ``ref=150.00 | spread=+0.0750 | slip=+0.0750 | fill=150.1500 | qty=10/10 | fee=0.0500``
    """
    if not notes:
        return None
    import re  # noqa: PLC0415
    parts = [p.strip() for p in notes.split("|")]
    result: dict = {}
    for part in parts:
        m = re.match(r"ref=([\d.]+)", part)
        if m:
            result["reference_price"] = float(m.group(1))
            continue
        m = re.match(r"spread=([+\-]?[\d.]+)", part)
        if m:
            result["spread_adj"] = float(m.group(1))
            continue
        m = re.match(r"slip=([+\-]?[\d.]+)", part)
        if m:
            result["slippage_adj"] = float(m.group(1))
            continue
        m = re.match(r"fill=([\d.]+)", part)
        if m:
            result["fill_price"] = float(m.group(1))
            continue
        m = re.match(r"qty=(\d+)/(\d+)", part)
        if m:
            filled = int(m.group(1))
            requested = int(m.group(2))
            result["filled_quantity"] = filled
            result["requested_quantity"] = requested
            result["fill_ratio"] = round(filled / requested, 4) if requested > 0 else 1.0
            result["is_partial"] = filled < requested
            continue
        m = re.match(r"fee=([\d.]+)", part)
        if m:
            result["fee_amount"] = float(m.group(1))
            continue
    return result if result else None


def _enrich_with_fill_details(item: dict) -> dict:
    """Add ``fill_details`` key to an order or trade dict by parsing notes."""
    notes = item.get("notes") or ""
    fill_details = _parse_fill_details_from_notes(notes)
    if fill_details:
        item["fill_details"] = fill_details
    return item


def get_trade_history(limit=100):
    broker = get_broker_summary(refresh=False)
    items = _build_broker_managed_trade_items(broker, limit=limit)
    return {
        "items": items,
        "count": len(items),
        "trade_source": "broker",
        "broker_environment": _broker_environment_label(broker),
        "broker_execution_mode": "broker_managed",
        "internal_paper_enabled": False,
    }


def _compact_signal(item: dict) -> dict:
    """Drop the heavy `payload` blob for list views; keep only a lightweight summary.

    The raw `payload` can exceed 250KB per signal (full indicator snapshots),
    which balloons list responses to 30MB+ and chokes the browser. Callers that
    need the full payload can fetch a specific signal by id.
    """
    payload = item.get("payload") or {}
    analysis = payload.get("analysis") if isinstance(payload, dict) else None
    compact_payload = None
    if isinstance(analysis, dict):
        keep = ("close", "rsi14", "macd", "macd_signal", "adx14", "atr14")
        compact_payload = {"analysis": {k: analysis.get(k) for k in keep if k in analysis}}
    item = dict(item)
    item["payload"] = compact_payload
    return item


def get_signal_history(limit=100, *, compact: bool = True):
    with session_scope() as session:
        repo = ExecutionRepository(session)
        rows = [row.model_dump(mode="json") for row in repo.list_signals(limit=limit)]
        if compact:
            rows = [_compact_signal(r) for r in rows]
        return {"items": rows, "count": len(rows)}


def get_alert_history(limit=100, severity: str | None = None):
    with session_scope() as session:
        repo = ExecutionRepository(session)
        rows = repo.list_alerts(limit=limit, severity=severity)
        return {"items": [row.model_dump(mode="json") for row in rows], "count": len(rows)}


def get_execution_audit(limit=100, symbol: str | None = None):
    with session_scope() as session:
        repo = ExecutionRepository(session)
        rows = repo.list_audit_events(limit=limit, symbol=symbol)
        return {"items": [row.model_dump(mode="json") for row in rows], "count": len(rows)}


def list_paper_orders(limit: int = 100, status: str | None = "OPEN") -> dict:
    broker = get_broker_summary(refresh=False)
    broker_source = _broker_active_source(broker)
    broker_environment = _broker_environment_label(broker)
    terminal_statuses = {"filled", "canceled", "cancelled", "expired", "rejected", "replaced", "suspended"}
    items = [
        _normalize_broker_order_record(
            item,
            broker_source=broker_source,
            broker_environment=broker_environment,
        )
        for item in list(broker.get("orders") or [])
    ]
    normalized_status = str(status or "").strip().upper()
    if normalized_status == "OPEN":
        items = [item for item in items if str(item.get("raw_status") or "").lower() not in terminal_statuses]
    elif normalized_status:
        items = [item for item in items if str(item.get("status") or "").upper() == normalized_status]
    items = items[:limit]
    return {
        "items": items,
        "count": len(items),
        "order_source": "broker",
        "broker_environment": broker_environment,
        "broker_execution_mode": "broker_managed",
        "internal_paper_enabled": False,
    }


def create_paper_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    limit_price: float | None = None,
    strategy_mode: str | None = "manual",
    notes: str | None = None,
    client_order_id: str | None = None,
    trace_id: str | None = None,
) -> dict:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_side = str(side or "").strip().upper()
    normalized_order_type = str(order_type or "market").strip().lower()
    trace_context = build_trace_context(trace_id)
    trace_id = trace_context["correlation_id"]
    if normalized_side not in {"BUY", "SELL"}:
        raise ValueError("Order side must be BUY or SELL.")
    if normalized_order_type not in {"market", "limit"}:
        raise ValueError("Order type must be market or limit.")
    if float(quantity or 0.0) <= 0:
        raise ValueError("Order quantity must be greater than zero.")
    if normalized_order_type == "limit" and limit_price in (None, 0):
        raise ValueError("Limit orders require a limit_price.")

    # --- kill switch ---------------------------------------------------------
    if is_halted():
        correlation_id = f"broker-order-{uuid4().hex[:12]}"
        with session_scope() as session:
            repo = ExecutionRepository(session)
            repo.append_audit_event(ExecutionEventRecord(
                event_type="halt_blocked_order",
                symbol=normalized_symbol,
                strategy_mode=strategy_mode,
                correlation_id=correlation_id,
                payload={"side": normalized_side, "quantity": quantity, "order_type": normalized_order_type},
            ))
        log_event(logger, logging.WARNING, "execution.order.halted", symbol=normalized_symbol, side=normalized_side)
        raise ExecutionHaltedError("Execution is currently halted. Clear the halt before submitting new orders.")
    # -------------------------------------------------------------------------

    from backend.app.services.broker.registry import get_broker_provider

    provider = get_broker_provider()
    broker_status = provider.get_status()
    if not bool(broker_status.get("connected")):
        raise ValueError(broker_status.get("detail") or "Broker integration is unavailable.")

    result = provider.submit_order(
        symbol=normalized_symbol,
        qty=float(quantity),
        side=normalized_side,
        order_type=normalized_order_type,
        time_in_force="day",
        limit_price=float(limit_price) if limit_price else None,
        estimated_price=float(limit_price) if limit_price else None,
    )
    if not bool(result.get("ok")):
        raise ValueError(result.get("error") or "Broker order submission failed.")

    broker_environment = "external_live"
    order_payload = _normalize_broker_order_record(
        result.get("order") or {},
        broker_source=_broker_active_source(broker_status),
        broker_environment=broker_environment,
    )
    order_payload.update(
        {
            "strategy_mode": strategy_mode,
            "notes": notes or f"Broker-managed submission routed through the deprecated trading compatibility endpoint.",
            "deprecated_internal_paper_route": True,
            "paper_route_disabled": True,
            "broker_managed_only": True,
            "execution_source": "broker",
            "account_source": "broker",
            "position_source": "broker",
            "order_source": "broker",
        }
    )
    with session_scope() as session:
        repo = ExecutionRepository(session)
        repo.append_audit_event(
            ExecutionEventRecord(
                event_type="broker_order_submitted_via_compat_route",
                symbol=normalized_symbol,
                strategy_mode=strategy_mode,
                correlation_id=trace_id,
                payload={
                    "symbol": normalized_symbol,
                    "side": normalized_side,
                    "quantity": float(quantity),
                    "order_type": normalized_order_type,
                    "limit_price": float(limit_price) if limit_price else None,
                    "broker_environment": broker_environment,
                    "order": order_payload,
                    "deprecated_internal_paper_route": True,
                    "internal_paper_enabled": False,
                },
            )
        )
    return order_payload


def preview_paper_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    limit_price: float | None = None,
    strategy_mode: str | None = "manual",
    notes: str | None = None,
) -> ExecutionPreview:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_side = str(side or "").strip().upper()
    normalized_order_type = str(order_type or "market").strip().lower()
    preview_id = f"deprecated-{uuid4().hex[:16]}"
    trace_id = f"trace-{uuid4().hex[:16]}"
    reason = (
        "Internal preview/confirm simulation is disabled. "
        "The platform now uses broker-managed execution only."
    )
    return ExecutionPreview(
        preview_id=preview_id,
        trace_id=trace_id,
        symbol=normalized_symbol,
        side=normalized_side,
        quantity=float(quantity),
        order_type=normalized_order_type,
        reference_price=0.0,
        estimated_fill_price=0.0,
        estimated_fee=0.0,
        estimated_slippage=0.0,
        estimated_spread=0.0,
        estimated_total_cost=0.0,
        halt_status=get_halt_status(),
        risk_check={"allowed": False, "deprecated": True},
        is_safe_to_execute=False,
        blocking_reasons=[reason],
        warnings=["Submit broker-managed orders directly through the broker execution route."],
        fill_preview={},
        expires_at=None,
    )


def confirm_paper_order(preview_id: str) -> ExecutionConfirmResult:
    normalized_preview_id = str(preview_id or "").strip()
    correlation_id = f"confirm-{uuid4().hex[:12]}"
    return ExecutionConfirmResult(
        client_order_id="",
        preview_id=normalized_preview_id,
        symbol="",
        status="REJECTED",
        blocked_reason=(
            "Internal preview/confirm execution is disabled. "
            "Use the broker-managed order submission path instead."
        ),
        audit_correlation_id=correlation_id,
    )


def cancel_paper_order(order_id: str) -> dict:
    from backend.app.services.broker.registry import get_broker_provider

    normalized_order_id = str(order_id or "").strip()
    if not normalized_order_id:
        raise LookupError("Broker order id is required.")
    provider = get_broker_provider()
    broker_status = provider.get_status()
    if not bool(broker_status.get("connected")):
        raise LookupError(broker_status.get("detail") or "Broker integration is unavailable.")
    result = provider.cancel_order(normalized_order_id)
    if not bool(result.get("ok")):
        raise ValueError(result.get("error") or "Broker order cancellation failed.")
    with session_scope() as session:
        repo = ExecutionRepository(session)
        repo.append_audit_event(
            ExecutionEventRecord(
                event_type="broker_order_canceled_via_compat_route",
                symbol="",
                strategy_mode="manual",
                correlation_id=f"broker-cancel-{normalized_order_id}",
                payload={
                    "order_id": normalized_order_id,
                    "broker_environment": "external_live",
                    "deprecated_internal_paper_route": True,
                    "internal_paper_enabled": False,
                },
            )
        )
    return {
        "ok": True,
        "id": normalized_order_id,
        "status": "CANCELED",
        "order_source": "broker",
        "execution_source": "broker",
        "broker_execution_mode": "broker_managed",
        "broker_environment": "external_live",
        "deprecated_internal_paper_route": True,
        "internal_paper_enabled": False,
    }


def get_paper_control_panel(*, broker_refresh: bool = False, limit: int = 50) -> dict:
    portfolio = get_internal_portfolio(limit=500)
    open_orders = list_paper_orders(limit=limit, status="OPEN")
    all_orders = list_paper_orders(limit=limit, status=None)
    trades = get_trade_history(limit=limit)
    signals = get_signal_history(limit=limit)
    alerts = get_alert_history(limit=limit)
    audit = get_execution_audit(limit=limit)
    broker = get_broker_summary(refresh=broker_refresh)

    return {
        "broker_managed_only": True,
        "internal_paper_enabled": False,
        "account_source": "broker",
        "position_source": "broker",
        "order_source": "broker",
        "execution_source": "broker",
        "broker_execution_mode": "broker_managed",
        "broker_environment": _broker_environment_label(broker),
        "detail": "Internal simulation is disabled. This control panel is backed by the external broker account.",
        "broker": broker,
        "portfolio": portfolio,
        "open_orders": open_orders,
        "orders": all_orders,
        "trades": trades,
        "signals": signals,
        "alerts": alerts,
        "audit": audit,
        "summary": {
            "open_positions": portfolio.get("summary", {}).get("open_positions", 0),
            "open_orders": open_orders.get("count", 0),
            "recent_trades": len(trades.get("items", [])),
            "recent_alerts": alerts.get("count", 0),
            "broker_connected": bool(broker.get("connected")),
            "broker_mode": broker.get("mode") or "live",
        },
    }
