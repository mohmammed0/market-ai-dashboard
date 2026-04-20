from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import logging
from time import perf_counter, sleep
from uuid import uuid4

from backend.app.application.alerts.service import list_alert_history
from backend.app.application.broker.service import get_broker_summary
from backend.app.application.model_lifecycle.service import (
    promote_model_run,
    review_model_promotion,
    train_dl_models,
    train_ml_models,
)
from backend.app.application.portfolio.service import get_portfolio_exposure
from backend.app.config import (
    AUTOMATION_ALERT_SYMBOL_LIMIT,
    AUTOMATION_DEFAULT_PRESET,
    AUTOMATION_SYMBOL_LIMIT,
    AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT,
    AUTONOMOUS_HISTORY_LOOKBACK_DAYS,
    AUTONOMOUS_INCLUDE_DL,
    AUTONOMOUS_REFRESH_UNIVERSE,
    AUTONOMOUS_TRAIN_SYMBOL_LIMIT,
    DEFAULT_SAMPLE_SYMBOLS,
    ENABLE_AUTO_RETRAIN,
    ENABLE_AUTONOMOUS_CYCLE,
    AUTO_TRADING_ENABLED,
    AUTO_TRADING_ANALYSIS_LOOKBACK_DAYS,
    AUTO_TRADING_NOTIONAL_PER_TRADE,
    AUTO_TRADING_QUANTITY,
    AUTO_TRADING_STRATEGY_MODE,
    AUTO_TRADING_SYMBOL_LIMIT,
    AUTO_TRADING_USE_FULL_PORTFOLIO,
    LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
    RISK_MAX_TRADE_PCT,
)
from backend.app.core.date_defaults import analysis_window_iso, training_window_iso
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.models import AutomationArtifact, AutomationRun, MarketUniverseSymbol
from backend.app.services.advanced_alerts import generate_advanced_alerts
from backend.app.services.auto_trading_governor import (
    acquire_auto_trading_cycle_lease,
    evaluate_daily_loss_guard,
    release_auto_trading_cycle_lease,
)
from backend.app.services.breadth_engine import compute_market_breadth, compute_sector_rotation
from backend.app.services.continuous_learning import get_continuous_learning_runtime_snapshot
from backend.app.services.market_data import SOURCE_DIR, fetch_quote_snapshots, load_history
from backend.app.services.market_universe import refresh_market_universe, resolve_universe_preset
from backend.app.services.smart_watchlists import build_dynamic_watchlists
from backend.app.services.signal_runtime import build_smart_analysis, extract_signal_view
from backend.app.services.storage import dumps_json, loads_json, session_scope
from backend.app.services.trade_journal import list_trade_journal_entries
from backend.app.services.auto_trading_diagnostics import (
    build_auto_trading_diagnostics_payload,
    cleanup_auto_trading_diagnostics_artifacts,
)
from backend.app.services.analysis_engines import get_analysis_engines_status
from backend.app.services.portfolio_brain import build_portfolio_brain_payload
from backend.app.services.market_session_intelligence import (
    get_market_session_snapshot,
    normalize_session_state,
    session_matches,
)
from backend.app.services.kronos_intelligence import kronos_status, warm_kronos, run_kronos_batch

logger = get_logger(__name__)

_RECON_TRACKABLE_ENGINE_STATES = {
    "submitted_to_execution_engine",
    "broker_submission_pending",
    "broker_submitted",
    "broker_accepted",
    "partially_filled",
}
_RECON_TERMINAL_LIFECYCLE = {"filled", "rejected", "cancelled", "expired"}
_RECON_TERMINAL_FINAL = {"filled", "rejected", "cancelled", "expired", "skipped", "exhausted_retries"}
_RECON_CAPITAL_RELEASE_ACTIONS = {"REDUCE_LONG", "EXIT_LONG", "CLOSE_LONG", "CLOSE_SHORT"}
_RECON_CAPITAL_DEPLOY_ACTIONS = {"OPEN_LONG", "ADD_LONG"}

JOB_NAMES = {
    "market_cycle": "Market Cycle",
    "alert_cycle": "Alert Cycle",
    "breadth_cycle": "Breadth Cycle",
    "retrain_cycle": "Retrain Cycle",
    "autonomous_cycle": "Autonomous Cycle",
    "daily_summary": "Daily Summary",
    "auto_trading_cycle": "Auto Trading Cycle",
}


def _normalize_auto_trading_strategy_mode(value: str | None) -> str:
    normalized = str(value or AUTO_TRADING_STRATEGY_MODE).strip().lower()
    return normalized if normalized in {"classic", "ml", "dl", "ensemble"} else AUTO_TRADING_STRATEGY_MODE


def _normalize_auto_trading_trade_direction(value: str | None) -> str:
    normalized = str(value or "both").strip().lower()
    return normalized if normalized in {"both", "long_only", "short_only"} else "both"


def _auto_trading_include_dl(strategy_mode: str) -> bool:
    normalized_mode = _normalize_auto_trading_strategy_mode(strategy_mode)
    return LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL or normalized_mode in {"dl", "ensemble"}


def _auto_trading_signal_actionable(signal_value: str, current_side: str | None, *, trade_direction: str, margin_enabled: bool) -> bool:
    normalized_signal = str(signal_value or "").strip().upper()
    normalized_side = str(current_side or "").strip().upper()
    normalized_direction = _normalize_auto_trading_trade_direction(trade_direction)
    allow_long_entries = normalized_direction in {"both", "long_only"}
    allow_short_entries = normalized_direction in {"both", "short_only"} and margin_enabled

    if normalized_signal == "BUY":
        return normalized_side == "SHORT" or allow_long_entries
    if normalized_signal == "SELL":
        return normalized_side == "LONG" or allow_short_entries
    return False


def _training_overlap_guard() -> dict | None:
    snapshot = get_continuous_learning_runtime_snapshot()
    owner = snapshot.get("owner") or {}
    if snapshot.get("runtime_state") not in {"starting", "running"}:
        return None
    if not owner.get("ownership_active"):
        return None
    return {
        "status": "guarded",
        "reason": "Skipped model training because the continuous learning worker is currently active.",
        "continuous_learning": {
            "runtime_state": snapshot.get("runtime_state"),
            "worker_id": owner.get("worker_id"),
            "pid": owner.get("pid"),
        },
    }


def _utc_today_iso() -> str:
    return datetime.utcnow().date().isoformat()


def _analysis_window() -> tuple[str, str]:
    return analysis_window_iso()


def _training_window() -> tuple[str, str]:
    return training_window_iso()


def _available_local_symbols() -> set[str]:
    if not SOURCE_DIR.exists():
        return set()
    return {
        path.stem.upper()
        for path in SOURCE_DIR.glob("*.csv")
        if path.is_file()
    }


def _preferred_local_symbols(preset: str) -> list[str]:
    local_symbols = sorted(_available_local_symbols())
    if not local_symbols:
        return []

    normalized_preset = str(preset or AUTOMATION_DEFAULT_PRESET).strip().upper()
    with session_scope() as session:
        query = session.query(MarketUniverseSymbol.symbol).filter(
            MarketUniverseSymbol.active.is_(True),
            MarketUniverseSymbol.is_test_issue.is_(False),
            MarketUniverseSymbol.symbol.in_(local_symbols),
        )
        if normalized_preset == "NASDAQ":
            query = query.filter(MarketUniverseSymbol.exchange == "NASDAQ")
        elif normalized_preset == "NYSE":
            query = query.filter(MarketUniverseSymbol.exchange.in_(["NYSE", "NYSE American", "NYSE Arca"]))
        elif normalized_preset == "ETF_ONLY":
            query = query.filter(MarketUniverseSymbol.is_etf.is_(True))
        rows = query.order_by(MarketUniverseSymbol.symbol.asc()).all()
    return [row[0] for row in rows]


def _select_symbols_for_cycle(preset: str, universe_symbols: list[str], desired_count: int) -> list[str]:
    desired_count = max(int(desired_count or 0), 1)
    preferred = _preferred_local_symbols(preset)
    if preferred:
        return preferred[:desired_count]
    fallback = [symbol for symbol in universe_symbols if symbol not in preferred]
    return fallback[:desired_count]


def _rotate_symbol_batch(symbols: list[str], desired_count: int) -> tuple[list[str], dict]:
    desired_count = max(int(desired_count or 0), 1)
    cleaned = [str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()]
    if not cleaned:
        return [], {"offset": 0, "next_offset": 0, "pool_size": 0, "batch_size": desired_count}

    from backend.app.services.runtime_settings import get_runtime_setting_value, set_runtime_setting_value

    pool_size = len(cleaned)
    try:
        offset = int(get_runtime_setting_value("auto_trading.rotation_cursor") or 0) % pool_size
    except Exception:
        offset = 0

    batch: list[str] = []
    for index in range(min(desired_count, pool_size)):
        batch.append(cleaned[(offset + index) % pool_size])

    next_offset = (offset + len(batch)) % pool_size
    try:
        set_runtime_setting_value("auto_trading.rotation_cursor", next_offset)
    except Exception:
        pass

    return batch, {
        "offset": offset,
        "next_offset": next_offset,
        "pool_size": pool_size,
        "batch_size": len(batch),
    }


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _normalize_symbol(value: str | None) -> str:
    return str(value or "").strip().upper()


def _normalize_broker_status(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _map_broker_lifecycle(status: str, filled_qty: float, requested_qty: float) -> str:
    normalized = _normalize_broker_status(status)
    requested = max(_safe_float(requested_qty), 0.0)
    filled = max(_safe_float(filled_qty), 0.0)

    if normalized in {"filled", "fill", "executed"}:
        return "filled"
    if normalized in {"partially_filled", "partial_fill", "partial"}:
        return "partially_filled"
    if normalized in {"rejected", "failed", "error"}:
        return "rejected"
    if normalized in {"canceled", "cancelled"}:
        return "cancelled"
    if normalized in {"expired"}:
        return "expired"
    if normalized in {"accepted", "acknowledged", "new"}:
        return "broker_accepted"
    if normalized in {"pending", "open", "queued", "submitted"}:
        return "broker_submission_pending"
    if filled > 0 and requested > 0:
        if filled + 1e-6 >= requested:
            return "filled"
        return "partially_filled"
    return "broker_submission_pending"


def _execution_final_from_lifecycle(lifecycle: str) -> str:
    if lifecycle in {"filled", "partially_filled", "rejected", "cancelled", "expired", "broker_accepted"}:
        return lifecycle
    if lifecycle == "broker_submission_pending":
        return "broker_submission_pending"
    return "submitted_to_execution_engine"


def _timeline_append_unique(timeline: list[dict], event: dict) -> None:
    if not isinstance(event, dict):
        return
    key = (
        str(event.get("event") or ""),
        str(event.get("queue_item_id") or ""),
        str(event.get("symbol") or ""),
        str(event.get("action") or ""),
        str(event.get("at") or ""),
        str(event.get("reason") or ""),
        str(event.get("dependency_outcome") or ""),
        str(event.get("broker_lifecycle_status") or ""),
        str(event.get("recompute_reason") or ""),
    )
    for existing in reversed(timeline[-120:]):
        existing_key = (
            str(existing.get("event") or ""),
            str(existing.get("queue_item_id") or ""),
            str(existing.get("symbol") or ""),
            str(existing.get("action") or ""),
            str(existing.get("at") or ""),
            str(existing.get("reason") or ""),
            str(existing.get("dependency_outcome") or ""),
            str(existing.get("broker_lifecycle_status") or ""),
            str(existing.get("recompute_reason") or ""),
        )
        if existing_key == key:
            return
    timeline.append(event)


def _order_time(order: dict, *keys: str) -> str | None:
    for key in keys:
        value = order.get(key)
        if value:
            return str(value)
    return None


def _to_utc_naive_datetime(value: str | None):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _queue_item_terminal(item: dict) -> bool:
    lifecycle = str(item.get("broker_lifecycle_status") or "").strip().lower()
    final_status = str(item.get("execution_final_status") or "").strip().lower()
    queue_status = str(item.get("queue_status") or "").strip().lower()
    if lifecycle in _RECON_TERMINAL_LIFECYCLE:
        return True
    if final_status in _RECON_TERMINAL_FINAL:
        return True
    if queue_status in {"skipped", "cancelled"}:
        return True
    return False


def _actual_release_value_from_queue_item(item: dict) -> float:
    action = str(item.get("requested_execution_action") or "").strip().upper()
    if action not in _RECON_CAPITAL_RELEASE_ACTIONS:
        return 0.0
    filled_qty = _safe_float(item.get("filled_qty"), 0.0)
    avg_fill_price = _safe_float(item.get("average_fill_price"), 0.0)
    if filled_qty > 0 and avg_fill_price > 0:
        return round(filled_qty * avg_fill_price, 4)
    return round(max(_safe_float(item.get("dependency_actual_release_value"), 0.0), 0.0), 4)


def _apply_dependency_progress(queue_items: list[dict], timeline: list[dict], at_iso: str) -> None:
    queue_by_id = {
        str(item.get("queue_item_id") or "").strip(): item
        for item in queue_items
        if isinstance(item, dict) and str(item.get("queue_item_id") or "").strip()
    }

    for item in queue_items:
        if not isinstance(item, dict):
            continue
        dependency_ids = [
            str(dep).strip()
            for dep in (item.get("depends_on_queue_item_ids") or [])
            if str(dep).strip()
        ]
        if not dependency_ids:
            item["dependency_release_progress_pct"] = 100.0 if not item.get("requires_capital_release") else 0.0
            continue

        expected = max(_safe_float(item.get("dependency_expected_release_value"), 0.0), 0.0)
        actual = 0.0
        unresolved = False
        failed = False
        for dep_id in dependency_ids:
            dep = queue_by_id.get(dep_id) or {}
            actual += _actual_release_value_from_queue_item(dep)
            dep_lifecycle = str(dep.get("broker_lifecycle_status") or "").strip().lower()
            dep_final = str(dep.get("execution_final_status") or "").strip().lower()
            if dep_lifecycle in {"rejected", "cancelled", "expired"} or dep_final in {"rejected", "cancelled", "expired"}:
                failed = True
            if not _queue_item_terminal(dep):
                unresolved = True
        actual = round(max(actual, 0.0), 4)
        delta = round(actual - expected, 4)
        progress = 0.0
        if expected > 0:
            progress = min(max((actual / expected) * 100.0, 0.0), 100.0)

        prior_outcome = str(item.get("dependency_outcome") or "").strip().lower()
        if expected <= 0:
            outcome = "capital_release_not_required"
            dependency_satisfied = True
        elif unresolved and actual <= 0:
            outcome = "waiting_for_capital_release"
            dependency_satisfied = False
        elif actual >= (expected * 0.99):
            outcome = "capital_release_completed"
            dependency_satisfied = True
        elif actual > 0:
            outcome = "capital_release_partial"
            dependency_satisfied = True
        elif failed:
            outcome = "capital_release_failed"
            dependency_satisfied = False
        else:
            outcome = "waiting_for_capital_release"
            dependency_satisfied = False

        item["dependency_actual_release_value"] = actual
        item["dependency_release_delta"] = delta
        item["dependency_release_progress_pct"] = round(progress, 3)
        item["dependency_outcome"] = outcome
        item["dependency_final_outcome"] = outcome
        item["dependency_satisfied"] = bool(dependency_satisfied)
        if outcome in {"capital_release_completed", "capital_release_partial", "capital_release_failed"}:
            item["dependency_resolved_at"] = item.get("dependency_resolved_at") or at_iso
            item["dependency_resolution_reason"] = outcome
        if outcome == "waiting_for_capital_release" and not item.get("dependency_wait_started_at"):
            item["dependency_wait_started_at"] = at_iso

        action = str(item.get("requested_execution_action") or "").strip().upper()
        if action in _RECON_CAPITAL_DEPLOY_ACTIONS and not bool(item.get("broker_order_submitted")):
            original_qty = max(_safe_float(item.get("original_approved_order_qty"), _safe_float(item.get("approved_order_qty"), 0.0)), 0.0)
            original_capital = max(_safe_float(item.get("capital_approved_value"), 0.0), 0.0)
            ratio = 1.0
            if expected > 0:
                ratio = min(max(actual / expected, 0.0), 1.0)
            recomputed_qty = round(max(original_qty * ratio, 0.0), 4)
            recomputed_capital = round(max(original_capital * ratio, 0.0), 4)
            item["recomputed_approved_order_qty"] = recomputed_qty
            item["recomputed_capital_approved_value"] = recomputed_capital
            if ratio < 0.999:
                item["resized_after_execution_result"] = True
                item["resized_after_capital_release"] = True
                item["funding_recomputed"] = True
                item["recompute_reason"] = (
                    "dependency_release_failed"
                    if outcome == "capital_release_failed"
                    else "dependency_release_partial"
                )
                _timeline_append_unique(
                    timeline,
                    {
                        "event": "dependent_action_resized",
                        "at": at_iso,
                        "queue_item_id": item.get("queue_item_id"),
                        "symbol": item.get("symbol"),
                        "action": item.get("requested_execution_action"),
                        "queue_rank": item.get("queue_rank"),
                        "recompute_reason": item.get("recompute_reason"),
                        "original_approved_order_qty": original_qty,
                        "recomputed_approved_order_qty": recomputed_qty,
                    },
                )
                if recomputed_qty <= 0:
                    item["queue_status"] = "cancelled"
                    item["execution_engine_status"] = "cancelled"
                    item["execution_final_status"] = "cancelled"
                    item["execution_skip_reason"] = item.get("execution_skip_reason") or "dependency_release_failed"
                    item["execution_completed_at"] = item.get("execution_completed_at") or at_iso
            elif outcome in {"capital_release_completed", "capital_release_partial"}:
                if str(item.get("queue_status") or "").strip().lower() == "waiting_for_prerequisite":
                    item["queue_status"] = "ready"
                    item["execution_engine_status"] = "ready"
                    item["execution_final_status"] = "ready"
                    item["queue_gate_result"] = "go"
                    item["queue_gate_reason"] = "dependency_resolved"

        if prior_outcome != outcome:
            _timeline_append_unique(
                timeline,
                {
                    "event": "dependency_resolved",
                    "at": at_iso,
                    "queue_item_id": item.get("queue_item_id"),
                    "symbol": item.get("symbol"),
                    "action": item.get("requested_execution_action"),
                    "queue_rank": item.get("queue_rank"),
                    "dependency_outcome": outcome,
                    "expected_release_value": expected,
                    "actual_release_value": actual,
                },
            )


def _update_execution_summary(execution_orchestrator: dict) -> None:
    queue_items = execution_orchestrator.get("queue_items") if isinstance(execution_orchestrator.get("queue_items"), list) else []
    if not queue_items:
        return
    summary = dict(execution_orchestrator.get("summary") or {})
    queue_status_counts = Counter(str(item.get("queue_status") or "unknown") for item in queue_items)
    engine_counts = Counter(str(item.get("execution_engine_status") or "unknown") for item in queue_items)
    broker_submission_counts = Counter(str(item.get("broker_submission_status") or "unknown") for item in queue_items)
    broker_lifecycle_counts = Counter(str(item.get("broker_lifecycle_status") or "unknown") for item in queue_items)
    final_counts = Counter(str(item.get("execution_final_status") or "unknown") for item in queue_items)
    summary.update(
        {
            "queue_total": len(queue_items),
            "submitted_count": int(queue_status_counts.get("submitted", 0)),
            "deferred_count": int(queue_status_counts.get("deferred", 0)),
            "waiting_count": int(queue_status_counts.get("waiting_for_prerequisite", 0)),
            "skipped_count": int(queue_status_counts.get("skipped", 0)),
            "ready_count": int(queue_status_counts.get("ready", 0)),
            "cancelled_count": int(queue_status_counts.get("cancelled", 0)),
            "execution_engine_status_counts": dict(engine_counts.most_common(16)),
            "broker_submission_status_counts": dict(broker_submission_counts.most_common(16)),
            "broker_lifecycle_status_counts": dict(broker_lifecycle_counts.most_common(16)),
            "execution_final_status_counts": dict(final_counts.most_common(16)),
            "retry_scheduled_count": int(final_counts.get("retry_scheduled", 0)),
            "backoff_active_count": int(sum(1 for item in queue_items if bool(item.get("backoff_active")))),
            "resized_after_execution_result_count": int(sum(1 for item in queue_items if bool(item.get("resized_after_execution_result")))),
            "reconciliation_started_count": int(sum(1 for item in queue_items if bool(item.get("reconciliation_started_at")))),
            "reconciliation_completed_count": int(sum(1 for item in queue_items if bool(item.get("reconciliation_completed_at")))),
            "reconciliation_active_count": int(sum(1 for item in queue_items if bool(item.get("reconciliation_started_at")) and not bool(item.get("reconciliation_completed_at")))),
            "reconciliation_terminal_count": int(sum(1 for item in queue_items if bool(item.get("reconciliation_terminal")))),
            "reconciliation_window_expired_count": int(sum(1 for item in queue_items if bool(item.get("reconciliation_window_expired")))),
            "reconciliation_poll_count_total": int(sum(_safe_int(item.get("reconciliation_poll_count"), 0) for item in queue_items)),
        }
    )
    execution_orchestrator["summary"] = summary


def _propagate_queue_state_to_rows(*, queue_items: list[dict], decision_rows: list[dict], signal_items: list[dict]) -> None:
    queue_by_symbol = {
        _normalize_symbol(item.get("symbol")): item
        for item in queue_items
        if isinstance(item, dict) and _normalize_symbol(item.get("symbol"))
    }
    update_fields = [
        "queue_item_id",
        "execution_stage",
        "queue_rank",
        "queue_reason",
        "queue_status",
        "queue_gate_result",
        "queue_gate_reason",
        "execution_go_no_go",
        "defer_reason",
        "dependency_type",
        "depends_on_queue_item_ids",
        "requires_capital_release",
        "dependency_satisfied",
        "dependency_outcome",
        "dependency_expected_release_value",
        "dependency_actual_release_value",
        "dependency_release_delta",
        "dependency_release_progress_pct",
        "dependency_wait_started_at",
        "dependency_resolved_at",
        "dependency_resolution_reason",
        "dependency_final_outcome",
        "resized_after_execution_result",
        "resized_after_capital_release",
        "funding_recomputed",
        "recompute_reason",
        "original_approved_order_qty",
        "recomputed_approved_order_qty",
        "recomputed_capital_approved_value",
        "submission_order",
        "queue_wait_seconds",
        "queue_submitted_at_offset_seconds",
        "liquidity_quality",
        "execution_engine_status",
        "broker_submission_status",
        "broker_lifecycle_status",
        "execution_final_status",
        "submitted_to_execution_engine_at",
        "broker_submission_attempted_at",
        "broker_acknowledged_at",
        "broker_last_update_at",
        "execution_completed_at",
        "first_fill_at",
        "final_fill_at",
        "retry_eligible",
        "retry_reason",
        "retry_attempt_count",
        "retry_max_attempts",
        "retry_next_attempt_at",
        "backoff_seconds",
        "backoff_strategy",
        "retry_exhausted",
        "backoff_active",
        "permanent_failure",
        "reconciliation_started_at",
        "reconciliation_last_polled_at",
        "reconciliation_completed_at",
        "reconciliation_poll_count",
        "reconciliation_terminal",
        "reconciliation_window_expired",
        "reconciliation_stop_reason",
        "broker_order_submitted",
        "broker_order_id",
        "broker_client_order_id",
        "broker_order_status",
        "filled_qty",
        "average_fill_price",
        "trade_fill_status",
        "execution_skip_reason",
    ]

    for row in decision_rows or []:
        if not isinstance(row, dict):
            continue
        item = queue_by_symbol.get(_normalize_symbol(row.get("symbol")))
        if not isinstance(item, dict):
            continue
        for field in update_fields:
            if field in item:
                row[field] = item.get(field)

    for row in signal_items or []:
        if not isinstance(row, dict):
            continue
        item = queue_by_symbol.get(_normalize_symbol(row.get("symbol")))
        if not isinstance(item, dict):
            continue
        for field in update_fields:
            if field in item:
                row[field] = item.get(field)


def _reconcile_execution_orchestrator_cycle(
    *,
    portfolio_brain_payload: dict,
    decision_rows: list[dict],
    signal_items: list[dict],
    auto_config: dict,
    cycle_id: str,
) -> dict:
    execution_orchestrator = (
        portfolio_brain_payload.get("execution_orchestrator")
        if isinstance(portfolio_brain_payload, dict)
        else {}
    )
    if not isinstance(execution_orchestrator, dict):
        return {"enabled": False, "applied": False, "reason": "missing_execution_orchestrator"}
    queue_items = execution_orchestrator.get("queue_items")
    if not isinstance(queue_items, list) or not queue_items:
        return {"enabled": False, "applied": False, "reason": "empty_queue"}

    enabled = bool(auto_config.get("execution_reconciliation_enabled", True))
    if not enabled:
        _update_execution_summary(execution_orchestrator)
        return {"enabled": False, "applied": False, "reason": "disabled"}

    window_seconds = max(_safe_int(auto_config.get("execution_reconciliation_window_seconds"), 30), 5)
    poll_interval_seconds = max(_safe_int(auto_config.get("execution_reconciliation_poll_interval_seconds"), 3), 1)
    max_polls = max(_safe_int(auto_config.get("execution_reconciliation_max_polls"), 8), 1)
    stop_on_terminal = bool(auto_config.get("execution_reconciliation_stop_on_terminal", True))
    update_dependent_actions = bool(auto_config.get("execution_reconciliation_update_dependent_actions", True))
    retry_enabled = bool(auto_config.get("execution_retry_enabled", True))
    retry_max_attempts = max(_safe_int(auto_config.get("execution_retry_max_attempts"), 2), 1)
    retry_initial_backoff_seconds = max(_safe_int(auto_config.get("execution_retry_initial_backoff_seconds"), 2), 1)
    retry_max_backoff_seconds = max(_safe_int(auto_config.get("execution_retry_max_backoff_seconds"), 20), 1)
    retry_backoff_multiplier = max(_safe_float(auto_config.get("execution_retry_backoff_multiplier"), 2.0), 1.0)
    retry_allowed_for_submit = bool(auto_config.get("execution_retry_allowed_for_broker_submit", True))

    trackable: list[dict] = []
    for item in queue_items:
        if not isinstance(item, dict):
            continue
        queue_status = str(item.get("queue_status") or "").strip().lower()
        engine_status = str(item.get("execution_engine_status") or "").strip().lower()
        lifecycle_status = str(item.get("broker_lifecycle_status") or "").strip().lower()
        if queue_status == "submitted" or engine_status in _RECON_TRACKABLE_ENGINE_STATES or lifecycle_status in {
            "broker_submission_pending",
            "broker_accepted",
            "partially_filled",
            "filled",
            "rejected",
            "cancelled",
            "expired",
        }:
            trackable.append(item)
    if not trackable:
        _update_execution_summary(execution_orchestrator)
        return {"enabled": True, "applied": False, "reason": "no_trackable_items"}

    timeline = execution_orchestrator.get("timeline")
    if not isinstance(timeline, list):
        timeline = []
        execution_orchestrator["timeline"] = timeline

    started_at = datetime.utcnow().isoformat()
    for item in trackable:
        item["reconciliation_started_at"] = item.get("reconciliation_started_at") or started_at
        item["reconciliation_terminal"] = bool(item.get("reconciliation_terminal", False))
        item["reconciliation_window_expired"] = False
    _timeline_append_unique(
        timeline,
        {
            "event": "reconciliation_started",
            "at": started_at,
            "cycle_id": cycle_id,
            "trackable_items": len(trackable),
            "window_seconds": window_seconds,
            "poll_interval_seconds": poll_interval_seconds,
            "max_polls": max_polls,
        },
    )

    start_perf = perf_counter()
    stop_reason = "max_polls_reached"
    completed_at = datetime.utcnow().isoformat()
    polls_done = 0
    cycle_started_dt = _to_utc_naive_datetime(
        portfolio_brain_payload.get("cycle_started_at")
        if isinstance(portfolio_brain_payload, dict)
        else None
    ) or datetime.utcnow()
    candidate_floor_dt = cycle_started_dt - timedelta(minutes=10)

    for poll_number in range(1, max_polls + 1):
        elapsed = perf_counter() - start_perf
        if elapsed > window_seconds:
            stop_reason = "reconciliation_window_expired"
            break

        polled_at = datetime.utcnow().isoformat()
        polls_done = poll_number
        orders_snapshot = {"items": [], "connected": False}
        orders_error = None
        try:
            from backend.app.adapters.broker.alpaca.orders import get_orders_snapshot

            orders_snapshot = get_orders_snapshot(refresh=True) or {"items": []}
        except Exception as exc:
            orders_error = str(exc)

        orders_items = orders_snapshot.get("items") if isinstance(orders_snapshot.get("items"), list) else []
        by_order_id = {}
        by_client_id = {}
        by_symbol: dict[str, list[dict]] = {}
        for order in orders_items:
            if not isinstance(order, dict):
                continue
            order_id = str(order.get("id") or "").strip()
            client_id = str(order.get("client_order_id") or "").strip()
            symbol = _normalize_symbol(order.get("symbol"))
            if order_id:
                by_order_id[order_id] = order
            if client_id:
                by_client_id[client_id] = order
            if symbol:
                by_symbol.setdefault(symbol, []).append(order)

        for item in trackable:
            action = str(item.get("requested_execution_action") or "").strip().upper()
            symbol = _normalize_symbol(item.get("symbol"))
            item["reconciliation_last_polled_at"] = polled_at
            item["reconciliation_poll_count"] = _safe_int(item.get("reconciliation_poll_count"), 0) + 1

            matched_order = None
            order_id = str(item.get("broker_order_id") or "").strip()
            client_id = str(item.get("broker_client_order_id") or "").strip()
            if order_id and order_id in by_order_id:
                matched_order = by_order_id[order_id]
            elif client_id and client_id in by_client_id:
                matched_order = by_client_id[client_id]
            elif symbol and by_symbol.get(symbol):
                current_cycle_candidates = []
                for candidate in (by_symbol.get(symbol) or []):
                    submitted_dt = _to_utc_naive_datetime(
                        _order_time(candidate, "submitted_at", "updated_at")
                    )
                    if submitted_dt is None or submitted_dt >= candidate_floor_dt:
                        current_cycle_candidates.append(candidate)
                sorted_candidates = sorted(
                    current_cycle_candidates,
                    key=lambda order: (
                        str(order.get("updated_at") or ""),
                        str(order.get("submitted_at") or ""),
                    ),
                    reverse=True,
                )
                matched_order = sorted_candidates[0] if sorted_candidates else None

            previous_lifecycle = str(item.get("broker_lifecycle_status") or "").strip().lower()
            previous_final = str(item.get("execution_final_status") or "").strip().lower()
            if matched_order:
                status = _normalize_broker_status(matched_order.get("status"))
                requested_qty = max(_safe_float(item.get("approved_order_qty"), 0.0), 0.0)
                filled_qty = max(_safe_float(matched_order.get("filled_qty"), _safe_float(item.get("filled_qty"), 0.0)), 0.0)
                avg_fill = max(_safe_float(matched_order.get("filled_avg_price"), _safe_float(item.get("average_fill_price"), 0.0)), 0.0)
                lifecycle = _map_broker_lifecycle(status, filled_qty, requested_qty)

                item["broker_order_submitted"] = True
                item["broker_order_id"] = str(matched_order.get("id") or item.get("broker_order_id") or "").strip() or None
                item["broker_client_order_id"] = str(
                    matched_order.get("client_order_id") or item.get("broker_client_order_id") or ""
                ).strip() or None
                item["broker_order_status"] = status or item.get("broker_order_status")
                item["broker_submission_status"] = (
                    "broker_submitted"
                    if lifecycle in {"broker_submission_pending", "broker_accepted", "partially_filled", "filled", "rejected", "cancelled", "expired"}
                    else "broker_submission_pending"
                )
                item["broker_submission_attempted_at"] = (
                    item.get("broker_submission_attempted_at")
                    or _order_time(matched_order, "submitted_at", "updated_at")
                    or item.get("submitted_to_execution_engine_at")
                    or polled_at
                )
                if lifecycle in {"broker_accepted", "partially_filled", "filled"}:
                    item["broker_acknowledged_at"] = (
                        item.get("broker_acknowledged_at")
                        or _order_time(matched_order, "submitted_at", "updated_at")
                        or polled_at
                    )
                item["broker_last_update_at"] = (
                    _order_time(matched_order, "updated_at", "submitted_at")
                    or item.get("broker_last_update_at")
                    or polled_at
                )
                item["broker_lifecycle_status"] = lifecycle
                item["trade_fill_status"] = (
                    "order_filled"
                    if lifecycle == "filled"
                    else "order_partially_filled"
                    if lifecycle == "partially_filled"
                    else "none"
                )
                if filled_qty > 0:
                    item["filled_qty"] = round(filled_qty, 4)
                    item["executed_qty"] = round(filled_qty, 4)
                    if avg_fill > 0:
                        item["average_fill_price"] = round(avg_fill, 4)
                        item["executed_price"] = round(avg_fill, 4)
                    if not item.get("first_fill_at"):
                        item["first_fill_at"] = _order_time(matched_order, "updated_at", "submitted_at") or polled_at
                if lifecycle == "filled":
                    item["final_fill_at"] = _order_time(matched_order, "updated_at", "submitted_at") or polled_at

                item["execution_final_status"] = _execution_final_from_lifecycle(lifecycle)
                if lifecycle in _RECON_TERMINAL_LIFECYCLE:
                    item["reconciliation_terminal"] = True
                    item["execution_completed_at"] = item.get("execution_completed_at") or polled_at
                else:
                    item["reconciliation_terminal"] = False

                if lifecycle != previous_lifecycle:
                    lifecycle_event = {
                        "broker_submission_pending": "broker_submit_attempted",
                        "broker_accepted": "broker_acknowledged",
                        "partially_filled": "broker_partially_filled",
                        "filled": "broker_filled",
                        "rejected": "broker_rejected",
                        "cancelled": "broker_cancelled",
                        "expired": "broker_expired",
                    }.get(lifecycle, "broker_status_polled")
                    _timeline_append_unique(
                        timeline,
                        {
                            "event": lifecycle_event,
                            "at": item.get("broker_last_update_at") or polled_at,
                            "queue_item_id": item.get("queue_item_id"),
                            "symbol": symbol,
                            "action": action,
                            "queue_rank": item.get("queue_rank"),
                            "broker_lifecycle_status": lifecycle,
                            "broker_order_status": status,
                        },
                    )
            else:
                if str(item.get("queue_status") or "").strip().lower() == "submitted":
                    item["broker_submission_status"] = "broker_submission_pending"
                    if str(item.get("execution_engine_status") or "").strip().lower() in {"", "queued"}:
                        item["execution_engine_status"] = "submitted_to_execution_engine"
                    if not item.get("execution_final_status") or str(item.get("execution_final_status")).strip().lower() in {"queued", "ready"}:
                        item["execution_final_status"] = "submitted_to_execution_engine"

                if retry_enabled and retry_allowed_for_submit and not item.get("broker_order_submitted"):
                    attempt_count = max(_safe_int(item.get("retry_attempt_count"), 0), poll_number - 1)
                    if attempt_count < retry_max_attempts:
                        backoff_seconds = min(
                            retry_max_backoff_seconds,
                            max(
                                retry_initial_backoff_seconds,
                                int(round(retry_initial_backoff_seconds * (retry_backoff_multiplier ** max(attempt_count, 0)))),
                            ),
                        )
                        item["retry_eligible"] = True
                        item["retry_reason"] = "broker_status_unavailable"
                        item["retry_attempt_count"] = attempt_count
                        item["backoff_seconds"] = float(backoff_seconds)
                        item["retry_next_attempt_at"] = (datetime.utcnow() + timedelta(seconds=backoff_seconds)).isoformat()
                        item["backoff_active"] = True
                        if str(item.get("execution_final_status") or "").strip().lower() not in {"filled", "partially_filled"}:
                            item["execution_final_status"] = "retry_scheduled"
                        _timeline_append_unique(
                            timeline,
                            {
                                "event": "retry_scheduled",
                                "at": polled_at,
                                "queue_item_id": item.get("queue_item_id"),
                                "symbol": symbol,
                                "action": action,
                                "queue_rank": item.get("queue_rank"),
                                "reason": item.get("retry_reason"),
                                "backoff_seconds": backoff_seconds,
                            },
                        )
                    else:
                        item["retry_eligible"] = False
                        item["retry_exhausted"] = True
                        item["permanent_failure"] = True
                        item["backoff_active"] = False
                        if not _queue_item_terminal(item):
                            item["execution_final_status"] = "exhausted_retries"
                            item["execution_completed_at"] = item.get("execution_completed_at") or polled_at

            if previous_final != str(item.get("execution_final_status") or "").strip().lower():
                _timeline_append_unique(
                    timeline,
                    {
                        "event": "queue_item_state",
                        "at": polled_at,
                        "queue_item_id": item.get("queue_item_id"),
                        "symbol": symbol,
                        "action": action,
                        "queue_rank": item.get("queue_rank"),
                        "queue_status": item.get("queue_status"),
                        "reason": item.get("queue_gate_reason") or item.get("defer_reason"),
                    },
                )

        if update_dependent_actions:
            _apply_dependency_progress(queue_items, timeline, polled_at)

        _timeline_append_unique(
            timeline,
            {
                "event": "broker_status_polled",
                "at": polled_at,
                "cycle_id": cycle_id,
                "poll_number": poll_number,
                "orders_seen": len(orders_items),
                "orders_connected": bool(orders_snapshot.get("connected", False)),
                "reason": orders_error,
            },
        )

        if stop_on_terminal and all(_queue_item_terminal(item) for item in trackable):
            stop_reason = "all_trackable_terminal"
            completed_at = polled_at
            break

        completed_at = polled_at
        if poll_number >= max_polls:
            stop_reason = "max_polls_reached"
            break
        elapsed_after_poll = perf_counter() - start_perf
        if elapsed_after_poll + poll_interval_seconds > window_seconds:
            stop_reason = "reconciliation_window_expired"
            break
        sleep(poll_interval_seconds)

    elapsed_total = perf_counter() - start_perf
    window_expired = stop_reason == "reconciliation_window_expired" or elapsed_total > window_seconds
    for item in trackable:
        item["reconciliation_window_expired"] = bool(window_expired)
        if item.get("reconciliation_terminal") or _queue_item_terminal(item) or window_expired:
            item["reconciliation_completed_at"] = item.get("reconciliation_completed_at") or completed_at
        item["reconciliation_stop_reason"] = stop_reason

    _timeline_append_unique(
        timeline,
        {
            "event": "reconciliation_completed",
            "at": completed_at,
            "cycle_id": cycle_id,
            "polls": polls_done,
            "stop_reason": stop_reason,
            "window_expired": bool(window_expired),
        },
    )

    _update_execution_summary(execution_orchestrator)
    _propagate_queue_state_to_rows(
        queue_items=queue_items,
        decision_rows=decision_rows,
        signal_items=signal_items,
    )
    return {
        "enabled": True,
        "applied": True,
        "trackable_items": len(trackable),
        "poll_count": polls_done,
        "stop_reason": stop_reason,
        "window_expired": bool(window_expired),
        "completed_at": completed_at,
    }


def _record_run(job_name: str, status: str, started_at: datetime, dry_run: bool, detail: str, artifacts: list[dict]) -> dict:
    run_id = f"automation-{job_name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    completed_at = datetime.utcnow()
    duration = round((completed_at - started_at).total_seconds(), 4) if isinstance(started_at, datetime) else None
    with session_scope() as session:
        session.add(AutomationRun(
            run_id=run_id,
            job_name=job_name,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            dry_run=dry_run,
            detail=detail,
            artifacts_count=len(artifacts),
        ))
        for artifact in artifacts:
            artifact_payload = artifact.get("payload")
            if (
                job_name == "auto_trading_cycle"
                and artifact.get("artifact_type") == "auto_trading_decision_trace"
                and isinstance(artifact_payload, dict)
            ):
                artifact_payload = dict(artifact_payload)
                artifact_payload["cycle_id"] = run_id
                rows = artifact_payload.get("rows")
                if isinstance(rows, list):
                    artifact_payload["rows"] = [
                        {**row, "cycle_id": run_id} if isinstance(row, dict) else row
                        for row in rows
                    ]
            session.add(AutomationArtifact(
                run_id=run_id,
                job_name=job_name,
                artifact_type=artifact.get("artifact_type", "payload"),
                artifact_key=artifact.get("artifact_key"),
                payload_json=dumps_json(artifact_payload),
            ))
    return {
        "run_id": run_id,
        "job_name": job_name,
        "status": status,
        "detail": detail,
        "artifacts": artifacts,
        "completed_at": completed_at.isoformat(),
        "dry_run": dry_run,
    }


def _build_ranked_candidates(symbols: list[str], start_date: str, end_date: str, include_dl: bool = True, include_ensemble: bool = True) -> list[dict]:
    ranked = []
    for symbol in symbols:
        try:
            ranked.append(
                build_smart_analysis(
                    symbol,
                    start_date,
                    end_date,
                    include_dl=include_dl,
                    include_ensemble=include_ensemble,
                )
            )
        except Exception as exc:
            ranked.append({"instrument": symbol, "error": str(exc)})
    return ranked


def _refresh_symbol_history(symbols: list[str], dry_run: bool = False) -> dict:
    normalized_symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    if not normalized_symbols:
        return {
            "requested_symbols": 0,
            "updated_symbols": 0,
            "total_rows": 0,
            "errors": [],
            "window": None,
            "dry_run": dry_run,
            "sample": [],
        }

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=max(int(AUTONOMOUS_HISTORY_LOOKBACK_DAYS), 5))
    updated = []
    errors = []
    total_rows = 0

    for symbol in normalized_symbols:
        try:
            result = load_history(
                symbol,
                str(start_date),
                str(end_date),
                interval="1d",
                persist=not dry_run,
            )
        except Exception as exc:
            errors.append({"symbol": symbol, "error": " ".join(str(exc).split()) or exc.__class__.__name__})
            continue
        if result.get("error"):
            errors.append({"symbol": symbol, "error": result.get("error")})
            continue
        rows = int(result.get("rows", 0) or 0)
        total_rows += rows
        updated.append({
            "symbol": symbol,
            "rows": rows,
            "source": result.get("source"),
        })

    return {
        "requested_symbols": len(normalized_symbols),
        "updated_symbols": len(updated),
        "total_rows": total_rows,
        "errors": errors[:25],
        "window": {
            "start_date": str(start_date),
            "end_date": str(end_date),
        },
        "dry_run": dry_run,
        "sample": updated[:10],
    }


def _review_and_promote(run_id: str | None) -> dict:
    if not run_id:
        return {
            "promoted_run_id": None,
            "review": None,
            "activation": None,
            "error": "No run_id was returned.",
        }

    review = review_model_promotion(run_id)
    if review.get("error"):
        return {
            "promoted_run_id": None,
            "review": review,
            "activation": None,
            "error": review.get("error"),
        }

    if not review.get("approved"):
        return {
            "promoted_run_id": None,
            "review": review,
            "activation": None,
            "error": None,
        }

    promotion = promote_model_run(run_id)
    return {
        "promoted_run_id": run_id if promotion.get("activation") else None,
        "review": review,
        "activation": promotion.get("activation"),
        "error": promotion.get("error"),
    }


def _market_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    universe = resolve_universe_preset(preset, limit=250)
    symbols = _select_symbols_for_cycle(preset, universe.get("symbols", []), min(10, AUTOMATION_SYMBOL_LIMIT))
    start_date, end_date = _analysis_window()
    snapshots = fetch_quote_snapshots(symbols, include_profile=False)
    ranked = _build_ranked_candidates(
        symbols[:8],
        start_date,
        end_date,
        include_dl=LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
        include_ensemble=True,
    )
    watchlists = build_dynamic_watchlists(preset=preset)
    artifacts = [
        {"artifact_type": "watchlists", "artifact_key": preset.lower(), "payload": watchlists},
        {"artifact_type": "market_snapshots", "artifact_key": "latest", "payload": snapshots},
        {"artifact_type": "smart_rankings", "artifact_key": "top_candidates", "payload": ranked},
    ]
    return (
        f"market_cycle symbols={len(symbols)} failed_snapshots={snapshots.get('failed_symbols', 0)} dry_run={dry_run}",
        artifacts,
    )


def _alert_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    universe = resolve_universe_preset(preset, limit=250)
    alert_symbols = _select_symbols_for_cycle(preset, universe.get("symbols", []), AUTOMATION_ALERT_SYMBOL_LIMIT)
    alerts = generate_advanced_alerts(alert_symbols, persist=not dry_run)
    return (
        f"generated_alerts={alerts.get('count', 0)} symbols={len(alert_symbols)} "
        f"failed_symbols={alerts.get('failed_symbols', 0)} dry_run={dry_run}",
        [
        {"artifact_type": "alerts", "artifact_key": "latest", "payload": alerts},
        ],
    )


def _breadth_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    breadth = compute_market_breadth(preset=preset)
    sectors = compute_sector_rotation()
    return (
        f"breadth_sample={breadth.get('sample_size', 0)} failed_symbols={breadth.get('failed_symbols', 0)} dry_run={dry_run}",
        [
        {"artifact_type": "breadth", "artifact_key": preset.lower(), "payload": breadth},
        {"artifact_type": "sector_rotation", "artifact_key": "sectors", "payload": sectors},
        ],
    )


def _retrain_cycle(dry_run: bool = False) -> tuple[str, list[dict]]:
    if not ENABLE_AUTO_RETRAIN:
        return "auto retraining is disabled by configuration", [
            {"artifact_type": "retrain_status", "artifact_key": "disabled", "payload": {"enabled": False}},
        ]

    if dry_run:
        return "dry run only, no retraining executed", [
            {"artifact_type": "retrain_status", "artifact_key": "dry_run", "payload": {"enabled": True, "dry_run": True}},
        ]

    training_guard = _training_overlap_guard()
    if training_guard is not None:
        return "retraining skipped because the continuous learning worker is already active", [
            {"artifact_type": "retrain_status", "artifact_key": "guarded", "payload": training_guard},
        ]

    start_date, end_date = _training_window()
    ml_result = train_ml_models(
        symbols=DEFAULT_SAMPLE_SYMBOLS,
        start_date=start_date,
        end_date=end_date,
        set_active=False,
    )
    promotion = None
    if ml_result.get("run_id"):
        promotion = _review_and_promote(ml_result["run_id"])
    return f"ml_retrain_status={ml_result.get('status', ml_result.get('error', 'unknown'))}", [
        {"artifact_type": "retrain_result", "artifact_key": "ml", "payload": ml_result},
        {"artifact_type": "promotion_review", "artifact_key": "ml", "payload": promotion},
    ]


def _autonomous_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    universe_refresh = {
        "status": "skipped",
        "enabled": bool(AUTONOMOUS_REFRESH_UNIVERSE),
    }
    if AUTONOMOUS_REFRESH_UNIVERSE:
        try:
            universe_refresh = refresh_market_universe(force=False)
            universe_refresh["enabled"] = True
        except Exception as exc:
            universe_refresh = {
                "status": "error",
                "enabled": True,
                "error": str(exc),
            }

    universe = resolve_universe_preset(preset, limit=250)

    analysis_symbols = _select_symbols_for_cycle(
        preset,
        universe.get("symbols", []),
        max(int(AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT or 0), 1),
    )
    training_symbols = _select_symbols_for_cycle(
        preset,
        universe.get("symbols", []),
        max(int(AUTONOMOUS_TRAIN_SYMBOL_LIMIT or 0), 1),
    )
    if not training_symbols:
        training_symbols = list(DEFAULT_SAMPLE_SYMBOLS)

    history_refresh = _refresh_symbol_history(training_symbols, dry_run=dry_run)
    analysis_start_date, analysis_end_date = _analysis_window()
    train_start_date, train_end_date = _training_window()

    snapshots = fetch_quote_snapshots(analysis_symbols, include_profile=False)
    ranked = _build_ranked_candidates(
        analysis_symbols,
        analysis_start_date,
        analysis_end_date,
        include_dl=AUTONOMOUS_INCLUDE_DL,
        include_ensemble=True,
    )
    watchlists = build_dynamic_watchlists(preset=preset, limit=max(len(analysis_symbols), AUTOMATION_SYMBOL_LIMIT))
    breadth = compute_market_breadth(preset=preset)
    sectors = compute_sector_rotation()
    alerts = generate_advanced_alerts(analysis_symbols, persist=not dry_run)

    ml_training = {
        "status": "skipped",
        "reason": "Auto retraining is disabled.",
    }
    ml_promotion = {
        "promoted_run_id": None,
        "review": None,
        "activation": None,
        "error": None,
    }
    dl_training = {
        "status": "skipped",
        "reason": "DL training is disabled for the autonomous cycle.",
    }
    dl_promotion = {
        "promoted_run_id": None,
        "review": None,
        "activation": None,
        "error": None,
    }
    training_guard = None

    if dry_run:
        ml_training = {
            "status": "dry_run",
            "symbols": training_symbols,
            "start_date": train_start_date,
            "end_date": train_end_date,
        }
        if AUTONOMOUS_INCLUDE_DL:
            dl_training = {
                "status": "dry_run",
                "symbols": training_symbols,
                "start_date": train_start_date,
                "end_date": train_end_date,
            }
    elif ENABLE_AUTO_RETRAIN:
        training_guard = _training_overlap_guard()
        if training_guard is not None:
            ml_training = dict(training_guard)
            ml_promotion = {
                "promoted_run_id": None,
                "review": None,
                "activation": None,
                "error": training_guard["reason"],
            }
            if AUTONOMOUS_INCLUDE_DL:
                dl_training = dict(training_guard)
                dl_promotion = {
                    "promoted_run_id": None,
                    "review": None,
                    "activation": None,
                    "error": training_guard["reason"],
                }
        else:
            ml_training = train_ml_models(
                symbols=training_symbols,
                start_date=train_start_date,
                end_date=train_end_date,
                set_active=False,
            )
            ml_promotion = _review_and_promote(ml_training.get("run_id"))

            if AUTONOMOUS_INCLUDE_DL:
                dl_training = train_dl_models(
                    symbols=training_symbols,
                    start_date=train_start_date,
                    end_date=train_end_date,
                    set_active=False,
                )
                dl_promotion = _review_and_promote(dl_training.get("run_id"))

    top_candidates = [
        {
            "instrument": row.get("instrument"),
            "signal": row.get("smart_signal") or row.get("enhanced_signal") or row.get("signal"),
            "confidence": row.get("smart_confidence", row.get("confidence")),
            "setup_type": row.get("setup_type"),
        }
        for row in ranked
        if not row.get("error")
    ][:5]

    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "preset": preset,
        "dry_run": dry_run,
        "analysis_window": {
            "start_date": analysis_start_date,
            "end_date": analysis_end_date,
        },
        "training_window": {
            "start_date": train_start_date,
            "end_date": train_end_date,
        },
        "universe_refresh": universe_refresh,
        "universe": {
            "preset": universe.get("preset"),
            "matched_count": universe.get("matched_count"),
            "analysis_symbols": analysis_symbols,
            "training_symbols": training_symbols,
        },
        "history_refresh": history_refresh,
        "alerts_count": alerts.get("count", 0),
        "breadth_ratio": breadth.get("breadth_ratio"),
        "top_candidates": top_candidates,
        "training": {
            "auto_retrain_enabled": ENABLE_AUTO_RETRAIN,
            "include_dl": AUTONOMOUS_INCLUDE_DL,
            "guardrail": training_guard,
            "ml": ml_training,
            "ml_promotion": ml_promotion,
            "dl": dl_training,
            "dl_promotion": dl_promotion,
        },
    }

    artifacts = [
        {"artifact_type": "history_refresh", "artifact_key": preset.lower(), "payload": history_refresh},
        {"artifact_type": "market_snapshots", "artifact_key": "autonomous_latest", "payload": snapshots},
        {"artifact_type": "smart_rankings", "artifact_key": "autonomous_top_candidates", "payload": ranked},
        {"artifact_type": "watchlists", "artifact_key": f"{preset.lower()}_autonomous", "payload": watchlists},
        {"artifact_type": "alerts", "artifact_key": "autonomous_latest", "payload": alerts},
        {"artifact_type": "breadth", "artifact_key": f"{preset.lower()}_autonomous", "payload": breadth},
        {"artifact_type": "sector_rotation", "artifact_key": "autonomous_sectors", "payload": sectors},
        {"artifact_type": "retrain_result", "artifact_key": "ml", "payload": ml_training},
        {"artifact_type": "promotion_review", "artifact_key": "ml", "payload": ml_promotion},
    ]
    if AUTONOMOUS_INCLUDE_DL:
        artifacts.extend([
            {"artifact_type": "retrain_result", "artifact_key": "dl", "payload": dl_training},
            {"artifact_type": "promotion_review", "artifact_key": "dl", "payload": dl_promotion},
        ])
    if training_guard is not None:
        artifacts.append({
            "artifact_type": "training_guardrail",
            "artifact_key": "continuous_learning_active",
            "payload": training_guard,
        })
    artifacts.append({
        "artifact_type": "autonomous_summary",
        "artifact_key": _utc_today_iso(),
        "payload": summary,
    })

    detail = (
        f"autonomous_cycle analyzed={len(analysis_symbols)} trained={len(training_symbols)} "
        f"history_symbols={history_refresh.get('updated_symbols', 0)} "
        f"history_errors={len(history_refresh.get('errors', []))} "
        f"alert_failures={alerts.get('failed_symbols', 0)} dry_run={dry_run}"
    )
    if training_guard is not None:
        detail = f"{detail} training_guarded=true"
    return detail, artifacts


def _daily_summary(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    breadth = compute_market_breadth(preset=preset)
    watchlists = build_dynamic_watchlists(preset=preset)
    portfolio = get_portfolio_exposure()
    broker = get_broker_summary()
    alerts = list_alert_history(limit=10)
    journal = list_trade_journal_entries(limit=10)
    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "breadth": breadth,
        "watchlists": watchlists,
        "portfolio": portfolio.get("summary", {}),
        "broker": {
            "provider": broker.get("provider"),
            "connected": broker.get("connected"),
            "mode": broker.get("mode"),
            "totals": broker.get("totals", {}),
            "account": broker.get("account"),
        },
        "alerts": alerts.get("items", []),
        "journal": journal.get("classification_counts", {}),
    }
    return f"daily_summary alerts={len(alerts.get('items', []))} dry_run={dry_run}", [
        {"artifact_type": "daily_summary", "artifact_key": datetime.utcnow().date().isoformat(), "payload": summary},
    ]



def _auto_trading_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    """Auto-trading cycle: scan symbols, generate signals, and execute via broker only."""
    from backend.app.services.runtime_settings import get_auto_trading_config

    cycle_started_at = datetime.utcnow()
    lease_info = acquire_auto_trading_cycle_lease()
    if not lease_info.get("acquired"):
        return (
            "auto_trading_cycle skipped: another cycle is already running",
            [
                {
                    "artifact_type": "auto_trading_status",
                    "artifact_key": "lease_locked",
                    "payload": lease_info,
                }
            ],
        )
    lease_holder_id = str(lease_info.get("holder_id") or "")

    def _return_with_lease_release(detail_text: str, payload_artifacts: list[dict]) -> tuple[str, list[dict]]:
        try:
            release_auto_trading_cycle_lease(holder_id=lease_holder_id)
        except Exception:
            pass
        return detail_text, payload_artifacts

    # Check runtime settings
    auto_config = get_auto_trading_config()
    strategy_mode = _normalize_auto_trading_strategy_mode(auto_config.get("strategy_mode"))
    trade_direction = _normalize_auto_trading_trade_direction(auto_config.get("trade_direction"))
    analysis_include_dl = _auto_trading_include_dl(strategy_mode)
    margin_enabled = str(auto_config.get("trading_mode") or "cash").strip().lower() == "margin"
    effective_ready = bool(auto_config["ready"])

    if not effective_ready:
        return _return_with_lease_release(
            f"auto_trading_cycle skipped: not ready (auto_trading={auto_config['auto_trading_enabled']}, "
            f"order_sub={auto_config['order_submission_enabled']}, alpaca_configured={auto_config['alpaca_configured']})",
            [{"artifact_type": "auto_trading_status", "artifact_key": "skipped", "payload": auto_config}],
        )

    broker_sync_result = None
    if auto_config.get("order_submission_enabled") and auto_config.get("alpaca_configured"):
        try:
            from backend.app.application.execution.service import sync_internal_positions_from_broker

            broker_sync_result = sync_internal_positions_from_broker(strategy_mode=strategy_mode)
            if str(auto_config.get("trading_mode") or "cash").strip().lower() == "cash" and int(broker_sync_result.get("short_positions") or 0) > 0:
                return _return_with_lease_release(
                    "auto_trading_cycle skipped: broker account has short positions while cash mode is active",
                    [
                        {
                            "artifact_type": "auto_trading_status",
                            "artifact_key": "cash_mode_short_positions",
                            "payload": {
                                **auto_config,
                                "broker_sync": broker_sync_result,
                            },
                        }
                    ],
                )
        except Exception as exc:
            return _return_with_lease_release(
                f"auto_trading_cycle skipped: broker sync failed ({exc})",
                [
                    {
                        "artifact_type": "auto_trading_status",
                        "artifact_key": "broker_sync_failed",
                        "payload": {
                            **auto_config,
                            "error": str(exc),
                        },
                    }
                ],
            )

    if dry_run:
        return _return_with_lease_release(
            "auto_trading_cycle dry_run=True",
            [{"artifact_type": "auto_trading_status", "artifact_key": "dry_run", "payload": {"dry_run": True, **auto_config, "broker_sync": broker_sync_result}}],
        )

    # Session intelligence: use broker/session snapshot as source-of-truth.
    session_snapshot = get_market_session_snapshot(refresh=False)
    session_state = str(session_snapshot.get("session_state") or "unknown").strip().lower()
    broker_market_open = bool(session_snapshot.get("market_open", False))
    # Keep session-aware behavior anchored to broker/session truth.
    market_open = bool(broker_market_open)

    if not market_open:
        log_event(
            logger,
            logging.INFO,
            "automation.auto_trading.session.non_regular",
            session_state=session_state,
            minutes_to_open=session_snapshot.get("minutes_to_open"),
            extended_hours_available=session_snapshot.get("extended_hours_available"),
            premarket_trading_enabled=bool(auto_config.get("premarket_trading_enabled", False)),
        )

    # Cap symbols per cycle so the schedule doesn't overlap with itself.
    # Each full ML analysis takes ~2 min on a 2-vCPU box, so for a 5-min cycle we
    # typically pick 2 symbols (see MARKET_AI_AUTO_TRADING_SYMBOL_LIMIT in .env).
    try:
        symbol_limit = int(auto_config.get("symbol_limit") or AUTO_TRADING_SYMBOL_LIMIT)
    except Exception:
        symbol_limit = AUTO_TRADING_SYMBOL_LIMIT
    symbol_limit = max(1, min(symbol_limit, 500))
    full_portfolio_mode = bool(auto_config.get("use_full_portfolio", AUTO_TRADING_USE_FULL_PORTFOLIO))
    universe_preset = str(auto_config.get("universe_preset") or preset or AUTOMATION_DEFAULT_PRESET).strip().upper()
    use_top_market_cap_rotation = universe_preset == "TOP_500_MARKET_CAP"
    symbols = list(DEFAULT_SAMPLE_SYMBOLS)
    rotation_state = {"offset": 0, "next_offset": 0, "pool_size": len(symbols), "batch_size": 0}
    ranked_universe_symbols: list[str] = []
    if use_top_market_cap_rotation:
        try:
            top_market_cap = resolve_universe_preset("TOP_500_MARKET_CAP", limit=500)
            ranked_universe_symbols = list(top_market_cap.get("symbols") or [])
            rotated_batch, rotation_state = _rotate_symbol_batch(ranked_universe_symbols, symbol_limit)
            if rotated_batch:
                symbols = rotated_batch
        except Exception:
            ranked_universe_symbols = []

    # Rotation: prefer symbols that don't already have an open position so each
    # cycle has a real chance to generate a NEW trade. Reserve one slot for a
    # held name so exit signals still get re-evaluated periodically.
    import random as _random
    try:
        from backend.app.application.execution.service import get_internal_portfolio
        held_payload = get_internal_portfolio(limit=500) or {}
        held_positions = {
            str(pos.get("symbol") or "").upper(): {
                "side": str(pos.get("side") or "").upper(),
                "quantity": float(pos.get("quantity") or 0.0),
                "avg_entry_price": float(pos.get("avg_entry_price") or 0.0),
            }
            for pos in (held_payload.get("items") or [])
            if (pos.get("status") or "").upper() == "OPEN"
        }
        held = set(held_positions.keys())
    except Exception:
        held_positions = {}
        held = set()

    if use_top_market_cap_rotation and ranked_universe_symbols:
        held_pool = [s for s in ranked_universe_symbols if s in held]
        rotation = [s for s in symbols if s not in held]
        if held_pool and held_pool[0] not in rotation:
            rotation = [held_pool[0], *rotation]
        symbols = list(dict.fromkeys(rotation))[:symbol_limit] or list(DEFAULT_SAMPLE_SYMBOLS)[:symbol_limit]
    else:
        unheld = [s for s in symbols if s not in held]
        held_pool = [s for s in symbols if s in held]
        _random.shuffle(unheld)
        _random.shuffle(held_pool)
        if symbol_limit >= 2 and held_pool and unheld:
            rotation = unheld[: symbol_limit - 1] + held_pool[:1]
        else:
            rotation = (unheld + held_pool)[:symbol_limit]
        symbols = rotation[:symbol_limit] or list(DEFAULT_SAMPLE_SYMBOLS)[:symbol_limit]
    candidate_symbols = list(symbols)
    if full_portfolio_mode and not use_top_market_cap_rotation:
        mover_limit = max(symbol_limit * 4, 12)
        try:
            local_candidates = []
            for candidate in _preferred_local_symbols(preset):
                normalized = str(candidate or "").upper()
                if not normalized.isalpha():
                    continue
                if len(normalized) > 5:
                    continue
                if normalized.endswith(("W", "U", "R")):
                    continue
                local_candidates.append(normalized)
                if len(local_candidates) >= 80:
                    break
            snapshot_symbols = local_candidates or list(DEFAULT_SAMPLE_SYMBOLS)
            mover_snapshots = fetch_quote_snapshots(snapshot_symbols, include_profile=False)
            mover_items = [
                item
                for item in (mover_snapshots or {}).get("items", [])
                if float(item.get("last_price") or item.get("price") or 0.0) >= 5.0
            ]
            mover_symbols = [
                str(item.get("symbol") or "").upper()
                for item in sorted(
                    mover_items,
                    key=lambda entry: abs(float(entry.get("change_pct") or 0.0)),
                    reverse=True,
                )
                if str(item.get("symbol") or "").strip()
            ][:mover_limit]
            candidate_symbols = list(dict.fromkeys(held_pool + mover_symbols))
        except Exception:
            candidate_symbols = list(dict.fromkeys(held_pool + list(DEFAULT_SAMPLE_SYMBOLS)[:mover_limit]))
    elif use_top_market_cap_rotation:
        candidate_symbols = list(symbols)

    # Run signal refresh with auto-execute.
    # Use a shorter analysis window for auto-trading so each symbol finishes fast
    # enough that cycles don't pile up behind the 5-min schedule.
    from backend.app.application.execution.service import refresh_signals
    from datetime import datetime as _dt, timedelta as _td

    try:
        lookback_days = int(auto_config.get("analysis_lookback_days") or AUTO_TRADING_ANALYSIS_LOOKBACK_DAYS)
    except Exception:
        lookback_days = AUTO_TRADING_ANALYSIS_LOOKBACK_DAYS

    if lookback_days > 0:
        end_date = _utc_today_iso()
        start_date = (_dt.utcnow() - _td(days=lookback_days)).strftime("%Y-%m-%d")
    else:
        start_date, end_date = _analysis_window()

    # --- dynamic position sizing: aim for NOTIONAL_PER_TRADE dollars per symbol.
    # In full-portfolio mode we size from the broker account cash balance.
    # Fetch quotes up-front (cheap) to size each order in shares. Falls back to the
    # flat AUTO_TRADING_QUANTITY when a quote is unavailable.
    fallback_qty = max(float(auto_config.get("quantity") or AUTO_TRADING_QUANTITY), 1.0)
    try:
        notional_per_trade = float(auto_config.get("notional_per_trade") or AUTO_TRADING_NOTIONAL_PER_TRADE or 0.0)
    except Exception:
        notional_per_trade = AUTO_TRADING_NOTIONAL_PER_TRADE
    portfolio_cash_balance = 0.0
    portfolio_equity = 0.0
    try:
        from backend.app.application.execution.service import get_internal_portfolio

        portfolio_payload = get_internal_portfolio(limit=500) or {}
        portfolio_summary = portfolio_payload.get("summary") or {}
        portfolio_cash_balance = float(portfolio_summary.get("cash_balance") or 0.0)
        portfolio_equity = float(portfolio_summary.get("total_equity") or 0.0)
    except Exception:
        portfolio_payload = {}
        portfolio_summary = {}

    daily_guard = evaluate_daily_loss_guard(portfolio_summary)
    daily_loss_snapshot = daily_guard.get("daily_risk") or {}
    if daily_guard.get("breached") and daily_guard.get("halted"):
        return _return_with_lease_release(
            "auto_trading_cycle skipped: daily loss limit reached and execution halted",
            [
                {
                    "artifact_type": "auto_trading_status",
                    "artifact_key": "daily_loss_halt",
                    "payload": {
                        **auto_config,
                        "broker_sync": broker_sync_result,
                        "daily_risk": daily_loss_snapshot,
                        "daily_guard": daily_guard,
                        "halt_status": daily_guard.get("halt_status"),
                    },
                }
            ],
        )

    if full_portfolio_mode:
        notional_per_trade = max(portfolio_cash_balance, 0.0)
        if notional_per_trade <= 0:
            notional_per_trade = max(portfolio_equity, 0.0)
    # Keep full-portfolio sizing inside risk guardrails so intended orders do not
    # get rejected due per-trade risk cap (default 10% of equity).
    per_trade_risk_cap = 0.0
    if float(portfolio_equity or 0.0) > 0:
        per_trade_risk_cap = max(float(portfolio_equity) * max(float(RISK_MAX_TRADE_PCT), 0.0) / 100.0, 0.0)

    price_lookup: dict[str, float] = {}
    quote_symbols = list(
        dict.fromkeys(candidate_symbols if full_portfolio_mode and candidate_symbols else symbols)
    )
    if notional_per_trade > 0 and quote_symbols:
        try:
            from backend.app.services.market_data import fetch_quote_snapshots
            snap = fetch_quote_snapshots(quote_symbols, include_profile=False)
            for item in (snap or {}).get("items", []):
                sym = str(item.get("symbol") or "").upper()
                px = float(item.get("last_price") or item.get("price") or 0.0)
                if sym and px > 0:
                    price_lookup[sym] = px
        except Exception:
            price_lookup = {}

    def _compute_qty(symbol: str, budget: float | None = None) -> float:
        effective_budget = float(notional_per_trade if budget is None else budget or 0.0)
        if effective_budget <= 0:
            return fallback_qty
        px = price_lookup.get(symbol.upper(), 0.0)
        if px <= 0:
            return fallback_qty
        shares = max(int(effective_budget // px), 1)
        return float(shares)

    # Loop per symbol when dynamic sizing is active so each order can carry its
    # own share count and pass portfolio-brain overrides into execution.
    aggregate_items: list[dict] = []
    last_correlation: str | None = None
    allocated_quantities: dict[str, float] = {}
    selected_execution_candidates: list[dict] = []
    portfolio_brain_payload: dict = {}
    decision_overrides: dict[str, dict] = {}
    kronos_batch_payload: dict = {"symbols": {}, "summary": {}}
    kronos_runtime_status: dict = kronos_status(auto_config=auto_config)
    readiness_payload: dict = {
        "cycle_id": str(lease_holder_id or f"cycle-{uuid4().hex[:8]}"),
        "generated_at": datetime.utcnow().isoformat(),
        "session": session_snapshot,
        "kronos_readiness_status": "disabled" if not auto_config.get("kronos_enabled", False) else "pending",
        "readiness_completed_percent": 0,
        "readiness_checks_passed": [],
        "readiness_checks_failed": [],
        "readiness_warnings": [],
    }

    try:
        symbol_pool = list(
            dict.fromkeys(candidate_symbols if full_portfolio_mode and candidate_symbols else symbols)
        )
        if not symbol_pool:
            symbol_pool = list(symbols)

        preview_candidates: list[dict] = []
        preview_by_symbol: dict[str, dict] = {}
        for sym in symbol_pool:
            try:
                preview_result = build_smart_analysis(
                    sym,
                    start_date,
                    end_date,
                    include_dl=analysis_include_dl,
                    include_ensemble=True,
                )
                signal_view = extract_signal_view(preview_result, mode=strategy_mode)
                signal_value = str(signal_view.get("signal") or "HOLD").upper()
                current_side = (held_positions.get(sym.upper()) or {}).get("side")
                analysis_score = 0.0
                if isinstance(preview_result, dict):
                    ensemble_payload = preview_result.get("ensemble_output") if isinstance(preview_result.get("ensemble_output"), dict) else {}
                    analysis_score = float(ensemble_payload.get("ensemble_score") or preview_result.get("ensemble_score") or preview_result.get("score") or 0.0)

                preview_entry = {
                    "symbol": sym,
                    "signal": signal_value,
                    "analysis_signal": signal_value,
                    "analysis_score": analysis_score,
                    "confidence": float(signal_view.get("confidence") or 0.0),
                    "price": float(signal_view.get("price") or price_lookup.get(sym.upper()) or 0.0),
                    "current_side": current_side,
                    "result": preview_result if isinstance(preview_result, dict) else {},
                }
                if isinstance(preview_result, dict) and preview_result.get("error"):
                    preview_entry["error"] = preview_result.get("error")
                preview_candidates.append(preview_entry)
                preview_by_symbol[sym.upper()] = preview_entry
            except Exception as exc:
                preview_candidates.append(
                    {
                        "symbol": sym,
                        "signal": "HOLD",
                        "analysis_signal": "HOLD",
                        "analysis_score": 0.0,
                        "confidence": 0.0,
                        "price": float(price_lookup.get(sym.upper()) or 0.0),
                        "current_side": (held_positions.get(sym.upper()) or {}).get("side"),
                        "result": {"error": str(exc)},
                        "error": str(exc),
                    }
                )

        preview_symbol_list = [
            str(item.get("symbol") or "").strip().upper()
            for item in preview_candidates
            if isinstance(item, dict) and str(item.get("symbol") or "").strip()
        ]
        preview_symbol_list = list(dict.fromkeys(preview_symbol_list))

        readiness_checks_passed: list[str] = []
        readiness_checks_failed: list[str] = []
        readiness_warnings: list[str] = []

        if bool(auto_config.get("market_session_intelligence_enabled", True)):
            readiness_checks_passed.append("session_intelligence_ready")
        else:
            readiness_checks_failed.append("session_intelligence_disabled")

        session_minutes_to_open = session_snapshot.get("minutes_to_open")
        try:
            session_minutes_to_open_value = float(session_minutes_to_open) if session_minutes_to_open is not None else None
        except Exception:
            session_minutes_to_open_value = None
        preopen_start_minutes = max(int(auto_config.get("preopen_readiness_start_minutes") or 60), 1)
        preopen_window_active = (
            session_minutes_to_open_value is not None
            and session_minutes_to_open_value <= preopen_start_minutes
            and not bool(session_snapshot.get("market_open", False))
        )

        kronos_symbol_map: dict[str, dict] = {}
        kronos_warm_payload: dict = {}
        kronos_batch_payload = {"symbols": {}, "summary": {}}

        if bool(auto_config.get("kronos_enabled", False)):
            try:
                if bool(auto_config.get("kronos_warmup_enabled", True)) and (
                    preopen_window_active
                    or session_matches(session_snapshot, "premarket_live")
                    or session_matches(session_snapshot, "opening_handoff_window")
                    or session_matches(session_snapshot, "preopen_preparation")
                ):
                    kronos_warm_payload = warm_kronos(
                        sample_symbol=(preview_symbol_list[0] if preview_symbol_list else "SPY"),
                        auto_config=auto_config,
                        session_type=normalize_session_state(session_snapshot.get("session_state") or "preopen_preparation"),
                    )
                    if bool(kronos_warm_payload.get("kronos_warmed")):
                        readiness_checks_passed.append("kronos_warmup_completed")
                    else:
                        readiness_warnings.append("kronos_warmup_not_completed")
                else:
                    readiness_warnings.append("kronos_warmup_skipped_window")

                if bool(auto_config.get("kronos_batch_preopen_enabled", True)):
                    kronos_batch_payload = run_kronos_batch(
                        preview_symbol_list,
                        session_snapshot=session_snapshot,
                        auto_config=auto_config,
                    )
                    kronos_symbol_map = {
                        str(sym).upper(): payload
                        for sym, payload in (kronos_batch_payload.get("symbols") or {}).items()
                        if str(sym).strip()
                    }
                    if int((kronos_batch_payload.get("summary") or {}).get("kronos_batch_ready_count") or 0) > 0:
                        readiness_checks_passed.append("kronos_batch_inference_completed")
                    else:
                        readiness_warnings.append("kronos_batch_ready_count_zero")
            except Exception as kronos_exc:
                readiness_checks_failed.append("kronos_inference_failed")
                readiness_warnings.append(str(kronos_exc))
            finally:
                kronos_runtime_status = kronos_status(auto_config=auto_config)
        else:
            readiness_warnings.append("kronos_disabled")

        readiness_total = max(len(readiness_checks_passed) + len(readiness_checks_failed), 1)
        readiness_completed_percent = round((len(readiness_checks_passed) / readiness_total) * 100.0, 2)
        readiness_payload = {
            **(readiness_payload if isinstance(readiness_payload, dict) else {}),
            "generated_at": datetime.utcnow().isoformat(),
            "session": session_snapshot,
            "session_state": session_snapshot.get("session_state"),
            "readiness_phase": session_snapshot.get("readiness_phase"),
            "minutes_to_open": session_snapshot.get("minutes_to_open"),
            "minutes_to_close": session_snapshot.get("minutes_to_close"),
            "is_trading_day": session_snapshot.get("is_trading_day"),
            "readiness_completed_percent": readiness_completed_percent,
            "readiness_checks_passed": readiness_checks_passed,
            "readiness_checks_failed": readiness_checks_failed,
            "readiness_warnings": readiness_warnings,
            "kronos_warmup_completed": bool((kronos_warm_payload or {}).get("kronos_warmed")),
            "kronos_batch_inference_completed": int((kronos_batch_payload.get("summary") or {}).get("kronos_batch_ready_count") or 0) > 0,
            "kronos_batch_symbol_count": int((kronos_batch_payload.get("summary") or {}).get("kronos_batch_symbol_count") or 0),
            "kronos_batch_duration_ms": float((kronos_batch_payload.get("summary") or {}).get("kronos_batch_duration_ms") or 0.0),
            "kronos_readiness_status": (kronos_batch_payload.get("summary") or {}).get("kronos_readiness_status") or ("disabled" if not auto_config.get("kronos_enabled", False) else "degraded"),
            "kronos_readiness_warnings": [
                item for item in ((kronos_batch_payload.get("summary") or {}).get("kronos_readiness_warnings") or []) if item
            ],
            "kronos_preopen_cache_fresh": int((kronos_batch_payload.get("summary") or {}).get("kronos_batch_cache_hits") or 0) > 0,
            "kronos_open_handoff_ready": int((kronos_batch_payload.get("summary") or {}).get("kronos_batch_ready_count") or 0) > 0,
        }

        portfolio_brain_payload = build_portfolio_brain_payload(
            cycle_id=str(lease_holder_id or f"cycle-{uuid4().hex[:8]}"),
            cycle_started_at=cycle_started_at.isoformat(),
            cycle_completed_at=datetime.utcnow().isoformat(),
            strategy_mode=strategy_mode,
            market_open=market_open,
            candidate_rows=preview_candidates,
            held_positions=held_positions,
            portfolio_summary=portfolio_summary,
            auto_trading_config=auto_config,
            session_snapshot=session_snapshot,
        )

        allocation_payload = portfolio_brain_payload.get("allocation") if isinstance(portfolio_brain_payload, dict) else {}
        decision_rows = allocation_payload.get("decisions") if isinstance(allocation_payload, dict) else []
        decision_overrides = allocation_payload.get("decision_overrides") if isinstance(allocation_payload, dict) else {}
        if not isinstance(decision_overrides, dict):
            decision_overrides = {}
        allocation_summary_payload = allocation_payload.get("summary") if isinstance(allocation_payload.get("summary"), dict) else {}
        allocation_capital_payload = allocation_summary_payload.get("capital") if isinstance(allocation_summary_payload.get("capital"), dict) else {}

        execution_orchestrator = portfolio_brain_payload.get("execution_orchestrator") if isinstance(portfolio_brain_payload, dict) else {}
        if not isinstance(execution_orchestrator, dict):
            execution_orchestrator = {}
        queue_items = execution_orchestrator.get("queue_items") if isinstance(execution_orchestrator.get("queue_items"), list) else []
        queue_by_symbol = {
            str(item.get("symbol") or "").upper(): item
            for item in queue_items
            if isinstance(item, dict) and str(item.get("symbol") or "").strip()
        }

        selected_execution_candidates = [
            row
            for row in (decision_rows or [])
            if str(row.get("requested_execution_action") or "").strip().upper() in {"OPEN_LONG", "ADD_LONG", "REDUCE_LONG", "EXIT_LONG"}
        ]

        def _local_clamp(value: float, low: float, high: float) -> float:
            try:
                numeric = float(value)
            except Exception:
                numeric = float(low)
            return max(float(low), min(numeric, float(high)))

        session_state = normalize_session_state(session_snapshot.get("session_state") or session_snapshot.get("session_code") or "fully_closed")
        session_snapshot["session_state"] = session_state
        session_snapshot.setdefault("session_code", session_state)
        extended_hours_available = bool(session_snapshot.get("extended_hours_available", False))
        premarket_enabled = bool(auto_config.get("premarket_trading_enabled", False))
        queued_for_open_enabled = bool(auto_config.get("queued_for_open_enabled", True))
        wait_for_open_enabled = bool(auto_config.get("wait_for_open_confirmation_enabled", True))
        premarket_live_session = session_matches(session_snapshot, "premarket_live")
        preopen_preparation_session = session_matches(session_snapshot, "preopen_preparation")
        opening_handoff_session = session_matches(session_snapshot, "opening_handoff_window")
        after_hours_session = session_matches(session_snapshot, "after_hours")
        fully_closed_session = session_matches(session_snapshot, "fully_closed")
        overnight_supported_session = session_matches(session_snapshot, "overnight_if_supported")
        session_quality = str(session_snapshot.get("session_quality") or "unknown").strip().lower()
        minimum_liquidity_score = float(auto_config.get("min_session_liquidity_score") or 52.0)
        session_slippage_tolerance = float(auto_config.get("session_slippage_tolerance") or 46.0)
        gap_excessive_wait_threshold = float(auto_config.get("gap_excessive_wait_threshold") or 4.2)
        opening_chase_guard_enabled = bool(auto_config.get("opening_chase_guard_enabled", True))
        premarket_top_rank_only = bool(auto_config.get("premarket_top_rank_only", True))
        capital_reserve_for_open_pct = max(float(auto_config.get("capital_reserve_for_open_pct") or 35.0), 0.0)
        premarket_size_multiplier = 0.65 if not market_open else 1.0
        opening_size_multiplier = 0.9 if not market_open else 1.0
        cash_remaining = float(
            allocation_capital_payload.get("cash_remaining")
            or portfolio_summary.get("cash")
            or portfolio_cash_balance
            or 0.0
        )
        premarket_exposure_used = 0.0
        analysis_engines_snapshot = get_analysis_engines_status(latest_nonempty=True)

        for row in (decision_rows or []):
            sym = str(row.get("symbol") or "").strip().upper()
            kronos_row = kronos_symbol_map.get(sym, {}) if isinstance(kronos_symbol_map, dict) else {}
            if not isinstance(kronos_row, dict):
                kronos_row = {}

            kronos_ready = bool(kronos_row.get("kronos_ready", False))
            base_score = float(row.get("opportunity_score") or 0.0)
            kronos_session_score = float(kronos_row.get("kronos_session_adjusted_score") or kronos_row.get("kronos_score") or 0.0)
            if session_state in {"premarket_live", "preopen_preparation"}:
                kronos_weight = float(auto_config.get("kronos_premarket_weight") or auto_config.get("kronos_weight") or 0.0)
            elif session_state == "opening_handoff_window":
                kronos_weight = float(auto_config.get("kronos_opening_weight") or auto_config.get("kronos_weight") or 0.0)
            else:
                kronos_weight = float(auto_config.get("kronos_weight") or 0.0)

            contribution = 0.0
            if kronos_ready:
                contribution = round((kronos_session_score - 50.0) * kronos_weight * 0.35, 4)

            session_adjusted_score = round(_local_clamp(base_score + contribution, 0.0, 100.0), 4)
            row["session_adjusted_opportunity_score"] = session_adjusted_score
            row["kronos_weight"] = round(kronos_weight, 4)
            row["kronos_contribution_to_score"] = contribution
            row["kronos_contribution_reason"] = (
                "kronos_session_adjusted_weighting" if kronos_ready else "kronos_not_ready"
            )
            row["kronos_overrode_session_timing"] = False

            if kronos_ready and abs(contribution) > 0.001:
                row["opportunity_score"] = session_adjusted_score

            target_position_pct = float(row.get("target_position_pct") or 0.0)
            size_multiplier = float(kronos_row.get("kronos_size_multiplier") or 1.0)
            modified_target_pct = round(_local_clamp(target_position_pct * size_multiplier, 0.0, 100.0), 4)
            row["kronos_modified_target_position_pct"] = modified_target_pct
            row["kronos_modified_funding_ratio"] = round(_local_clamp(float(row.get("funding_ratio") or 0.0) * max(size_multiplier, 0.0), 0.0, 1.0), 4)
            row["kronos_modified_execution_priority"] = row.get("execution_priority_band")

            requested_action = str(row.get("requested_execution_action") or "").strip().upper()
            kronos_timing_bias = str(kronos_row.get("kronos_execution_timing_bias") or "wait").strip().lower()
            kronos_preferred_action = str(kronos_row.get("kronos_session_preferred_action") or "NO_ACTION").strip().upper()
            session_order_plan = "no_action"
            session_reason = None
            session_preferred_action = requested_action or "NO_ACTION"
            submit_before_open = False
            submit_after_open = bool(market_open)
            queued_for_open = False
            wait_for_open_confirmation = False
            opening_auction_candidate = False
            premarket_live_candidate = False
            extended_hours_eligible = False
            session_order_style = str(kronos_row.get("kronos_order_style_modifier") or row.get("order_style_preference") or "limit").strip().lower()
            order_session_type = "regular"
            order_session_route = "regular"
            session_tif = "day"
            session_risk_flags = list(kronos_row.get("kronos_warning_flags") or []) if isinstance(kronos_row.get("kronos_warning_flags"), list) else []
            premarket_submit_reason = None
            queued_for_open_reason = None
            wait_for_open_reason = None
            no_trade_before_open_reason = None
            premarket_submission_allowed = False
            premarket_submission_block_reason = None
            session_queue_type = "regular_session_queue" if market_open else "planning_queue"
            queue_activation_time = None
            queue_expiration_time = session_snapshot.get("next_close_at") if market_open else session_snapshot.get("next_open_at")
            waiting_for_market_open = False
            waiting_for_open_revalidation = False
            session_go_no_go = "no_go"
            session_gate_result = "blocked"
            session_queue_reason = None

            portfolio_rank = int(row.get("portfolio_priority_rank") or 999)
            session_score = float(row.get("session_adjusted_opportunity_score") or row.get("opportunity_score") or 0.0)
            opening_score = float(row.get("opening_score") or 0.0)
            premarket_score = float(row.get("premarket_score") or 0.0)
            open_confirmation_score = float(row.get("open_confirmation_score") or 0.0)
            relative_strength_score = float(row.get("relative_strength_score") or 0.0)
            liquidity_score = float(row.get("liquidity_score") or 0.0)
            spread_risk_score = float(row.get("spread_risk_score") or 0.0)
            volatility_risk_score = float(row.get("volatility_risk_score") or 0.0)
            gap_pct = abs(float(row.get("gap_pct") or 0.0))
            engine_alignment_score = float(row.get("engine_alignment_score") or 0.0)
            engine_conflicts_present = bool(row.get("engine_conflicts_present", False))
            capital_approved_value = float(row.get("capital_approved_value") or 0.0)
            approved_position_pct = float(row.get("approved_position_pct") or row.get("target_position_pct") or 0.0)

            top_rank_candidate = portfolio_rank <= 3 or session_score >= 78.0
            liquidity_ok = liquidity_score >= minimum_liquidity_score
            spread_ok = spread_risk_score <= session_slippage_tolerance
            gap_ok = gap_pct <= gap_excessive_wait_threshold
            alignment_ok = engine_alignment_score >= 58.0 and not (engine_conflicts_present and engine_alignment_score < 70.0)
            strong_premarket_candidate = premarket_score >= 68.0 or session_score >= 74.0
            strong_open_candidate = opening_score >= 70.0 or session_score >= 72.0
            needs_open_confirmation = open_confirmation_score >= 52.0 or engine_conflicts_present

            if not liquidity_ok:
                session_risk_flags.append("premarket_liquidity_too_low")
            if not spread_ok:
                session_risk_flags.append("premarket_spread_too_wide")
            if not gap_ok:
                session_risk_flags.append("gap_excessive_wait_for_open")
            if not alignment_ok:
                session_risk_flags.append("weak_engine_alignment")
            if volatility_risk_score >= 68.0:
                session_risk_flags.append("session_slippage_risk_too_high")
            if premarket_top_rank_only and not top_rank_candidate and requested_action in {"OPEN_LONG", "ADD_LONG"}:
                session_risk_flags.append("weak_rank_not_allowed_premarket")
            session_risk_flags = list(dict.fromkeys([flag for flag in session_risk_flags if flag]))

            if requested_action in {"OPEN_LONG", "ADD_LONG"}:
                if market_open:
                    session_order_plan = "regular_session_submit"
                    session_preferred_action = "REGULAR_SESSION_OPEN_LONG" if requested_action == "OPEN_LONG" else "REGULAR_SESSION_ADD_LONG"
                    submit_after_open = True
                    session_reason = "regular_session_open"
                    order_session_type = "regular"
                    order_session_route = "regular"
                    session_queue_type = "regular_session_queue"
                    session_go_no_go = "go"
                    session_gate_result = "pass"
                    session_queue_reason = "regular_session_open"
                else:
                    submit_after_open = False
                    queue_activation_time = session_snapshot.get("next_open_at")
                    premarket_submission_allowed = bool(
                        premarket_enabled
                        and premarket_live_session
                        and extended_hours_available
                        and liquidity_ok
                        and spread_ok
                        and gap_ok
                        and alignment_ok
                        and (not premarket_top_rank_only or top_rank_candidate)
                        and kronos_timing_bias == "submit_now"
                        and kronos_preferred_action in {"PREMARKET_OPEN_LONG", "PREMARKET_ADD_LONG", "REGULAR_SESSION_OPEN_LONG"}
                    )

                    if premarket_submission_allowed:
                        session_order_plan = "submit_before_open"
                        session_preferred_action = "PREMARKET_OPEN_LONG" if requested_action == "OPEN_LONG" else "PREMARKET_ADD_LONG"
                        submit_before_open = True
                        premarket_live_candidate = True
                        extended_hours_eligible = True
                        premarket_submit_reason = "kronos_supports_premarket_entry"
                        session_reason = premarket_submit_reason
                        order_session_type = "premarket"
                        order_session_route = "extended_hours"
                        session_tif = "day"
                        session_queue_type = "premarket_queue"
                        session_go_no_go = "go"
                        session_gate_result = "pass"
                        session_queue_reason = premarket_submit_reason
                    elif not premarket_enabled:
                        premarket_submission_block_reason = "extended_hours_not_allowed"
                    elif not premarket_live_session:
                        premarket_submission_block_reason = "wait_for_open_confirmation"
                    elif not extended_hours_available:
                        premarket_submission_block_reason = "extended_hours_not_allowed"
                    elif not liquidity_ok:
                        premarket_submission_block_reason = "premarket_liquidity_too_low"
                    elif not spread_ok:
                        premarket_submission_block_reason = "premarket_spread_too_wide"
                    elif not gap_ok:
                        premarket_submission_block_reason = "gap_excessive_wait_for_open"
                    elif premarket_top_rank_only and not top_rank_candidate:
                        premarket_submission_block_reason = "weak_rank_not_allowed_premarket"
                    elif not alignment_ok:
                        premarket_submission_block_reason = "weak_engine_alignment"
                    elif opening_chase_guard_enabled and str(kronos_timing_bias) == "wait":
                        premarket_submission_block_reason = "opening_chase_risk_too_high"
                    else:
                        premarket_submission_block_reason = "wait_for_open_confirmation"

                    if session_order_plan != "submit_before_open" and queued_for_open_enabled and strong_open_candidate and (
                        kronos_timing_bias in {"queue_for_open", "submit_now"}
                        or preopen_preparation_session
                        or opening_handoff_session
                        or fully_closed_session
                        or overnight_supported_session
                    ):
                        session_order_plan = "queue_for_open"
                        session_preferred_action = "QUEUE_FOR_OPEN_LONG" if requested_action == "OPEN_LONG" else "QUEUE_FOR_OPEN_ADD"
                        queued_for_open = True
                        opening_auction_candidate = True
                        queued_for_open_reason = (
                            "capital_reserved_for_better_open_candidate"
                            if premarket_submission_block_reason in {"premarket_liquidity_too_low", "premarket_spread_too_wide", "gap_excessive_wait_for_open"}
                            else "queued_for_open_due_to_better_opening_structure"
                        )
                        session_reason = queued_for_open_reason
                        order_session_type = "opening_auction"
                        order_session_route = "queue_for_open"
                        session_tif = "opg"
                        row["kronos_overrode_session_timing"] = kronos_timing_bias != "wait"
                        session_queue_type = "queued_for_open_queue"
                        waiting_for_market_open = True
                        session_go_no_go = "wait"
                        session_gate_result = "deferred"
                        session_queue_reason = queued_for_open_reason
                    elif wait_for_open_enabled and (needs_open_confirmation or strong_premarket_candidate):
                        session_order_plan = "wait_for_open_confirmation"
                        session_preferred_action = "WAIT_FOR_OPEN_CONFIRMATION"
                        wait_for_open_confirmation = True
                        wait_for_open_reason = str(
                            kronos_row.get("kronos_no_trade_reason")
                            or premarket_submission_block_reason
                            or "wait_for_open_confirmation"
                        )
                        session_reason = wait_for_open_reason
                        order_session_type = "open_confirmation"
                        order_session_route = "delayed"
                        session_queue_type = "queued_for_open_queue"
                        waiting_for_market_open = True
                        waiting_for_open_revalidation = True
                        session_go_no_go = "wait"
                        session_gate_result = "deferred"
                        session_queue_reason = wait_for_open_reason
                    else:
                        session_order_plan = "no_trade_before_open"
                        no_trade_before_open_reason = (
                            premarket_submission_block_reason
                            or ("low_quality_gap" if not strong_open_candidate and not strong_premarket_candidate else "regular_session_only_strategy")
                        )
                        session_reason = no_trade_before_open_reason
                        session_preferred_action = "NO_ACTION"
                        order_session_type = "regular"
                        order_session_route = "delayed"
                        session_queue_type = "planning_queue"
                        session_go_no_go = "no_go"
                        session_gate_result = "blocked"
                        session_queue_reason = no_trade_before_open_reason
            elif requested_action in {"REDUCE_LONG", "EXIT_LONG"} and not market_open:
                session_preferred_action = requested_action
                if premarket_enabled and extended_hours_available and (premarket_live_session or after_hours_session):
                    session_order_plan = "submit_before_open"
                    submit_before_open = True
                    extended_hours_eligible = True
                    session_reason = "risk_exit_preopen_allowed"
                    premarket_submit_reason = session_reason
                    order_session_type = "premarket"
                    order_session_route = "extended_hours"
                    session_queue_type = "reduction_before_open_queue"
                    session_go_no_go = "go"
                    session_gate_result = "pass"
                    session_queue_reason = session_reason
                else:
                    session_order_plan = "queue_for_open"
                    queued_for_open = True
                    session_reason = "risk_exit_waiting_open"
                    queued_for_open_reason = session_reason
                    order_session_type = "opening_auction"
                    order_session_route = "queue_for_open"
                    session_tif = "opg"
                    session_queue_type = "reduction_before_open_queue"
                    waiting_for_market_open = True
                    session_go_no_go = "wait"
                    session_gate_result = "deferred"
                    session_queue_reason = session_reason
            else:
                session_order_plan = "no_action"
                session_preferred_action = requested_action or ("HOLD" if str(row.get("planned_execution_action") or "").strip().upper() == "HOLD" else "NO_ACTION")
                session_queue_type = "planning_queue"
                session_go_no_go = "no_go"
                session_gate_result = "blocked"
                session_queue_reason = "no_action"

            if bool(premarket_live_candidate):
                premarket_exposure_used += max(capital_approved_value, 0.0)

            session_context = {
                "session_state": session_state,
                "session_preferred_action": session_preferred_action,
                "session_order_plan": session_order_plan,
                "session_quality": session_quality,
                "estimated_slippage_risk": (
                    "high" if spread_risk_score > session_slippage_tolerance or volatility_risk_score >= 68.0 else "medium" if spread_risk_score > 28.0 else "low"
                ),
                "order_session_type": order_session_type,
                "session_order_style_preference": session_order_style,
                "session_time_in_force_preference": session_tif,
                "order_session_route": order_session_route,
                "extended_hours_eligible": bool(extended_hours_eligible),
                "queued_for_open": bool(queued_for_open),
                "opening_auction_candidate": bool(opening_auction_candidate),
                "premarket_live_candidate": bool(premarket_live_candidate),
                "submit_before_open": bool(submit_before_open),
                "submit_after_open": bool(submit_after_open),
                "wait_for_open_confirmation": bool(wait_for_open_confirmation),
                "session_reason": session_reason,
                "premarket_submit_reason": premarket_submit_reason,
                "queued_for_open_reason": queued_for_open_reason,
                "wait_for_open_reason": wait_for_open_reason,
                "no_trade_before_open_reason": no_trade_before_open_reason,
                "premarket_submission_allowed": bool(premarket_submission_allowed),
                "premarket_submission_block_reason": premarket_submission_block_reason,
                "session_queue_type": session_queue_type,
                "queue_activation_time": queue_activation_time,
                "queue_expiration_time": queue_expiration_time,
                "waiting_for_market_open": bool(waiting_for_market_open),
                "waiting_for_open_revalidation": bool(waiting_for_open_revalidation),
                "session_go_no_go": session_go_no_go,
                "session_gate_result": session_gate_result,
                "session_queue_reason": session_queue_reason,
                "session_order_risk_flags": session_risk_flags,
                "kronos_ready": bool(kronos_ready),
                "kronos_score": kronos_row.get("kronos_score"),
                "kronos_confidence": kronos_row.get("kronos_confidence"),
                "kronos_premarket_score": kronos_row.get("kronos_premarket_score"),
                "kronos_opening_score": kronos_row.get("kronos_opening_score"),
                "kronos_session_preferred_action": kronos_preferred_action,
                "kronos_execution_timing_bias": kronos_timing_bias,
                "kronos_wait_reason": kronos_row.get("kronos_no_trade_reason"),
                "kronos_warning_flags": kronos_row.get("kronos_warning_flags") if isinstance(kronos_row.get("kronos_warning_flags"), list) else [],
                "kronos_expected_volatility": kronos_row.get("kronos_expected_volatility"),
                "kronos_volatility_risk": kronos_row.get("kronos_volatility_risk"),
            }
            row.update(session_context)

            override = decision_overrides.get(sym)
            if not isinstance(override, dict):
                override = {}
            override.update(
                {
                    **session_context,
                    "kronos_weight": row.get("kronos_weight"),
                    "kronos_contribution_to_score": row.get("kronos_contribution_to_score"),
                    "kronos_contribution_reason": row.get("kronos_contribution_reason"),
                    "kronos_modified_target_position_pct": row.get("kronos_modified_target_position_pct"),
                    "kronos_modified_funding_ratio": row.get("kronos_modified_funding_ratio"),
                    "kronos_modified_execution_priority": row.get("kronos_modified_execution_priority"),
                }
            )
            decision_overrides[sym] = override

        premarket_candidate_count = sum(1 for row in (decision_rows or []) if bool(row.get("premarket_live_candidate")))
        queued_for_open_count = sum(1 for row in (decision_rows or []) if bool(row.get("queued_for_open")))
        wait_for_open_count = sum(1 for row in (decision_rows or []) if bool(row.get("wait_for_open_confirmation")))
        preopen_reduce_candidates = [
            row for row in (decision_rows or [])
            if str(row.get("requested_execution_action") or "").strip().upper() in {"REDUCE_LONG", "EXIT_LONG"}
        ]

        requested_premarket_capital = sum(float(row.get("capital_approved_value") or 0.0) for row in (decision_rows or []) if bool(row.get("premarket_live_candidate")))
        queued_for_open_budget = round(
            sum(float(row.get("capital_approved_value") or 0.0) for row in (decision_rows or []) if bool(row.get("queued_for_open"))),
            4,
        )
        wait_for_open_budget = round(
            sum(float(row.get("capital_approved_value") or 0.0) for row in (decision_rows or []) if bool(row.get("wait_for_open_confirmation"))),
            4,
        )
        premarket_capital_budget = round(min(requested_premarket_capital, cash_remaining * premarket_size_multiplier), 4)
        capital_reserved_for_open = round(min(cash_remaining, queued_for_open_budget + wait_for_open_budget + (cash_remaining * capital_reserve_for_open_pct / 100.0 if not market_open else 0.0)), 4)
        session_adjusted_capital_budget = round(max(cash_remaining, 0.0), 4)
        premarket_exposure_remaining = round(max(premarket_capital_budget - premarket_exposure_used, 0.0), 4)
        capital_reserved_for_open_reason = (
            "capital_reserved_for_better_open_candidate"
            if capital_reserved_for_open > 0 and (queued_for_open_count > 0 or wait_for_open_count > 0)
            else "no_open_reserve_needed"
        )
        desk_brief_rows = sorted(
            [item for item in (decision_rows or []) if isinstance(item, dict)],
            key=lambda item: float(item.get("session_adjusted_opportunity_score") or item.get("opportunity_score") or 0.0),
            reverse=True,
        )
        risk_flag_counts = Counter(
            flag
            for row in desk_brief_rows
            for flag in (
                (row.get("session_order_risk_flags") if isinstance(row.get("session_order_risk_flags"), list) else [])
                + (row.get("warning_flags") if isinstance(row.get("warning_flags"), list) else [])
            )
            if flag
        )
        premarket_candidates_payload = [
            {
                "symbol": row.get("symbol"),
                "session_preferred_action": row.get("session_preferred_action"),
                "session_order_plan": row.get("session_order_plan"),
                "session_adjusted_opportunity_score": row.get("session_adjusted_opportunity_score"),
                "premarket_score": row.get("premarket_score"),
                "opening_score": row.get("opening_score"),
                "premarket_submit_reason": row.get("premarket_submit_reason"),
            }
            for row in desk_brief_rows
            if bool(row.get("premarket_live_candidate"))
        ][:8]
        queued_for_open_candidates_payload = [
            {
                "symbol": row.get("symbol"),
                "session_preferred_action": row.get("session_preferred_action"),
                "session_order_plan": row.get("session_order_plan"),
                "session_adjusted_opportunity_score": row.get("session_adjusted_opportunity_score"),
                "queued_for_open_reason": row.get("queued_for_open_reason"),
                "portfolio_priority_rank": row.get("portfolio_priority_rank"),
            }
            for row in desk_brief_rows
            if bool(row.get("queued_for_open"))
        ][:8]
        wait_for_open_confirmation_candidates_payload = [
            {
                "symbol": row.get("symbol"),
                "session_preferred_action": row.get("session_preferred_action"),
                "session_order_plan": row.get("session_order_plan"),
                "session_adjusted_opportunity_score": row.get("session_adjusted_opportunity_score"),
                "wait_for_open_reason": row.get("wait_for_open_reason"),
                "open_confirmation_score": row.get("open_confirmation_score"),
            }
            for row in desk_brief_rows
            if bool(row.get("wait_for_open_confirmation"))
        ][:8]
        preopen_reduce_candidates_payload = [
            {
                "symbol": row.get("symbol"),
                "session_preferred_action": row.get("session_preferred_action"),
                "requested_execution_action": row.get("requested_execution_action"),
                "decision_outcome_code": row.get("decision_outcome_code"),
                "session_order_plan": row.get("session_order_plan"),
                "current_position_pct": row.get("current_position_pct"),
            }
            for row in preopen_reduce_candidates[:8]
        ]
        no_trade_reasons_payload = dict(
            Counter(
                str(row.get("no_trade_before_open_reason") or row.get("wait_for_open_reason") or row.get("premarket_submission_block_reason") or "").strip()
                for row in desk_brief_rows
                if str(row.get("no_trade_before_open_reason") or row.get("wait_for_open_reason") or row.get("premarket_submission_block_reason") or "").strip()
            )
        )

        readiness_payload.update({
            "ready_for_open": bool(
                session_snapshot.get("is_trading_day")
                and not market_open
                and readiness_completed_percent >= 50.0
                and (queued_for_open_count > 0 or wait_for_open_count > 0 or premarket_candidate_count > 0)
            ),
            "premarket_candidate_count": premarket_candidate_count,
            "queued_for_open_count": queued_for_open_count,
            "wait_for_open_confirmation_count": wait_for_open_count,
            "session_adjusted_capital_budget": session_adjusted_capital_budget,
            "premarket_capital_budget": premarket_capital_budget,
            "queued_for_open_budget": queued_for_open_budget,
            "wait_for_open_budget": wait_for_open_budget,
            "capital_reserved_for_open": capital_reserved_for_open,
            "capital_reserved_for_open_reason": capital_reserved_for_open_reason,
            "premarket_exposure_used": round(premarket_exposure_used, 4),
            "premarket_exposure_remaining": premarket_exposure_remaining,
            "premarket_size_multiplier": premarket_size_multiplier,
            "opening_size_multiplier": opening_size_multiplier,
            "premarket_candidates": premarket_candidates_payload,
            "queued_for_open_candidates": queued_for_open_candidates_payload,
            "wait_for_open_confirmation_candidates": wait_for_open_confirmation_candidates_payload,
            "preopen_reduce_candidates": preopen_reduce_candidates_payload,
            "no_trade_reasons": no_trade_reasons_payload,
            "engine_status": analysis_engines_snapshot if isinstance(analysis_engines_snapshot, dict) else {},
            "market_judgment": portfolio_brain_payload.get("market_judgment") if isinstance(portfolio_brain_payload.get("market_judgment"), dict) else {},
            "portfolio_sleeves": portfolio_brain_payload.get("portfolio_sleeves") if isinstance(portfolio_brain_payload.get("portfolio_sleeves"), dict) else {},
            "self_governed_limits": portfolio_brain_payload.get("self_governed_limits") if isinstance(portfolio_brain_payload.get("self_governed_limits"), dict) else {},
            "judgment_summary": portfolio_brain_payload.get("judgment_summary") if isinstance(portfolio_brain_payload.get("judgment_summary"), dict) else {},
            "daily_review": ((portfolio_brain_payload.get("self_review") or {}).get("daily_review") if isinstance(portfolio_brain_payload.get("self_review"), dict) else {}),
            "weekly_review": ((portfolio_brain_payload.get("self_review") or {}).get("weekly_review") if isinstance(portfolio_brain_payload.get("self_review"), dict) else {}),
            "top_ranked_symbols": [
                {
                    "symbol": row.get("symbol"),
                    "portfolio_priority_rank": row.get("portfolio_priority_rank"),
                    "opportunity_score": row.get("opportunity_score"),
                    "session_adjusted_opportunity_score": row.get("session_adjusted_opportunity_score"),
                    "stock_quality_score": row.get("stock_quality_score"),
                    "news_strength_score": row.get("news_strength_score"),
                    "session_preferred_action": row.get("session_preferred_action"),
                    "session_order_plan": row.get("session_order_plan"),
                    "kronos_score": row.get("kronos_score"),
                    "kronos_session_preferred_action": row.get("kronos_session_preferred_action"),
                }
                for row in desk_brief_rows[:12]
            ],
            "desk_brief": {
                "session_state": session_state,
                "readiness_phase": session_snapshot.get("readiness_phase"),
                "market_open": bool(session_snapshot.get("market_open", False)),
                "session_quality": session_quality,
                "regime": portfolio_brain_payload.get("regime") if isinstance(portfolio_brain_payload.get("regime"), dict) else {},
                "market_judgment": portfolio_brain_payload.get("market_judgment") if isinstance(portfolio_brain_payload.get("market_judgment"), dict) else {},
                "portfolio_sleeves": portfolio_brain_payload.get("portfolio_sleeves") if isinstance(portfolio_brain_payload.get("portfolio_sleeves"), dict) else {},
                "self_governed_limits": portfolio_brain_payload.get("self_governed_limits") if isinstance(portfolio_brain_payload.get("self_governed_limits"), dict) else {},
                "top_ranked_ideas": [
                    {
                        "symbol": row.get("symbol"),
                        "rank": row.get("portfolio_priority_rank"),
                        "score": row.get("session_adjusted_opportunity_score"),
                        "action": row.get("session_preferred_action"),
                        "plan": row.get("session_order_plan"),
                    }
                    for row in desk_brief_rows[:10]
                ],
                "strongest_current_holdings": [
                    {
                        "symbol": row.get("symbol"),
                        "current_position_pct": row.get("current_position_pct"),
                        "target_position_pct": row.get("target_position_pct"),
                        "action": row.get("requested_execution_action"),
                    }
                    for row in sorted(
                        [row for row in desk_brief_rows if float(row.get("current_position_pct") or 0.0) > 0.0],
                        key=lambda item: float(item.get("current_position_pct") or 0.0),
                        reverse=True,
                    )[:8]
                ],
                "premarket_candidates": premarket_candidates_payload,
                "queued_for_open_candidates": queued_for_open_candidates_payload,
                "wait_for_open_confirmation_candidates": wait_for_open_confirmation_candidates_payload,
                "preopen_reduce_candidates": preopen_reduce_candidates_payload,
                "rotation_opportunities": ((portfolio_brain_payload.get("judgment_summary") or {}).get("rotation_opportunities") if isinstance(portfolio_brain_payload.get("judgment_summary"), dict) else []),
                "why_not_buying": ((portfolio_brain_payload.get("judgment_summary") or {}).get("why_not_buying") if isinstance(portfolio_brain_payload.get("judgment_summary"), dict) else []),
                "small_cap_tactical_candidates": ((portfolio_brain_payload.get("judgment_summary") or {}).get("small_cap_tactical_candidates") if isinstance(portfolio_brain_payload.get("judgment_summary"), dict) else []),
                "top_risk_flags": dict(risk_flag_counts.most_common(8)),
                "reserved_capital": capital_reserved_for_open,
                "reserved_capital_reason": capital_reserved_for_open_reason,
                "expected_first_actions_after_open": [
                    {
                        "symbol": row.get("symbol"),
                        "plan": row.get("session_order_plan"),
                        "reason": row.get("queued_for_open_reason") or row.get("wait_for_open_reason") or row.get("session_reason"),
                    }
                    for row in desk_brief_rows
                    if bool(row.get("queued_for_open")) or bool(row.get("wait_for_open_confirmation"))
                ][:8],
                "model_health": {
                    "classic": (analysis_engines_snapshot.get("classic") if isinstance(analysis_engines_snapshot, dict) else {}),
                    "ranking": (analysis_engines_snapshot.get("ranking") if isinstance(analysis_engines_snapshot, dict) else {}),
                    "ml": (analysis_engines_snapshot.get("ml") if isinstance(analysis_engines_snapshot, dict) else {}),
                    "dl": (analysis_engines_snapshot.get("dl") if isinstance(analysis_engines_snapshot, dict) else {}),
                    "kronos": (analysis_engines_snapshot.get("kronos") if isinstance(analysis_engines_snapshot, dict) else {}),
                },
            },
        })

        if isinstance(portfolio_brain_payload, dict):
            portfolio_brain_payload["session"] = session_snapshot
            portfolio_brain_payload["kronos"] = {
                "status": kronos_runtime_status,
                "batch_summary": kronos_batch_payload.get("summary") if isinstance(kronos_batch_payload.get("summary"), dict) else {},
            }
            portfolio_brain_payload["market_readiness"] = readiness_payload

        for row in selected_execution_candidates:
            sym = str(row.get("symbol") or "").strip().upper()
            if not sym:
                continue
            queue_item = queue_by_symbol.get(sym, {}) if isinstance(queue_by_symbol.get(sym, {}), dict) else {}
            override = decision_overrides.get(sym)
            if not isinstance(override, dict):
                override = {}

            if queue_item:
                override.update(
                    {
                        "queue_item_id": queue_item.get("queue_item_id"),
                        "execution_stage": queue_item.get("execution_stage"),
                        "queue_rank": queue_item.get("queue_rank"),
                        "queue_reason": queue_item.get("queue_reason"),
                        "dependency_type": queue_item.get("dependency_type"),
                        "depends_on_queue_item_ids": queue_item.get("depends_on_queue_item_ids") if isinstance(queue_item.get("depends_on_queue_item_ids"), list) else [],
                        "requires_capital_release": bool(queue_item.get("requires_capital_release", False)),
                        "dependency_satisfied": bool(queue_item.get("dependency_satisfied", False)),
                        "dependency_outcome": queue_item.get("dependency_outcome"),
                        "queue_status": queue_item.get("queue_status"),
                        "queue_gate_result": queue_item.get("queue_gate_result"),
                        "queue_gate_reason": queue_item.get("queue_gate_reason"),
                        "execution_go_no_go": queue_item.get("execution_go_no_go"),
                        "defer_reason": queue_item.get("defer_reason"),
                        "submission_order": queue_item.get("submission_order"),
                        "queue_submitted_at_offset_seconds": queue_item.get("queue_submitted_at_offset_seconds"),
                        "queue_wait_seconds": queue_item.get("queue_wait_seconds"),
                        "liquidity_quality": queue_item.get("liquidity_quality"),
                    }
                )
                if not override.get("execution_skip_reason") and str(queue_item.get("queue_status") or "") in {"deferred", "waiting_for_prerequisite", "skipped"}:
                    override["execution_skip_reason"] = (
                        queue_item.get("queue_gate_reason")
                        or queue_item.get("blocking_reason")
                        or queue_item.get("defer_reason")
                    )
                row.update(
                    {
                        "queue_item_id": queue_item.get("queue_item_id"),
                        "execution_stage": queue_item.get("execution_stage"),
                        "queue_rank": queue_item.get("queue_rank"),
                        "queue_status": queue_item.get("queue_status"),
                        "queue_reason": queue_item.get("queue_reason"),
                        "queue_gate_result": queue_item.get("queue_gate_result"),
                        "queue_gate_reason": queue_item.get("queue_gate_reason"),
                        "execution_go_no_go": queue_item.get("execution_go_no_go"),
                        "defer_reason": queue_item.get("defer_reason"),
                        "dependency_type": queue_item.get("dependency_type"),
                        "depends_on_queue_item_ids": queue_item.get("depends_on_queue_item_ids") if isinstance(queue_item.get("depends_on_queue_item_ids"), list) else [],
                        "dependency_satisfied": queue_item.get("dependency_satisfied"),
                        "dependency_outcome": queue_item.get("dependency_outcome"),
                        "liquidity_quality": queue_item.get("liquidity_quality"),
                    }
                )
            decision_overrides[sym] = override

        dispatch_symbols = [
            str(symbol).strip().upper()
            for symbol in (execution_orchestrator.get("dispatch_symbols") or [])
            if str(symbol).strip()
        ]
        if not dispatch_symbols:
            dispatch_symbols = [
                str(item.get("symbol") or "").strip().upper()
                for item in queue_items
                if str(item.get("queue_status") or "") == "submitted"
                and str(item.get("requested_execution_action") or "").strip().upper() in {"OPEN_LONG", "ADD_LONG", "REDUCE_LONG", "EXIT_LONG"}
                and str(item.get("symbol") or "").strip()
            ]

        symbols = list(dict.fromkeys(dispatch_symbols))
        dispatch_symbol_set = set(symbols)

        for row in selected_execution_candidates:
            sym = str(row.get("symbol") or "").upper()
            if sym not in dispatch_symbol_set:
                continue
            qty = float(row.get("approved_order_qty") or row.get("proposed_order_qty") or 0.0)
            if sym and qty > 0:
                allocated_quantities[sym] = qty

        if not allocated_quantities and symbols:
            for sym in symbols:
                qty = _compute_qty(sym, budget=float(notional_per_trade))
                if qty > 0:
                    allocated_quantities[sym.upper()] = qty

        result = refresh_signals(
            symbols=symbols,
            mode=strategy_mode,
            start_date=start_date,
            end_date=end_date,
            auto_execute=True,
            quantity=fallback_qty,
            quantity_map=allocated_quantities,
            decision_overrides=decision_overrides,
        )
        aggregate_items = list(result.get("items", []))
        last_correlation = result.get("correlation_id") or last_correlation

        decision_by_symbol = {
            str(row.get("symbol") or "").upper(): row
            for row in (decision_rows or [])
            if isinstance(row, dict) and row.get("symbol")
        }

        enriched_items: list[dict] = []
        seen_symbols: set[str] = set()
        for item in aggregate_items:
            sym = str(item.get("symbol") or "").upper()
            seen_symbols.add(sym)
            decision = decision_by_symbol.get(sym, {})
            preview = preview_by_symbol.get(sym, {})

            enriched = dict(item)
            if "analysis_score" not in enriched:
                enriched["analysis_score"] = float(preview.get("analysis_score") or 0.0)
            if "analysis" not in enriched and isinstance(preview.get("result"), dict):
                enriched["analysis"] = preview.get("result")
            if decision:
                enriched.update(
                    {
                        "opportunity_score": decision.get("opportunity_score"),
                        "conviction_tier": decision.get("conviction_tier"),
                        "setup_type": decision.get("setup_type"),
                        "expected_direction": decision.get("expected_direction"),
                        "preferred_action_candidate": decision.get("preferred_action_candidate"),
                        "preferred_holding_horizon": decision.get("preferred_holding_horizon"),
                        "risk_reward_estimate": decision.get("risk_reward_estimate"),
                        "quality_flags": decision.get("quality_flags") or [],
                        "warning_flags": decision.get("warning_flags") or [],
                        "portfolio_priority_rank": decision.get("portfolio_priority_rank"),
                        "target_position_pct": decision.get("target_position_pct"),
                        "current_position_pct": decision.get("current_position_pct"),
                        "desired_delta_pct": decision.get("desired_delta_pct"),
                        "capital_competition_reason": decision.get("capital_competition_reason"),
                        "replacement_candidate": decision.get("replacement_candidate"),
                        "portfolio_brain_requested_action": decision.get("requested_execution_action"),
                        "portfolio_brain_decision_code": decision.get("decision_outcome_code"),
                        "portfolio_brain_decision_detail": decision.get("decision_outcome_detail"),
                        "proposed_order_qty": decision.get("proposed_order_qty"),
                    "requested_order_qty": decision.get("requested_order_qty"),
                    "approved_order_qty": decision.get("approved_order_qty"),
                    "approved_position_pct": decision.get("approved_position_pct"),
                    "funded_partially": decision.get("funded_partially"),
                    "funding_status": decision.get("funding_status"),
                    "funding_ratio": decision.get("funding_ratio"),
                    "partial_funding_reason": decision.get("partial_funding_reason"),
                    "capital_requested_value": decision.get("capital_requested_value"),
                    "capital_approved_value": decision.get("capital_approved_value"),
                    "execution_priority_band": decision.get("execution_priority_band"),
                        "execution_priority": decision.get("execution_priority"),
                        "order_style_preference": decision.get("order_style_preference"),
                        "execution_skip_reason": decision.get("execution_skip_reason") or item.get("execution_skip_reason"),
                        "queue_item_id": decision.get("queue_item_id"),
                        "execution_stage": decision.get("execution_stage"),
                        "queue_rank": decision.get("queue_rank"),
                        "queue_status": decision.get("queue_status"),
                        "queue_reason": decision.get("queue_reason"),
                        "queue_gate_result": decision.get("queue_gate_result"),
                        "queue_gate_reason": decision.get("queue_gate_reason"),
                        "execution_go_no_go": decision.get("execution_go_no_go"),
                        "defer_reason": decision.get("defer_reason"),
                        "dependency_type": decision.get("dependency_type"),
                        "depends_on_queue_item_ids": decision.get("depends_on_queue_item_ids") if isinstance(decision.get("depends_on_queue_item_ids"), list) else [],
                        "dependency_satisfied": decision.get("dependency_satisfied"),
                        "dependency_outcome": decision.get("dependency_outcome"),
                        "submission_order": decision.get("submission_order"),
                        "queue_submitted_at_offset_seconds": decision.get("queue_submitted_at_offset_seconds"),
                        "queue_wait_seconds": decision.get("queue_wait_seconds"),
                        "liquidity_quality": decision.get("liquidity_quality"),
                    }
                )
            enriched_items.append(enriched)

        for sym, decision in decision_by_symbol.items():
            if sym in seen_symbols:
                continue
            preview = preview_by_symbol.get(sym, {})
            enriched_items.append(
                {
                    "symbol": sym,
                    "strategy_mode": strategy_mode,
                    "signal": str(preview.get("signal") or decision.get("analysis_signal") or "HOLD").upper(),
                    "confidence": float(preview.get("confidence") or decision.get("confidence") or 0.0),
                    "price": float(preview.get("price") or decision.get("price") or 0.0),
                    "reasoning": str(preview.get("result", {}).get("setup_type") or preview.get("result", {}).get("reasons") or "portfolio decision only"),
                    "analysis_score": float(preview.get("analysis_score") or decision.get("analysis_score") or 0.0),
                    "analysis": preview.get("result") if isinstance(preview.get("result"), dict) else {},
                    "opportunity_score": decision.get("opportunity_score"),
                    "conviction_tier": decision.get("conviction_tier"),
                    "setup_type": decision.get("setup_type"),
                    "expected_direction": decision.get("expected_direction"),
                    "preferred_action_candidate": decision.get("preferred_action_candidate"),
                    "preferred_holding_horizon": decision.get("preferred_holding_horizon"),
                    "risk_reward_estimate": decision.get("risk_reward_estimate"),
                    "quality_flags": decision.get("quality_flags") or [],
                    "warning_flags": decision.get("warning_flags") or [],
                    "portfolio_priority_rank": decision.get("portfolio_priority_rank"),
                    "target_position_pct": decision.get("target_position_pct"),
                    "current_position_pct": decision.get("current_position_pct"),
                    "desired_delta_pct": decision.get("desired_delta_pct"),
                    "capital_competition_reason": decision.get("capital_competition_reason"),
                    "replacement_candidate": decision.get("replacement_candidate"),
                    "portfolio_brain_requested_action": decision.get("requested_execution_action"),
                    "portfolio_brain_decision_code": decision.get("decision_outcome_code"),
                    "portfolio_brain_decision_detail": decision.get("decision_outcome_detail"),
                    "proposed_order_qty": decision.get("proposed_order_qty"),
                    "requested_order_qty": decision.get("requested_order_qty"),
                    "approved_order_qty": decision.get("approved_order_qty"),
                    "approved_position_pct": decision.get("approved_position_pct"),
                    "funded_partially": decision.get("funded_partially"),
                    "funding_status": decision.get("funding_status"),
                    "funding_ratio": decision.get("funding_ratio"),
                    "partial_funding_reason": decision.get("partial_funding_reason"),
                    "capital_requested_value": decision.get("capital_requested_value"),
                    "capital_approved_value": decision.get("capital_approved_value"),
                    "execution_priority_band": decision.get("execution_priority_band"),
                    "execution_priority": decision.get("execution_priority"),
                    "order_style_preference": decision.get("order_style_preference"),
                    "execution_skip_reason": decision.get("execution_skip_reason"),
                    "queue_item_id": decision.get("queue_item_id"),
                    "execution_stage": decision.get("execution_stage"),
                    "queue_rank": decision.get("queue_rank"),
                    "queue_status": decision.get("queue_status"),
                    "queue_reason": decision.get("queue_reason"),
                    "queue_gate_result": decision.get("queue_gate_result"),
                    "queue_gate_reason": decision.get("queue_gate_reason"),
                    "execution_go_no_go": decision.get("execution_go_no_go"),
                    "defer_reason": decision.get("defer_reason"),
                    "dependency_type": decision.get("dependency_type"),
                    "depends_on_queue_item_ids": decision.get("depends_on_queue_item_ids") if isinstance(decision.get("depends_on_queue_item_ids"), list) else [],
                    "dependency_satisfied": decision.get("dependency_satisfied"),
                    "dependency_outcome": decision.get("dependency_outcome"),
                    "submission_order": decision.get("submission_order"),
                    "queue_submitted_at_offset_seconds": decision.get("queue_submitted_at_offset_seconds"),
                    "queue_wait_seconds": decision.get("queue_wait_seconds"),
                    "liquidity_quality": decision.get("liquidity_quality"),
                }
            )

        aggregate_items = enriched_items
        result["items"] = aggregate_items

        reconciliation_meta: dict = {}
        try:
            reconciliation_meta = _reconcile_execution_orchestrator_cycle(
                portfolio_brain_payload=portfolio_brain_payload if isinstance(portfolio_brain_payload, dict) else {},
                decision_rows=decision_rows if isinstance(decision_rows, list) else [],
                signal_items=aggregate_items,
                auto_config=auto_config if isinstance(auto_config, dict) else {},
                cycle_id=str(result.get("correlation_id") or lease_holder_id or f"cycle-{uuid4().hex[:8]}"),
            )
        except Exception as reconciliation_exc:
            reconciliation_meta = {
                "enabled": bool(auto_config.get("execution_reconciliation_enabled", True)),
                "applied": False,
                "reason": "reconciliation_exception",
                "error": str(reconciliation_exc),
            }
            log_event(
                logger,
                logging.WARNING,
                "automation.auto_trading.reconciliation_failed",
                cycle_id=str(result.get("correlation_id") or lease_holder_id or ""),
                error=str(reconciliation_exc),
            )

        if isinstance(portfolio_brain_payload, dict):
            portfolio_brain_payload["reconciliation"] = reconciliation_meta
        result["portfolio_brain"] = portfolio_brain_payload
        result["portfolio_brain_reconciliation"] = reconciliation_meta
        quantity = fallback_qty  # reported default; per-symbol used above
    except Exception as exc:
        return _return_with_lease_release(
            f"auto_trading_cycle failed: {exc}",
            [{"artifact_type": "auto_trading_error", "artifact_key": "execution_failed", "payload": {"error": str(exc)}}],
        )

    # Summarize results
    items = result.get("items", [])
    buy_signals = [i for i in items if i.get("signal") == "BUY"]
    sell_signals = [i for i in items if i.get("signal") == "SELL"]
    hold_signals = [i for i in items if i.get("signal") == "HOLD"]
    errors = [i for i in items if i.get("error")]

    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "universe_preset": universe_preset,
        "strategy_mode": strategy_mode,
        "trade_direction": trade_direction,
        "use_top_market_cap_rotation": use_top_market_cap_rotation,
        "broker_sync": broker_sync_result,
        "symbols_scanned": len(symbols),
        "symbol_limit": symbol_limit,
        "buy_signals": len(buy_signals),
        "sell_signals": len(sell_signals),
        "hold_signals": len(hold_signals),
        "errors": len(errors),
        "auto_executed": True,
        "quantity_per_trade": quantity,
        "full_portfolio_mode": full_portfolio_mode,
        "notional_per_trade": round(float(notional_per_trade or 0.0), 4),
        "portfolio_cash_balance": round(float(portfolio_cash_balance or 0.0), 4),
        "daily_risk": daily_loss_snapshot,
        "allocated_quantities": allocated_quantities,
        "correlation_id": result.get("correlation_id"),
        "rotation": rotation_state,
        "rotation_pool_size": len(ranked_universe_symbols),
        "top_buys": [
            {"symbol": i["symbol"], "confidence": i.get("confidence", 0), "price": i.get("price", 0)}
            for i in sorted(buy_signals, key=lambda x: x.get("confidence", 0), reverse=True)[:5]
        ],
        "portfolio": result.get("portfolio", {}),
    }

    summary["market_session"] = {
        "session_state": session_snapshot.get("session_state"),
        "session_code": session_snapshot.get("session_code"),
        "market_open": bool(session_snapshot.get("market_open", False)),
        "minutes_to_open": session_snapshot.get("minutes_to_open"),
        "minutes_to_close": session_snapshot.get("minutes_to_close"),
        "next_open_at": session_snapshot.get("next_open_at"),
        "next_close_at": session_snapshot.get("next_close_at"),
        "readiness_phase": session_snapshot.get("readiness_phase"),
        "extended_hours_available": bool(session_snapshot.get("extended_hours_available", False)),
        "opening_auction_window": bool(session_snapshot.get("opening_auction_window", False)),
    }
    summary["market_readiness"] = readiness_payload if isinstance(readiness_payload, dict) else {}
    summary["kronos"] = {
        "status": kronos_runtime_status if isinstance(kronos_runtime_status, dict) else {},
        "batch_summary": kronos_batch_payload.get("summary") if isinstance(kronos_batch_payload.get("summary"), dict) else {},
    }

    scheduler_runtime_state = "unknown"
    scheduler_delegated = False
    try:
        from backend.app.services.scheduler_runtime import get_scheduler_status

        scheduler_status = get_scheduler_status()
        scheduler_runtime_state = str(scheduler_status.get("runtime_state") or "unknown")
        scheduler_delegated = bool(scheduler_status.get("delegated", False))
    except Exception:
        scheduler_status = {}

    diagnostics_payload = build_auto_trading_diagnostics_payload(
        cycle_id=str(result.get("correlation_id") or lease_holder_id or f"cycle-{uuid4().hex[:8]}"),
        cycle_started_at=cycle_started_at.isoformat(),
        cycle_completed_at=datetime.utcnow().isoformat(),
        runtime_state=scheduler_runtime_state,
        delegated=scheduler_delegated,
        symbols=list(symbols),
        signal_items=items,
        preview_items=selected_execution_candidates,
        held_positions=held_positions,
        strategy_mode=strategy_mode,
        trade_direction=trade_direction,
        margin_enabled=margin_enabled,
        market_open=market_open,
        correlation_id=result.get("correlation_id"),
        portfolio_summary=(result.get("portfolio", {}) or {}).get("summary", result.get("portfolio", {})),
        auto_trading_config=auto_config,
        portfolio_brain=portfolio_brain_payload,
        market_session=session_snapshot,
        market_readiness=readiness_payload,
        kronos_payload={
            "status": kronos_runtime_status if isinstance(kronos_runtime_status, dict) else {},
            "batch_summary": kronos_batch_payload.get("summary") if isinstance(kronos_batch_payload.get("summary"), dict) else {},
            "symbols": kronos_batch_payload.get("symbols") if isinstance(kronos_batch_payload.get("symbols"), dict) else {},
        },
    )
    summary_counts = diagnostics_payload.get("summary_counts", {}) if isinstance(diagnostics_payload, dict) else {}
    summary.update(summary_counts)
    summary["signal_counts"] = {
        "signal_buy_count": summary_counts.get("signal_buy_count", len(buy_signals)),
        "signal_sell_count": summary_counts.get("signal_sell_count", len(sell_signals)),
        "signal_hold_count": summary_counts.get("signal_hold_count", len(hold_signals)),
    }
    summary["execution_counts"] = {
        "submitted_order_count": summary_counts.get("submitted_order_count", 0),
        "accepted_order_count": summary_counts.get("accepted_order_count", 0),
        "rejected_order_count": summary_counts.get("rejected_order_count", 0),
        "filled_order_count": summary_counts.get("filled_order_count", 0),
        "partially_filled_order_count": summary_counts.get("partially_filled_order_count", 0),
        "blocked_count": summary_counts.get("blocked_count", 0),
        "no_action_count": summary_counts.get("no_action_count", 0),
    }
    summary["decision_trace_note"] = "Analysis signals are distinct from broker execution outcomes."
    if isinstance(portfolio_brain_payload, dict):
        regime_payload = portfolio_brain_payload.get("regime") if isinstance(portfolio_brain_payload.get("regime"), dict) else {}
        allocation_summary = portfolio_brain_payload.get("allocation", {}).get("summary", {}) if isinstance(portfolio_brain_payload.get("allocation"), dict) else {}
        execution_orchestrator = portfolio_brain_payload.get("execution_orchestrator") if isinstance(portfolio_brain_payload.get("execution_orchestrator"), dict) else {}
        reconciliation_meta = portfolio_brain_payload.get("reconciliation") if isinstance(portfolio_brain_payload.get("reconciliation"), dict) else {}
        queue_summary = execution_orchestrator.get("summary") if isinstance(execution_orchestrator.get("summary"), dict) else {}
        summary["portfolio_brain"] = {
            "regime_code": regime_payload.get("regime_code"),
            "regime_bias": regime_payload.get("regime_bias"),
            "risk_multiplier": regime_payload.get("risk_multiplier"),
            "max_new_positions": regime_payload.get("max_new_positions"),
            "funded_count": allocation_summary.get("funded_count"),
            "symbols_considered": allocation_summary.get("symbols_considered"),
            "queue_total": queue_summary.get("queue_total"),
            "queue_submitted_count": queue_summary.get("submitted_count"),
            "queue_deferred_count": queue_summary.get("deferred_count"),
            "queue_waiting_count": queue_summary.get("waiting_count"),
            "queue_skipped_count": queue_summary.get("skipped_count"),
            "reconciliation_poll_count_total": queue_summary.get("reconciliation_poll_count_total"),
            "reconciliation_terminal_count": queue_summary.get("reconciliation_terminal_count"),
            "reconciliation_window_expired_count": queue_summary.get("reconciliation_window_expired_count"),
        }
        summary["execution_orchestrator"] = {
            "summary": queue_summary,
            "timeline_preview": execution_orchestrator.get("timeline", [])[:20] if isinstance(execution_orchestrator.get("timeline"), list) else [],
            "reconciliation": reconciliation_meta,
        }

    # Send Telegram notification
    try:
        from backend.app.services.trade_notifier import notify_auto_trading_summary
        notify_auto_trading_summary(
            symbols_scanned=len(symbols),
            buy_count=len(buy_signals),
            sell_count=len(sell_signals),
            hold_count=len(hold_signals),
            errors=len(errors),
            top_buys=summary.get("top_buys", []),
        )
    except Exception:
        pass

    detail = (
        f"auto_trading_cycle preset={universe_preset} mode={strategy_mode} direction={trade_direction} scanned={len(symbols)} buys={len(buy_signals)} "
        f"sells={len(sell_signals)} holds={len(hold_signals)} errors={len(errors)} submitted={summary_counts.get('submitted_order_count', 0)} "
        f"filled={summary_counts.get('filled_order_count', 0)} qty={quantity}"
    )

    artifacts = [
        {"artifact_type": "auto_trading_summary", "artifact_key": _utc_today_iso(), "payload": summary},
        {
            "artifact_type": "auto_trading_decision_trace",
            "artifact_key": str(result.get("correlation_id") or "latest"),
            "payload": diagnostics_payload,
        },
        {
            "artifact_type": "portfolio_brain_cycle",
            "artifact_key": str(result.get("correlation_id") or "latest"),
            "payload": portfolio_brain_payload,
        },
        {
            "artifact_type": "portfolio_brain_summary",
            "artifact_key": str(result.get("correlation_id") or "latest"),
            "payload": (portfolio_brain_payload.get("allocation", {}).get("summary", {}) if isinstance(portfolio_brain_payload, dict) else {}),
        },
        {
            "artifact_type": "market_session_status",
            "artifact_key": str(result.get("correlation_id") or "latest"),
            "payload": session_snapshot,
        },
        {
            "artifact_type": "market_open_readiness",
            "artifact_key": str(result.get("correlation_id") or "latest"),
            "payload": readiness_payload,
        },
        {
            "artifact_type": "kronos_intelligence",
            "artifact_key": str(result.get("correlation_id") or "latest"),
            "payload": {
                "status": kronos_runtime_status if isinstance(kronos_runtime_status, dict) else {},
                "batch_summary": kronos_batch_payload.get("summary") if isinstance(kronos_batch_payload.get("summary"), dict) else {},
            },
        },
        {"artifact_type": "auto_trading_signals", "artifact_key": "latest", "payload": items},
        {"artifact_type": "auto_trading_rotation", "artifact_key": universe_preset.lower(), "payload": rotation_state},
    ]

    return _return_with_lease_release(detail, artifacts)


def _is_us_market_open() -> bool:
    """Check if the US stock market is currently open (9:30 AM - 4:00 PM ET, weekdays)."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    now_et = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))

    # Weekend check
    if now_et.weekday() >= 5:
        return False

    # Market hours: 9:30 AM to 4:00 PM ET
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now_et <= market_close


def run_automation_job(job_name: str, dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> dict:
    normalized = str(job_name or "").strip().lower()
    started_at = datetime.utcnow()
    handlers = {
        "market_cycle": lambda: _market_cycle(dry_run=dry_run, preset=preset),
        "alert_cycle": lambda: _alert_cycle(dry_run=dry_run, preset=preset),
        "breadth_cycle": lambda: _breadth_cycle(dry_run=dry_run, preset=preset),
        "retrain_cycle": lambda: _retrain_cycle(dry_run=dry_run),
        "autonomous_cycle": lambda: _autonomous_cycle(dry_run=dry_run, preset=preset),
        "daily_summary": lambda: _daily_summary(dry_run=dry_run, preset=preset),
        "auto_trading_cycle": lambda: _auto_trading_cycle(dry_run=dry_run, preset=preset),
    }
    handler = handlers.get(normalized)
    if handler is None:
        return {"error": f"Unsupported automation job: {job_name}"}

    started_perf = perf_counter()
    log_event(logger, logging.INFO, "automation.run.started", job_name=normalized, dry_run=dry_run, preset=preset)
    try:
        detail, artifacts = handler()
        result = _record_run(normalized, "completed", started_at, dry_run, detail, artifacts)
        if normalized == "auto_trading_cycle":
            try:
                result["diagnostics_cleanup"] = cleanup_auto_trading_diagnostics_artifacts()
            except Exception as cleanup_exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "diagnostics.auto_trading.cleanup_failed",
                    error=str(cleanup_exc),
                    job_name=normalized,
                )
        result["duration_seconds"] = round(perf_counter() - started_perf, 4)
        log_event(logger, logging.INFO, "automation.run.completed", job_name=normalized, dry_run=dry_run, duration_seconds=result["duration_seconds"], artifacts=len(artifacts))
        return result
    except Exception as exc:
        result = _record_run(normalized, "error", started_at, dry_run, str(exc), [])
        result["duration_seconds"] = round(perf_counter() - started_perf, 4)
        result["error"] = str(exc)
        log_event(logger, logging.ERROR, "automation.run.failed", job_name=normalized, dry_run=dry_run, duration_seconds=result["duration_seconds"], error=str(exc))
        return result


def get_automation_status(limit: int = 20) -> dict:
    limit = max(1, min(int(limit or 20), 100))
    with session_scope() as session:
        rows = (
            session.query(AutomationRun)
            .order_by(AutomationRun.started_at.desc())
            .limit(limit)
            .all()
        )
        items = [
            {
                "run_id": row.run_id,
                "job_name": row.job_name,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "duration_seconds": row.duration_seconds,
                "dry_run": bool(row.dry_run),
                "detail": row.detail,
                "artifacts_count": row.artifacts_count,
            }
            for row in rows
        ]
        artifacts = (
            session.query(AutomationArtifact)
            .order_by(AutomationArtifact.created_at.desc())
            .limit(limit)
            .all()
        )
        latest_artifacts = [
            {
                "run_id": row.run_id,
                "job_name": row.job_name,
                "artifact_type": row.artifact_type,
                "artifact_key": row.artifact_key,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "payload": loads_json(row.payload_json),
            }
            for row in artifacts
        ]

    return {
        "jobs": [{"job_name": key, "label": value} for key, value in JOB_NAMES.items()],
        "recent_runs": items,
        "latest_artifacts": latest_artifacts,
        "auto_retrain_enabled": ENABLE_AUTO_RETRAIN,
        "autonomous_cycle_enabled": ENABLE_AUTONOMOUS_CYCLE,
        "autonomous_analysis_symbol_limit": AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT,
        "autonomous_train_symbol_limit": AUTONOMOUS_TRAIN_SYMBOL_LIMIT,
        "autonomous_include_dl": AUTONOMOUS_INCLUDE_DL,
    }
