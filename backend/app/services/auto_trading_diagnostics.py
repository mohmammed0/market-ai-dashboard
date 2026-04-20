from __future__ import annotations

from collections import Counter
import csv
from io import StringIO
import logging
from typing import Any

from backend.app.config import (
    AUTO_TRADING_DIAGNOSTICS_RETENTION_CYCLES,
    AUTO_TRADING_DIAGNOSTICS_RETENTION_DELETE_BATCH_SIZE,
    AUTO_TRADING_EXECUTION_RETRY_ENABLED,
    AUTO_TRADING_EXECUTION_RETRY_MAX_ATTEMPTS,
    AUTO_TRADING_EXECUTION_RETRY_INITIAL_BACKOFF_SECONDS,
    AUTO_TRADING_EXECUTION_RETRY_MAX_BACKOFF_SECONDS,
    AUTO_TRADING_EXECUTION_RETRY_BACKOFF_MULTIPLIER,
    AUTO_TRADING_EXECUTION_RETRY_JITTER_ENABLED,
    AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_BROKER_SUBMIT,
    AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_DEPENDENCY_WAIT,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.models import AutomationArtifact, AutomationRun
from backend.app.models.execution import ExecutionAuditEvent
from backend.app.models.platform_events import OrderEvent
from backend.app.services.storage import loads_json, session_scope


logger = get_logger(__name__)

_DIAGNOSTICS_JOB_NAME = "auto_trading_cycle"
_DIAGNOSTICS_ARTIFACT_TYPE = "auto_trading_decision_trace"
_DEFAULT_HEAVY_FIELDS = (
    "model_source_breakdown",
    "broker_event_timeline",
    "raw_audit_events",
    "raw_order_events",
)
_DEFAULT_RAW_FIELDS = (
    "analysis_payload",
    "raw_broker_payload",
)

_ADD_LONG_REASON_CODES = {
    "add_long_allowed",
    "at_target_position_size",
    "insufficient_add_conviction",
    "add_cooldown_active",
    "add_blocked_by_cash",
    "add_blocked_by_risk",
    "add_blocked_by_market_hours",
    "add_qty_below_minimum",
    "existing_long_position_no_add",
    "add_daily_limit_reached",
}
_NO_BROKER_ADD_LONG_REASON_CODES = _ADD_LONG_REASON_CODES - {"add_long_allowed"}

_EXECUTION_ACTIONS = {"OPEN_LONG", "ADD_LONG", "REDUCE_LONG", "EXIT_LONG", "CLOSE_LONG", "CLOSE_SHORT"}
_CAPITAL_RELEASE_ACTIONS = {"REDUCE_LONG", "EXIT_LONG", "CLOSE_LONG", "CLOSE_SHORT"}
_CAPITAL_DEPLOY_ACTIONS = {"OPEN_LONG", "ADD_LONG"}

_RETRYABLE_BROKER_MARKERS = {
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    return text not in {"0", "false", "no", "off"}


def _clamp(value: Any, low: float, high: float) -> float:
    return max(low, min(_safe_float(value, low), high))


def _safe_mean(values: list[Any], default: float = 0.0) -> float:
    cleaned = [_safe_float(value, 0.0) for value in values if value is not None]
    if not cleaned:
        return float(default)
    return float(sum(cleaned) / len(cleaned))


def _parse_iso(value: Any) -> Any:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        from datetime import datetime, timezone

        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _iso_with_offset(base_iso: str | None, seconds: float | int | None) -> str | None:
    base_dt = _parse_iso(base_iso)
    if base_dt is None:
        return None
    offset = _safe_float(seconds, 0.0)
    if abs(offset) <= 1e-9:
        return base_dt.isoformat()
    from datetime import timedelta

    return (base_dt + timedelta(seconds=offset)).isoformat()


def _cycle_retry_config(auto_trading_config: dict | None) -> dict:
    config = auto_trading_config if isinstance(auto_trading_config, dict) else {}
    return {
        "retry_enabled": _safe_bool(config.get("execution_retry_enabled"), AUTO_TRADING_EXECUTION_RETRY_ENABLED),
        "retry_max_attempts": max(
            _safe_int(config.get("execution_retry_max_attempts"), AUTO_TRADING_EXECUTION_RETRY_MAX_ATTEMPTS),
            1,
        ),
        "retry_initial_backoff_seconds": max(
            _safe_int(
                config.get("execution_retry_initial_backoff_seconds"),
                AUTO_TRADING_EXECUTION_RETRY_INITIAL_BACKOFF_SECONDS,
            ),
            1,
        ),
        "retry_max_backoff_seconds": max(
            _safe_int(
                config.get("execution_retry_max_backoff_seconds"),
                AUTO_TRADING_EXECUTION_RETRY_MAX_BACKOFF_SECONDS,
            ),
            1,
        ),
        "retry_backoff_multiplier": max(
            _safe_float(
                config.get("execution_retry_backoff_multiplier"),
                AUTO_TRADING_EXECUTION_RETRY_BACKOFF_MULTIPLIER,
            ),
            1.0,
        ),
        "retry_jitter_enabled": _safe_bool(
            config.get("execution_retry_jitter_enabled"),
            AUTO_TRADING_EXECUTION_RETRY_JITTER_ENABLED,
        ),
        "retry_allowed_for_broker_submit": _safe_bool(
            config.get("execution_retry_allowed_for_broker_submit"),
            AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_BROKER_SUBMIT,
        ),
        "retry_allowed_for_dependency_wait": _safe_bool(
            config.get("execution_retry_allowed_for_dependency_wait"),
            AUTO_TRADING_EXECUTION_RETRY_ALLOWED_FOR_DEPENDENCY_WAIT,
        ),
    }


def _compute_backoff_seconds(*, retry_config: dict, attempt_count: int) -> float:
    initial = max(_safe_float(retry_config.get("retry_initial_backoff_seconds"), 2.0), 1.0)
    max_backoff = max(_safe_float(retry_config.get("retry_max_backoff_seconds"), 20.0), 1.0)
    multiplier = max(_safe_float(retry_config.get("retry_backoff_multiplier"), 2.0), 1.0)
    exponent = max(int(attempt_count) - 1, 0)
    value = initial * (multiplier ** exponent)
    return round(min(max(value, 1.0), max_backoff), 3)


def _is_transient_broker_failure(reason: str | None) -> bool:
    lowered = str(reason or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _RETRYABLE_BROKER_MARKERS)


def _order_event_time(order_events: list[dict], *, event_type: str) -> str | None:
    for event in order_events or []:
        if str(event.get("event_type") or "").strip().lower() == event_type:
            return event.get("created_at")
    return None


def _derive_execution_state_fields(
    *,
    row: dict,
    queue_row: dict,
    order_events: list[dict],
    broker_enrichment: dict,
    cycle_started_at: str,
    cycle_completed_at: str,
    retry_config: dict,
) -> dict:
    queue_status = str(row.get("queue_status") or queue_row.get("queue_status") or "").strip().lower() or None
    queue_gate_reason = str(
        row.get("queue_gate_reason")
        or row.get("blocking_reason")
        or queue_row.get("queue_gate_reason")
        or queue_row.get("blocking_reason")
        or row.get("defer_reason")
        or ""
    ).strip().lower() or None
    requested_action = str(
        row.get("requested_execution_action")
        or row.get("derived_intent")
        or ""
    ).strip().upper()

    execution_engine_status = str(
        row.get("execution_engine_status")
        or queue_row.get("execution_engine_status")
        or ("queued" if requested_action in _EXECUTION_ACTIONS else "not_queued")
    ).strip().lower()
    if queue_status == "submitted":
        execution_engine_status = "submitted_to_execution_engine"
    elif queue_status == "waiting_for_prerequisite":
        execution_engine_status = "waiting_for_dependency"
    elif queue_status == "deferred":
        execution_engine_status = "deferred"
    elif queue_status == "skipped":
        execution_engine_status = "skipped"
    elif queue_status == "ready":
        execution_engine_status = "ready"

    submitted_to_execution_engine_at = (
        row.get("submitted_to_execution_engine_at")
        or queue_row.get("submitted_to_execution_engine_at")
        or _iso_with_offset(cycle_started_at, row.get("queue_submitted_at_offset_seconds"))
        or _iso_with_offset(cycle_started_at, queue_row.get("queue_submitted_at_offset_seconds"))
    )
    if execution_engine_status != "submitted_to_execution_engine":
        submitted_to_execution_engine_at = submitted_to_execution_engine_at if queue_status in {"submitted"} else None

    broker_submission_attempted_at = (
        row.get("broker_submission_attempted_at")
        or queue_row.get("broker_submission_attempted_at")
        or _order_event_time(order_events, event_type="execution.order.submitted")
    )
    broker_acknowledged_at = (
        row.get("broker_acknowledged_at")
        or queue_row.get("broker_acknowledged_at")
        or _order_event_time(order_events, event_type="execution.order.acknowledged")
    )
    broker_last_update_at = (
        row.get("broker_last_update_at")
        or queue_row.get("broker_last_update_at")
        or broker_enrichment.get("broker_last_status_at")
        or _order_event_time(order_events, event_type="execution.fill.received")
        or _order_event_time(order_events, event_type="execution.order.canceled")
    )

    broker_order_submitted = bool(
        row.get("broker_order_submitted")
        if row.get("broker_order_submitted") is not None
        else queue_row.get("broker_order_submitted", False)
    )
    trade_fill_status = str(
        row.get("trade_fill_status")
        or queue_row.get("trade_fill_status")
        or broker_enrichment.get("trade_fill_status")
        or "none"
    ).strip().lower()
    broker_order_status = str(
        row.get("broker_order_status")
        or queue_row.get("broker_order_status")
        or broker_enrichment.get("broker_order_status")
        or ""
    ).strip().lower()
    broker_rejection = str(
        row.get("broker_rejection_message")
        or row.get("broker_rejection_reason")
        or queue_row.get("broker_rejection_message")
        or queue_row.get("broker_rejection_reason")
        or broker_enrichment.get("broker_rejection_message")
        or ""
    ).strip()
    broker_skip_reason = str(
        row.get("broker_skip_reason")
        or queue_row.get("broker_skip_reason")
        or broker_enrichment.get("broker_skip_reason")
        or ""
    ).strip().lower() or None
    first_fill_at = (
        row.get("first_fill_at")
        or queue_row.get("first_fill_at")
        or _order_event_time(order_events, event_type="execution.fill.received")
    )
    final_fill_at = row.get("final_fill_at") or queue_row.get("final_fill_at")

    broker_submission_status = "not_attempted"
    if broker_submission_attempted_at and not broker_order_submitted:
        broker_submission_status = "broker_submission_pending"
    if broker_order_submitted:
        broker_submission_status = "broker_submitted"
    if execution_engine_status == "submitted_to_execution_engine" and not broker_submission_attempted_at:
        broker_submission_status = "broker_submission_pending"
    if queue_status in {"deferred", "waiting_for_prerequisite"} and not broker_submission_attempted_at:
        broker_submission_status = "not_attempted"

    broker_lifecycle_status = "not_started"
    if broker_order_submitted:
        if trade_fill_status == "order_filled":
            broker_lifecycle_status = "filled"
        elif trade_fill_status == "order_partially_filled":
            broker_lifecycle_status = "partially_filled"
        elif broker_order_status in {"rejected", "failed", "error"} or broker_rejection:
            broker_lifecycle_status = "rejected"
        elif broker_order_status in {"canceled", "cancelled"}:
            broker_lifecycle_status = "cancelled"
        elif broker_order_status in {"accepted", "acknowledged", "new"}:
            broker_lifecycle_status = "broker_accepted"
        else:
            broker_lifecycle_status = "broker_submission_pending"
    elif broker_skip_reason:
        broker_lifecycle_status = "not_started"
    elif str(queue_row.get("broker_lifecycle_status") or "").strip():
        broker_lifecycle_status = str(queue_row.get("broker_lifecycle_status") or "").strip().lower()

    execution_final_status = str(
        row.get("execution_final_status")
        or queue_row.get("execution_final_status")
        or "queued"
    ).strip().lower()
    if broker_lifecycle_status in {"filled", "partially_filled", "rejected", "cancelled", "broker_accepted", "broker_submission_pending"}:
        execution_final_status = broker_lifecycle_status
    elif str(queue_row.get("execution_final_status") or "").strip():
        execution_final_status = str(queue_row.get("execution_final_status") or "").strip().lower()
    elif queue_status == "submitted":
        execution_final_status = "submitted_to_execution_engine"
    elif queue_status == "waiting_for_prerequisite":
        execution_final_status = "waiting_for_dependency"
    elif queue_status in {"deferred", "skipped"}:
        execution_final_status = queue_status
    elif queue_status == "ready":
        execution_final_status = "ready"

    retry_attempt_count = max(
        _safe_int(row.get("retry_attempt_count"), 0),
        max(len([evt for evt in order_events or [] if str(evt.get("event_type") or "").strip().lower() == "execution.order.submitted"]) - 1, 0),
    )
    retry_max_attempts = max(
        _safe_int(row.get("retry_max_attempts"), _safe_int(retry_config.get("retry_max_attempts"), 1)),
        1,
    )
    retry_eligible = bool(row.get("retry_eligible", False))
    retry_reason = str(row.get("retry_reason") or "").strip().lower() or None
    retry_exhausted = bool(row.get("retry_exhausted", False))
    permanent_failure = bool(row.get("permanent_failure", False))
    backoff_seconds = _safe_float(row.get("backoff_seconds"), 0.0)
    retry_next_attempt_at = row.get("retry_next_attempt_at")
    backoff_active = bool(row.get("backoff_active", False))
    backoff_strategy = (
        str(row.get("backoff_strategy") or "").strip().lower()
        or ("exponential_jitter" if _safe_bool(retry_config.get("retry_jitter_enabled"), True) else "exponential")
    )

    if broker_lifecycle_status == "rejected":
        transient = _is_transient_broker_failure(broker_rejection)
        allow_retry = (
            _safe_bool(retry_config.get("retry_enabled"), True)
            and _safe_bool(retry_config.get("retry_allowed_for_broker_submit"), True)
            and transient
        )
        if allow_retry and retry_attempt_count < retry_max_attempts:
            retry_eligible = True
            retry_reason = retry_reason or "transient_broker_error"
            retry_attempt_count = max(retry_attempt_count, 1)
            backoff_seconds = _compute_backoff_seconds(
                retry_config=retry_config,
                attempt_count=max(retry_attempt_count, 1),
            )
            retry_next_attempt_at = _iso_with_offset(cycle_completed_at, backoff_seconds)
            backoff_active = True
            execution_final_status = "retry_scheduled"
        elif allow_retry and retry_attempt_count >= retry_max_attempts:
            retry_eligible = False
            retry_exhausted = True
            backoff_active = False
            execution_final_status = "exhausted_retries"
            retry_reason = retry_reason or "retry_budget_exhausted"
        elif not transient:
            permanent_failure = True
            retry_eligible = False
            backoff_active = False
            retry_next_attempt_at = None

    if execution_final_status in {"deferred", "waiting_for_dependency"} and queue_gate_reason:
        allow_wait_retry = (
            _safe_bool(retry_config.get("retry_enabled"), True)
            and _safe_bool(retry_config.get("retry_allowed_for_dependency_wait"), True)
        )
        if allow_wait_retry and queue_gate_reason in {
            "waiting_for_prior_reduction",
            "throttled_due_to_cycle_limit",
            "throttled_due_to_symbol_cooldown",
            "waiting_for_cash_refresh",
        }:
            retry_eligible = True
            retry_reason = queue_gate_reason
            backoff_seconds = _compute_backoff_seconds(retry_config=retry_config, attempt_count=max(retry_attempt_count + 1, 1))
            retry_next_attempt_at = _iso_with_offset(cycle_completed_at, backoff_seconds)
            backoff_active = True
            execution_final_status = "retry_scheduled"

    execution_completed_at = row.get("execution_completed_at") or queue_row.get("execution_completed_at")
    if not execution_completed_at and execution_final_status in {
        "filled",
        "partially_filled",
        "rejected",
        "cancelled",
        "expired",
        "skipped",
        "deferred",
        "retry_scheduled",
        "exhausted_retries",
    }:
        execution_completed_at = cycle_completed_at

    if trade_fill_status in {"order_filled", "order_partially_filled"} and not first_fill_at:
        first_fill_at = broker_last_update_at or execution_completed_at
    if trade_fill_status == "order_filled" and not final_fill_at:
        final_fill_at = broker_last_update_at or execution_completed_at

    reconciliation_started_at = row.get("reconciliation_started_at") or queue_row.get("reconciliation_started_at")
    reconciliation_last_polled_at = row.get("reconciliation_last_polled_at") or queue_row.get("reconciliation_last_polled_at")
    reconciliation_completed_at = row.get("reconciliation_completed_at") or queue_row.get("reconciliation_completed_at")
    reconciliation_poll_count = _safe_int(
        row.get("reconciliation_poll_count"),
        _safe_int(queue_row.get("reconciliation_poll_count"), 0),
    )
    reconciliation_terminal = bool(
        row.get("reconciliation_terminal")
        if row.get("reconciliation_terminal") is not None
        else queue_row.get("reconciliation_terminal", False)
    )
    reconciliation_window_expired = bool(
        row.get("reconciliation_window_expired")
        if row.get("reconciliation_window_expired") is not None
        else queue_row.get("reconciliation_window_expired", False)
    )
    reconciliation_stop_reason = (
        row.get("reconciliation_stop_reason")
        or queue_row.get("reconciliation_stop_reason")
    )

    if reconciliation_started_at and not reconciliation_completed_at and not reconciliation_terminal:
        if execution_final_status in {"filled", "partially_filled", "rejected", "cancelled", "expired", "skipped", "exhausted_retries"}:
            reconciliation_terminal = True
            reconciliation_completed_at = execution_completed_at or cycle_completed_at
            reconciliation_stop_reason = reconciliation_stop_reason or "terminal_state_reached"
    if reconciliation_window_expired and not reconciliation_stop_reason:
        reconciliation_stop_reason = "reconciliation_window_expired"

    return {
        "execution_engine_status": execution_engine_status,
        "broker_submission_status": broker_submission_status,
        "broker_lifecycle_status": broker_lifecycle_status,
        "execution_final_status": execution_final_status,
        "submitted_to_execution_engine_at": submitted_to_execution_engine_at,
        "broker_submission_attempted_at": broker_submission_attempted_at,
        "broker_acknowledged_at": broker_acknowledged_at,
        "broker_last_update_at": broker_last_update_at,
        "execution_completed_at": execution_completed_at,
        "first_fill_at": first_fill_at,
        "final_fill_at": final_fill_at,
        "retry_eligible": bool(retry_eligible),
        "retry_reason": retry_reason,
        "retry_attempt_count": int(retry_attempt_count),
        "retry_max_attempts": int(retry_max_attempts),
        "retry_next_attempt_at": retry_next_attempt_at,
        "backoff_seconds": round(max(backoff_seconds, 0.0), 3),
        "backoff_strategy": backoff_strategy,
        "retry_exhausted": bool(retry_exhausted),
        "backoff_active": bool(backoff_active),
        "permanent_failure": bool(permanent_failure),
        "reconciliation_started_at": reconciliation_started_at,
        "reconciliation_last_polled_at": reconciliation_last_polled_at,
        "reconciliation_completed_at": reconciliation_completed_at,
        "reconciliation_poll_count": int(reconciliation_poll_count),
        "reconciliation_terminal": bool(reconciliation_terminal),
        "reconciliation_window_expired": bool(reconciliation_window_expired),
        "reconciliation_stop_reason": reconciliation_stop_reason,
    }


def _actual_release_value_from_row(row: dict) -> float:
    action = str(
        row.get("requested_execution_action")
        or row.get("actual_execution_action")
        or row.get("derived_intent")
        or ""
    ).strip().upper()
    if action not in _CAPITAL_RELEASE_ACTIONS:
        return 0.0
    filled_qty = _safe_float(row.get("filled_qty"), 0.0)
    avg_fill = _safe_float(row.get("average_fill_price"), 0.0)
    if filled_qty > 0 and avg_fill > 0:
        return round(filled_qty * avg_fill, 4)
    executed_qty = _safe_float(row.get("executed_qty"), 0.0)
    executed_price = _safe_float(row.get("executed_price"), 0.0)
    if executed_qty > 0 and executed_price > 0:
        return round(executed_qty * executed_price, 4)
    return 0.0


def _apply_dependency_resizing(rows: list[dict], *, cycle_completed_at: str) -> None:
    row_by_queue_id = {
        str(row.get("queue_item_id") or "").strip(): row
        for row in rows
        if isinstance(row, dict) and str(row.get("queue_item_id") or "").strip()
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        row["dependency_actual_release_value"] = round(_safe_float(row.get("dependency_actual_release_value"), _actual_release_value_from_row(row)), 4)

    for row in rows:
        if not isinstance(row, dict):
            continue
        dependency_ids = [
            str(dep).strip()
            for dep in (row.get("depends_on_queue_item_ids") or [])
            if str(dep).strip()
        ]
        if not dependency_ids:
            continue

        expected_release = 0.0
        actual_release = 0.0
        unresolved = False
        for dep_id in dependency_ids:
            dep_row = row_by_queue_id.get(dep_id)
            if not isinstance(dep_row, dict):
                unresolved = True
                continue
            expected_release += max(_safe_float(dep_row.get("capital_approved_value"), 0.0), 0.0)
            actual_release += max(_safe_float(dep_row.get("dependency_actual_release_value"), _actual_release_value_from_row(dep_row)), 0.0)
            if str(dep_row.get("execution_final_status") or "").strip().lower() in {
                "waiting_for_dependency",
                "submitted_to_execution_engine",
                "broker_submission_pending",
                "broker_accepted",
                "retry_scheduled",
                "backoff_active",
            }:
                unresolved = True

        expected_release = round(max(expected_release, 0.0), 4)
        actual_release = round(max(actual_release, 0.0), 4)
        delta = round(actual_release - expected_release, 4)
        progress_pct = 0.0
        if expected_release > 0:
            progress_pct = min(max((actual_release / expected_release) * 100.0, 0.0), 100.0)

        row["dependency_expected_release_value"] = expected_release
        row["dependency_actual_release_value"] = actual_release
        row["dependency_release_delta"] = delta
        row["dependency_release_progress_pct"] = round(progress_pct, 3)

        if unresolved:
            dependency_outcome = "waiting_for_capital_release"
        elif expected_release <= 0:
            dependency_outcome = "capital_release_not_required"
        elif actual_release >= expected_release * 0.99:
            dependency_outcome = "capital_release_completed"
        elif actual_release > 0:
            dependency_outcome = "capital_release_partial"
        else:
            dependency_outcome = "capital_release_failed"

        row["dependency_outcome"] = dependency_outcome
        row["dependency_final_outcome"] = dependency_outcome
        row["dependency_satisfied"] = dependency_outcome in {"capital_release_completed", "capital_release_partial"}
        row["dependency_resolution_reason"] = dependency_outcome
        if dependency_outcome in {"capital_release_completed", "capital_release_partial", "capital_release_failed"}:
            row["dependency_resolved_at"] = row.get("dependency_resolved_at") or cycle_completed_at

        action = str(row.get("requested_execution_action") or "").strip().upper()
        if action not in _CAPITAL_DEPLOY_ACTIONS:
            continue

        original_qty = _safe_float(
            row.get("original_approved_order_qty"),
            _safe_float(row.get("approved_order_qty"), 0.0),
        )
        original_capital = _safe_float(
            row.get("capital_approved_value"),
            _safe_float(row.get("recomputed_capital_approved_value"), 0.0),
        )
        row["original_approved_order_qty"] = round(max(original_qty, 0.0), 4)

        ratio = 1.0
        if expected_release > 0:
            ratio = max(min(actual_release / expected_release, 1.0), 0.0)
        recomputed_qty = round(max(original_qty * ratio, 0.0), 4)
        recomputed_capital = round(max(original_capital * ratio, 0.0), 4)

        row["recomputed_approved_order_qty"] = recomputed_qty
        row["recomputed_capital_approved_value"] = recomputed_capital

        should_resize = ratio < 0.999 and not bool(row.get("broker_order_submitted"))
        if should_resize:
            row["resized_after_execution_result"] = True
            row["resized_after_capital_release"] = True
            row["funding_recomputed"] = True
            row["recompute_reason"] = (
                "dependency_release_failed"
                if dependency_outcome == "capital_release_failed"
                else "dependency_release_partial"
            )
            if recomputed_qty <= 0:
                row["execution_final_status"] = "cancelled"
                row["execution_skip_reason"] = row.get("execution_skip_reason") or "dependency_release_failed"
        else:
            row["resized_after_execution_result"] = bool(row.get("resized_after_execution_result", False))
            row["resized_after_capital_release"] = bool(row.get("resized_after_capital_release", False))
            row["funding_recomputed"] = bool(row.get("funding_recomputed", False))


def _enrich_execution_queue_and_timeline(
    *,
    rows: list[dict],
    base_queue: list[dict],
    base_timeline: list[dict],
) -> tuple[list[dict], list[dict], dict]:
    queue_items: list[dict] = [dict(item) for item in (base_queue or []) if isinstance(item, dict)]
    row_by_symbol = {
        _normalize_symbol(row.get("symbol")): row
        for row in rows
        if isinstance(row, dict) and _normalize_symbol(row.get("symbol"))
    }

    for item in queue_items:
        symbol = _normalize_symbol(item.get("symbol"))
        row = row_by_symbol.get(symbol, {})
        if not isinstance(row, dict):
            continue
        item.update(
            {
                "execution_engine_status": row.get("execution_engine_status"),
                "broker_submission_status": row.get("broker_submission_status"),
                "broker_lifecycle_status": row.get("broker_lifecycle_status"),
                "execution_final_status": row.get("execution_final_status"),
                "submitted_to_execution_engine_at": row.get("submitted_to_execution_engine_at"),
                "broker_submission_attempted_at": row.get("broker_submission_attempted_at"),
                "broker_acknowledged_at": row.get("broker_acknowledged_at"),
                "broker_last_update_at": row.get("broker_last_update_at"),
                "execution_completed_at": row.get("execution_completed_at"),
                "first_fill_at": row.get("first_fill_at"),
                "final_fill_at": row.get("final_fill_at"),
                "retry_eligible": row.get("retry_eligible"),
                "retry_reason": row.get("retry_reason"),
                "retry_attempt_count": row.get("retry_attempt_count"),
                "retry_max_attempts": row.get("retry_max_attempts"),
                "retry_next_attempt_at": row.get("retry_next_attempt_at"),
                "backoff_seconds": row.get("backoff_seconds"),
                "backoff_strategy": row.get("backoff_strategy"),
                "retry_exhausted": row.get("retry_exhausted"),
                "backoff_active": row.get("backoff_active"),
                "permanent_failure": row.get("permanent_failure"),
                "dependency_expected_release_value": row.get("dependency_expected_release_value"),
                "dependency_actual_release_value": row.get("dependency_actual_release_value"),
                "dependency_release_delta": row.get("dependency_release_delta"),
                "dependency_wait_started_at": row.get("dependency_wait_started_at"),
                "dependency_resolved_at": row.get("dependency_resolved_at"),
                "dependency_resolution_reason": row.get("dependency_resolution_reason"),
                "dependency_final_outcome": row.get("dependency_final_outcome"),
                "resized_after_execution_result": row.get("resized_after_execution_result"),
                "original_approved_order_qty": row.get("original_approved_order_qty"),
                "recomputed_approved_order_qty": row.get("recomputed_approved_order_qty"),
                "recomputed_capital_approved_value": row.get("recomputed_capital_approved_value"),
                "recompute_reason": row.get("recompute_reason"),
                "reconciliation_started_at": row.get("reconciliation_started_at"),
                "reconciliation_last_polled_at": row.get("reconciliation_last_polled_at"),
                "reconciliation_completed_at": row.get("reconciliation_completed_at"),
                "reconciliation_poll_count": row.get("reconciliation_poll_count"),
                "reconciliation_terminal": row.get("reconciliation_terminal"),
                "reconciliation_window_expired": row.get("reconciliation_window_expired"),
                "reconciliation_stop_reason": row.get("reconciliation_stop_reason"),
                "dependency_release_progress_pct": row.get("dependency_release_progress_pct"),
            }
        )

    timeline: list[dict] = [dict(event) for event in (base_timeline or []) if isinstance(event, dict)]
    for item in queue_items:
        queue_item_id = item.get("queue_item_id")
        symbol = item.get("symbol")
        action = item.get("requested_execution_action")
        queue_rank = item.get("queue_rank")

        if item.get("submitted_to_execution_engine_at"):
            timeline.append(
                {
                    "event": "submitted_to_execution_engine",
                    "at": item.get("submitted_to_execution_engine_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                }
            )
        if item.get("broker_submission_attempted_at"):
            timeline.append(
                {
                    "event": "broker_submit_attempted",
                    "at": item.get("broker_submission_attempted_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                }
            )
            timeline.append(
                {
                    "event": "broker_submit_succeeded"
                    if str(item.get("broker_submission_status") or "") == "broker_submitted"
                    else "broker_submit_failed",
                    "at": item.get("broker_submission_attempted_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                    "reason": item.get("retry_reason") or item.get("queue_gate_reason"),
                }
            )
        if item.get("retry_eligible") and item.get("retry_next_attempt_at"):
            timeline.append(
                {
                    "event": "retry_scheduled",
                    "at": item.get("retry_next_attempt_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                    "reason": item.get("retry_reason"),
                    "backoff_seconds": item.get("backoff_seconds"),
                }
            )
        if item.get("backoff_active"):
            timeline.append(
                {
                    "event": "backoff_started",
                    "at": item.get("retry_next_attempt_at") or item.get("execution_completed_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                    "backoff_seconds": item.get("backoff_seconds"),
                }
            )
        if item.get("reconciliation_started_at"):
            timeline.append(
                {
                    "event": "reconciliation_started",
                    "at": item.get("reconciliation_started_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                }
            )
        if item.get("reconciliation_last_polled_at"):
            timeline.append(
                {
                    "event": "broker_status_polled",
                    "at": item.get("reconciliation_last_polled_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                    "poll_count": _safe_int(item.get("reconciliation_poll_count"), 0),
                }
            )
        if item.get("reconciliation_completed_at"):
            timeline.append(
                {
                    "event": "reconciliation_completed",
                    "at": item.get("reconciliation_completed_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                    "reason": item.get("reconciliation_stop_reason"),
                    "window_expired": bool(item.get("reconciliation_window_expired")),
                }
            )
        if str(item.get("dependency_final_outcome") or "").strip().lower() not in {"", "not_required", "pending"}:
            timeline.append(
                {
                    "event": "dependency_resolved",
                    "at": item.get("dependency_resolved_at") or item.get("execution_completed_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                    "dependency_outcome": item.get("dependency_final_outcome"),
                    "expected_release_value": item.get("dependency_expected_release_value"),
                    "actual_release_value": item.get("dependency_actual_release_value"),
                }
            )
        if item.get("resized_after_execution_result"):
            timeline.append(
                {
                    "event": "dependent_action_resized",
                    "at": item.get("dependency_resolved_at") or item.get("execution_completed_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                    "recompute_reason": item.get("recompute_reason"),
                    "original_approved_order_qty": item.get("original_approved_order_qty"),
                    "recomputed_approved_order_qty": item.get("recomputed_approved_order_qty"),
                }
            )
        lifecycle = str(item.get("broker_lifecycle_status") or "").strip().lower()
        lifecycle_event_map = {
            "partially_filled": "order_partially_filled",
            "filled": "order_filled",
            "rejected": "order_rejected",
            "cancelled": "order_cancelled",
            "broker_accepted": "broker_accepted",
        }
        if lifecycle in lifecycle_event_map:
            timeline.append(
                {
                    "event": lifecycle_event_map[lifecycle],
                    "at": item.get("broker_last_update_at") or item.get("execution_completed_at"),
                    "queue_item_id": queue_item_id,
                    "symbol": symbol,
                    "action": action,
                    "queue_rank": queue_rank,
                    "broker_lifecycle_status": lifecycle,
                }
            )

    timeline = [
        event
        for event in timeline
        if isinstance(event, dict) and event.get("event")
    ]
    deduped_timeline: list[dict] = []
    seen_timeline_keys: set[tuple[Any, ...]] = set()
    for event in timeline:
        dedupe_key = (
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
        if dedupe_key in seen_timeline_keys:
            continue
        seen_timeline_keys.add(dedupe_key)
        deduped_timeline.append(event)
    timeline = deduped_timeline
    timeline.sort(
        key=lambda item: (
            _parse_iso(item.get("at")) is None,
            _parse_iso(item.get("at")) or _parse_iso("1970-01-01T00:00:00"),
            str(item.get("event") or ""),
            str(item.get("queue_item_id") or ""),
        )
    )

    queue_status_counts = Counter(str(item.get("queue_status") or "unknown") for item in queue_items)
    engine_status_counts = Counter(str(item.get("execution_engine_status") or "unknown") for item in queue_items)
    broker_submission_counts = Counter(str(item.get("broker_submission_status") or "unknown") for item in queue_items)
    broker_lifecycle_counts = Counter(str(item.get("broker_lifecycle_status") or "unknown") for item in queue_items)
    final_status_counts = Counter(str(item.get("execution_final_status") or "unknown") for item in queue_items)

    summary = {
        "queue_total": len(queue_items),
        "submitted_count": int(queue_status_counts.get("submitted", 0)),
        "deferred_count": int(queue_status_counts.get("deferred", 0)),
        "waiting_count": int(queue_status_counts.get("waiting_for_prerequisite", 0)),
        "skipped_count": int(queue_status_counts.get("skipped", 0)),
        "ready_count": int(queue_status_counts.get("ready", 0)),
        "execution_engine_status_counts": dict(engine_status_counts.most_common(16)),
        "broker_submission_status_counts": dict(broker_submission_counts.most_common(16)),
        "broker_lifecycle_status_counts": dict(broker_lifecycle_counts.most_common(16)),
        "execution_final_status_counts": dict(final_status_counts.most_common(16)),
        "retry_scheduled_count": int(final_status_counts.get("retry_scheduled", 0)),
        "backoff_active_count": int(
            sum(1 for item in queue_items if bool(item.get("backoff_active")))
        ),
        "resized_after_execution_result_count": int(
            sum(1 for item in queue_items if bool(item.get("resized_after_execution_result")))
        ),
        "reconciliation_started_count": int(
            sum(1 for item in queue_items if bool(item.get("reconciliation_started_at")))
        ),
        "reconciliation_completed_count": int(
            sum(1 for item in queue_items if bool(item.get("reconciliation_completed_at")))
        ),
        "reconciliation_active_count": int(
            sum(
                1
                for item in queue_items
                if bool(item.get("reconciliation_started_at")) and not bool(item.get("reconciliation_completed_at"))
            )
        ),
        "reconciliation_terminal_count": int(
            sum(1 for item in queue_items if bool(item.get("reconciliation_terminal")))
        ),
        "reconciliation_window_expired_count": int(
            sum(1 for item in queue_items if bool(item.get("reconciliation_window_expired")))
        ),
        "reconciliation_poll_count_total": int(
            sum(_safe_int(item.get("reconciliation_poll_count"), 0) for item in queue_items)
        ),
        "submitted_order_sequence": [
            {
                "queue_item_id": item.get("queue_item_id"),
                "symbol": item.get("symbol"),
                "action": item.get("requested_execution_action"),
                "queue_rank": item.get("queue_rank"),
                "submission_order": item.get("submission_order"),
                "execution_priority_band": item.get("execution_priority_band"),
            }
            for item in sorted(
                [entry for entry in queue_items if str(entry.get("queue_status") or "") == "submitted"],
                key=lambda entry: _safe_int(entry.get("submission_order"), 9999),
            )
        ],
        "deferred_order_sequence": [
            {
                "queue_item_id": item.get("queue_item_id"),
                "symbol": item.get("symbol"),
                "action": item.get("requested_execution_action"),
                "queue_rank": item.get("queue_rank"),
                "reason": item.get("queue_gate_reason") or item.get("defer_reason"),
            }
            for item in queue_items
            if str(item.get("queue_status") or "") == "deferred"
        ],
        "skipped_order_sequence": [
            {
                "queue_item_id": item.get("queue_item_id"),
                "symbol": item.get("symbol"),
                "action": item.get("requested_execution_action"),
                "queue_rank": item.get("queue_rank"),
                "reason": item.get("queue_gate_reason") or item.get("defer_reason"),
            }
            for item in queue_items
            if str(item.get("queue_status") or "") == "skipped"
        ],
    }
    return queue_items, timeline, summary

def _normalize_signal(value: Any) -> str:
    signal = str(value or "HOLD").strip().upper()
    return signal if signal in {"BUY", "SELL", "HOLD"} else "HOLD"


def _normalize_side(value: Any) -> str | None:
    side = str(value or "").strip().upper()
    if side in {"LONG", "SHORT"}:
        return side
    return None


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _derive_intent(
    *,
    signal: str,
    current_side: str | None,
    trade_direction: str,
    margin_enabled: bool,
) -> tuple[str, str, str, str]:
    normalized_signal = _normalize_signal(signal)
    current = _normalize_side(current_side)
    direction = str(trade_direction or "both").strip().lower()
    allow_long = direction in {"both", "long_only"}
    allow_short = direction in {"both", "short_only"} and bool(margin_enabled)

    if normalized_signal == "BUY":
        if current == "SHORT" and allow_long:
            return ("CLOSE_SHORT+OPEN_LONG", "order_submitted", "BUY closes short then opens long", "passed")
        if current == "SHORT":
            return ("CLOSE_SHORT", "order_submitted", "BUY closes short", "passed")
        if current == "LONG":
            if allow_long:
                return ("ADD_LONG", "add_long_candidate", "BUY on existing LONG evaluated for add sizing", "passed")
            return ("NONE", "existing_long_position_no_add", "BUY blocked by trade direction for existing LONG", "blocked")
        if allow_long:
            return ("OPEN_LONG", "order_submitted", "BUY opens long", "passed")
        return ("NONE", "no_action_from_signal", "BUY blocked by trade direction", "blocked")

    if normalized_signal == "SELL":
        if current == "LONG" and allow_short:
            return ("CLOSE_LONG+OPEN_SHORT", "order_submitted", "SELL closes long then opens short", "passed")
        if current == "LONG":
            return ("CLOSE_LONG", "order_submitted", "SELL closes long", "passed")
        if current == "SHORT":
            return ("NONE", "existing_short_position", "SELL suppressed because SHORT already open", "blocked")
        if allow_short:
            return ("OPEN_SHORT", "order_submitted", "SELL opens short", "passed")
        return ("NONE", "no_action_from_signal", "SELL blocked by trade direction", "blocked")

    return ("NONE", "no_action_from_signal", "HOLD generated no execution intent", "passed")


def _map_block_reason_to_code(block_reason: str | None, blocking_reasons: list[str] | None = None) -> tuple[str, str]:
    reason_text = " ".join(str(x) for x in (blocking_reasons or []) if x)
    if block_reason:
        reason_text = f"{reason_text} {block_reason}".strip()
    normalized = reason_text.lower()

    if "cash" in normalized or "insufficient" in normalized:
        return ("insufficient_cash", reason_text)
    if "market" in normalized and "closed" in normalized:
        return ("market_closed", reason_text)
    if "short" in normalized and "disabled" in normalized:
        return ("insufficient_margin", reason_text)
    if "risk" in normalized or "budget" in normalized or "trade" in normalized:
        return ("risk_gate_blocked", reason_text)
    if reason_text:
        return ("risk_gate_blocked", reason_text)
    return ("risk_gate_blocked", "blocked by execution guardrails")


def _collect_events_by_symbol(correlation_id: str | None) -> dict[str, list[dict]]:
    if not correlation_id:
        return {}

    with session_scope() as session:
        rows = (
            session.query(ExecutionAuditEvent)
            .filter(ExecutionAuditEvent.correlation_id == correlation_id)
            .order_by(ExecutionAuditEvent.created_at.asc())
            .all()
        )

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        symbol = _normalize_symbol(row.symbol)
        if not symbol:
            continue
        grouped.setdefault(symbol, []).append(
            {
                "event_type": str(row.event_type or "").strip().lower(),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "payload": loads_json(row.payload_json),
            }
        )
    return grouped


def _collect_order_events_by_symbol(correlation_id: str | None) -> dict[str, list[dict]]:
    if not correlation_id:
        return {}

    with session_scope() as session:
        rows = (
            session.query(OrderEvent)
            .filter(OrderEvent.correlation_id == correlation_id)
            .order_by(OrderEvent.created_at.asc())
            .all()
        )

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        payload = loads_json(row.payload_json)
        symbol = _normalize_symbol(row.symbol)
        if not symbol and isinstance(payload, dict):
            symbol = _normalize_symbol(payload.get("symbol"))
        if not symbol:
            continue

        grouped.setdefault(symbol, []).append(
            {
                "event_type": str(row.event_type or "").strip().lower(),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "payload": payload if isinstance(payload, dict) else {},
            }
        )
    return grouped


def _symbol_analysis_map(signal_items: list[dict], preview_items: list[dict] | None = None) -> dict[str, dict]:
    combined: dict[str, dict] = {}
    for item in (preview_items or []):
        symbol = _normalize_symbol(item.get("symbol"))
        if not symbol:
            continue
        combined[symbol] = {
            "analysis_signal": _normalize_signal(item.get("signal")),
            "analysis_score": _safe_float(item.get("score") or item.get("analysis_score"), 0.0),
            "confidence": _safe_float(item.get("confidence"), 0.0),
            "price": _safe_float(item.get("price"), 0.0),
            "analysis_payload": item.get("result") if isinstance(item.get("result"), dict) else {},
        }
    for item in (signal_items or []):
        symbol = _normalize_symbol(item.get("symbol"))
        if not symbol:
            continue
        prior = combined.get(symbol, {})
        combined[symbol] = {
            "analysis_signal": _normalize_signal(item.get("signal") or prior.get("analysis_signal")),
            "analysis_score": _safe_float(item.get("analysis_score") or prior.get("analysis_score"), 0.0),
            "confidence": _safe_float(item.get("confidence") if item.get("confidence") is not None else prior.get("confidence"), 0.0),
            "price": _safe_float(item.get("price") if item.get("price") is not None else prior.get("price"), 0.0),
            "analysis_payload": item.get("analysis") if isinstance(item.get("analysis"), dict) else prior.get("analysis_payload", {}),
        }
    return combined




def _dedupe_component_names(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = str(value or "").strip().lower()
        if not item or item in normalized:
            continue
        normalized.append(item)
    return normalized


def _derive_engine_contribution_fields(row: dict, *, strategy_mode: str | None = None) -> dict:
    analysis_payload = row.get("analysis_payload") if isinstance(row.get("analysis_payload"), dict) else {}
    ml_output = analysis_payload.get("ml_output") if isinstance(analysis_payload.get("ml_output"), dict) else {}
    dl_output = analysis_payload.get("dl_output") if isinstance(analysis_payload.get("dl_output"), dict) else {}
    ensemble_output = analysis_payload.get("ensemble_output") if isinstance(analysis_payload.get("ensemble_output"), dict) else {}
    components = ensemble_output.get("components") if isinstance(ensemble_output.get("components"), dict) else {}

    normalized_mode = str(strategy_mode or row.get("strategy_mode") or "").strip().lower()
    ml_enabled = _safe_bool(analysis_payload.get("ml_enabled"), True) or bool(ml_output)
    dl_enabled = normalized_mode in {"dl", "ensemble"} or bool(dl_output)
    ml_ready = bool(ml_output) and not str(ml_output.get("error") or "").strip()
    dl_ready = bool(dl_output) and not str(dl_output.get("error") or "").strip()

    classic_signal = _normalize_signal(analysis_payload.get("signal") or row.get("analysis_signal"))
    ranking_signal = _normalize_signal(
        analysis_payload.get("enhanced_signal")
        or analysis_payload.get("enhanced_recommendation")
        or row.get("analysis_signal")
    )
    ml_signal = _normalize_signal(ml_output.get("signal"))
    dl_signal = _normalize_signal(dl_output.get("signal"))

    ml_component = _safe_float(components.get("ml_component"), 0.0)
    dl_component = _safe_float(components.get("dl_component"), 0.0)
    kronos_contribution = _safe_float(row.get("kronos_contribution_to_score"), 0.0)

    available: list[str] = []
    used: list[str] = []
    skipped: list[str] = []

    if analysis_payload:
        available.extend(["classic", "ranking"])
        used.extend(["classic", "ranking"])

    if ml_enabled or ml_output:
        available.append("ml")
        if ml_ready and abs(ml_component) > 1e-9:
            used.append("ml")
        else:
            skipped.append("ml")

    if dl_enabled or dl_output:
        available.append("dl")
        if dl_ready and abs(dl_component) > 1e-9:
            used.append("dl")
        else:
            skipped.append("dl")

    kronos_available = bool(row.get("kronos_ready")) or bool(_safe_float(row.get("kronos_score"), 0.0)) or bool(row.get("kronos_wait_reason"))
    if kronos_available:
        available.append("kronos")
        if abs(kronos_contribution) > 1e-9:
            used.append("kronos")
        else:
            skipped.append("kronos")

    available = _dedupe_component_names(available)
    used = _dedupe_component_names(used)
    skipped = _dedupe_component_names([item for item in skipped if item not in used])

    ml_reason_not_used = None
    if "ml" in available and "ml" not in used:
        ml_reason_not_used = str(ml_output.get("error") or "").strip() or ("ml_output_missing" if not ml_output else "ensemble_component_zero")

    dl_reason_not_used = None
    if "dl" in available and "dl" not in used:
        dl_reason_not_used = (
            "runtime_disabled" if not dl_enabled else str(dl_output.get("error") or "").strip() or ("dl_output_missing" if not dl_output else "ensemble_component_zero")
        )

    kronos_reason_not_used = None
    if "kronos" in available and "kronos" not in used:
        kronos_reason_not_used = (
            str(row.get("kronos_wait_reason") or row.get("kronos_no_trade_reason") or "").strip().lower()
            or ("kronos_not_ready" if not row.get("kronos_ready") else "score_weight_zero")
        )

    dl_model_resolution = str(dl_output.get("model_resolution") or "").strip().lower() or None
    kronos_fallback_used = bool(row.get("kronos_fallback_used", False))

    return {
        "classic_signal": classic_signal or None,
        "ranking_signal": ranking_signal or None,
        "ml_enabled": bool(ml_enabled),
        "ml_ready": bool(ml_ready),
        "ml_signal": ml_signal or None,
        "ml_confidence": _safe_float(ml_output.get("confidence"), 0.0),
        "ml_model_resolution": str(ml_output.get("model_resolution") or "").strip().lower() or None,
        "ml_contributed": bool("ml" in used),
        "ml_contribution_to_score": ml_component,
        "ml_reason_not_used": ml_reason_not_used,
        "dl_enabled": bool(dl_enabled),
        "dl_ready": bool(dl_ready),
        "dl_signal": dl_signal or None,
        "dl_confidence": _safe_float(dl_output.get("confidence"), 0.0),
        "dl_model_resolution": dl_model_resolution,
        "dl_contributed": bool("dl" in used),
        "dl_contribution_to_score": dl_component,
        "dl_reason_not_used": dl_reason_not_used,
        "dl_fallback_used": bool(dl_ready and dl_model_resolution not in {None, "active", "explicit"}),
        "kronos_contributed": bool("kronos" in used),
        "kronos_reason_not_used": kronos_reason_not_used,
        "kronos_fallback_used": kronos_fallback_used,
        "ensemble_components_available": available,
        "ensemble_components_used": used,
        "ensemble_components_skipped": skipped,
    }


def _derive_autonomous_action(row: dict) -> tuple[str, str]:
    requested = str(row.get("requested_execution_action") or row.get("action_decision") or "").strip().upper()
    session_plan = str(row.get("session_order_plan") or "").strip().lower()
    session_preferred = str(row.get("session_preferred_action") or "").strip().upper()
    if str(row.get("replacement_candidate") or "").strip() or str(row.get("displaced_symbol") or "").strip():
        return ("ROTATE_OUT", str(row.get("better_use_of_capital_reason") or row.get("decision_outcome_detail") or "capital_rotation"))
    if session_plan == "queue_for_open" or session_preferred.startswith("QUEUE_FOR_OPEN"):
        return ("QUEUE_FOR_OPEN", str(row.get("queued_for_open_reason") or row.get("session_reason") or row.get("decision_outcome_detail") or "queue_for_open"))
    if bool(row.get("wait_for_open_confirmation")) or session_preferred == "WAIT_FOR_OPEN_CONFIRMATION":
        return ("WAIT_FOR_CONFIRMATION", str(row.get("wait_for_open_reason") or row.get("session_reason") or row.get("decision_outcome_detail") or "wait_for_confirmation"))
    if requested in {"OPEN_LONG", "ADD_LONG", "HOLD", "REDUCE_LONG", "EXIT_LONG"}:
        return (requested, str(row.get("decision_outcome_detail") or row.get("session_reason") or requested.lower()))
    if session_preferred == "NO_ACTION" or session_plan == "no_action":
        return ("NO_ACTION", str(row.get("no_trade_before_open_reason") or row.get("capital_competition_reason") or row.get("decision_outcome_detail") or "no_action"))
    return ("NO_ACTION", str(row.get("decision_outcome_detail") or "no_action"))


def _build_reward_penalty_profile(row: dict) -> dict:
    session_score = _safe_float(row.get("session_adjusted_opportunity_score"), _safe_float(row.get("opportunity_score"), 0.0))
    quality_score = _clamp(
        session_score * 0.34
        + _safe_float(row.get("stock_quality_score"), 0.0) * 0.18
        + _safe_float(row.get("engine_alignment_score"), 0.0) * 0.14
        + _safe_float(row.get("news_confidence"), 0.0) * 0.10
        + _safe_float(row.get("liquidity_score"), 0.0) * 0.10
        + (100.0 - _safe_float(row.get("volatility_risk_score"), 0.0)) * 0.14,
        0.0,
        100.0,
    )
    autonomous_action = str(row.get("autonomous_action") or "NO_ACTION")
    if autonomous_action in {"OPEN_LONG", "ADD_LONG"}:
        timing_seed = _safe_float(row.get("opening_score"), 0.0)
    elif autonomous_action in {"REDUCE_LONG", "EXIT_LONG", "ROTATE_OUT"}:
        timing_seed = _safe_float(row.get("reduce_pressure_score"), 0.0) * 0.45 + _safe_float(row.get("exit_pressure_score"), 0.0) * 0.55
    else:
        timing_seed = _safe_float(row.get("open_confirmation_score"), 0.0)
    timing_quality_score = round(_clamp(timing_seed - (8.0 if bool(row.get("news_requires_wait")) else 0.0), 0.0, 100.0), 4)
    sizing_quality_score = round(
        _clamp(
            68.0
            + (_safe_float(row.get("funding_ratio"), 0.0) * 18.0)
            - (_safe_float(row.get("small_cap_position_size_multiplier"), 1.0) < 0.6) * 6.0
            - (_safe_float(row.get("spread_risk_score"), 0.0) * 0.05),
            0.0,
            100.0,
        ),
        4,
    )
    execution_quality_score = round(
        _clamp(
            72.0
            + (8.0 if str(row.get("session_go_no_go") or "").strip().lower() == "go" else -8.0 if str(row.get("session_go_no_go") or "").strip().lower() in {"wait", "defer"} else 0.0)
            - (_safe_float(row.get("spread_risk_score"), 0.0) * 0.04)
            - (_safe_float(row.get("volatility_risk_score"), 0.0) * 0.03),
            0.0,
            100.0,
        ),
        4,
    )
    capital_use_quality_score = round(
        _clamp(
            session_score * 0.45
            + (12.0 if not str(row.get("better_use_of_capital_reason") or "").strip() else -6.0)
            + (_safe_float(row.get("funding_ratio"), 0.0) * 16.0)
            + (6.0 if str(row.get("capital_competition_reason") or "").strip() in {"won_priority_allocation", "replacement_selected"} else 0.0),
            0.0,
            100.0,
        ),
        4,
    )

    reward_components: list[dict] = []
    penalty_components: list[dict] = []
    if quality_score >= 70.0:
        reward_components.append({"component": "high_quality_setup", "score": round((quality_score - 60.0) * 0.45, 4)})
    if capital_use_quality_score >= 70.0:
        reward_components.append({"component": "capital_allocation_quality", "score": round((capital_use_quality_score - 60.0) * 0.35, 4)})
    if autonomous_action in {"REDUCE_LONG", "EXIT_LONG", "ROTATE_OUT"} and not str(row.get("better_use_of_capital_reason") or "").strip():
        reward_components.append({"component": "risk_discipline", "score": 6.0})
    if bool(row.get("news_requires_wait")):
        penalty_components.append({"component": "news_requires_wait", "score": 6.0})
    if bool(row.get("engine_conflicts_present")):
        penalty_components.append({"component": "engine_conflict", "score": 8.0})
    if _safe_float(row.get("spread_risk_score"), 0.0) >= 60.0:
        penalty_components.append({"component": "spread_risk", "score": 7.0})
    if _safe_float(row.get("volatility_risk_score"), 0.0) >= 68.0:
        penalty_components.append({"component": "volatility_risk", "score": 8.0})
    if str(row.get("capital_competition_reason") or "").strip() in {"higher_priority_symbols_funded_first", "better_existing_use_of_capital"}:
        penalty_components.append({"component": "better_alternative_existed", "score": 5.0})

    reward_score = round(_clamp(sum(item["score"] for item in reward_components), 0.0, 100.0), 4)
    penalty_score = round(_clamp(sum(item["score"] for item in penalty_components), 0.0, 100.0), 4)
    behavior_update_applied = bool(penalty_score > reward_score + 4.0)
    strategy_confidence_adjustment = round(_clamp((reward_score - penalty_score) / 20.0, -5.0, 5.0), 4)
    sleeve_bias_adjustment = (
        "raise_cash_and_defense" if penalty_score >= reward_score + 6.0
        else "lean_growth" if reward_score >= penalty_score + 6.0
        else "hold_current_sleeves"
    )
    engine_weight_adjustment = {
        "increase_news_weight": bool(_safe_float(row.get("news_strength_score"), 0.0) >= 65.0 and penalty_score <= reward_score),
        "increase_wait_bias": bool(bool(row.get("engine_conflicts_present")) or bool(row.get("news_requires_wait"))),
        "decrease_small_cap_bias": bool(bool(row.get("tactical_small_cap_candidate")) and penalty_score > reward_score),
    }
    better_symbol = str(row.get("replacement_candidate") or row.get("displaced_symbol") or "").strip() or None
    trade_review_completed = str(row.get("execution_final_status") or "").strip().lower() in {"filled", "partially_filled", "rejected", "cancelled", "expired"}
    trade_review_summary = (
        f"{autonomous_action}: quality={quality_score:.1f}, timing={timing_quality_score:.1f}, capital_use={capital_use_quality_score:.1f}."
    )
    lesson_learned = (
        "Favor confirmation and capital preservation when engine/news conflict persists."
        if behavior_update_applied
        else "Current setup quality and portfolio fit support the chosen posture."
    )
    behavior_adjustment_hint = (
        "wait_or_reduce"
        if behavior_update_applied
        else "press_advantage_selectively"
    )
    return {
        "trade_review_completed": trade_review_completed,
        "trade_quality_score": round(quality_score, 4),
        "timing_quality_score": timing_quality_score,
        "sizing_quality_score": sizing_quality_score,
        "execution_quality_score": execution_quality_score,
        "capital_use_quality_score": capital_use_quality_score,
        "better_alternative_existed": bool(better_symbol),
        "better_alternative_symbol": better_symbol,
        "trade_review_reward": reward_score,
        "trade_review_penalty": penalty_score,
        "trade_review_summary": trade_review_summary,
        "lesson_learned": lesson_learned,
        "behavior_adjustment_hint": behavior_adjustment_hint,
        "reward_score": reward_score,
        "penalty_score": penalty_score,
        "reward_components": reward_components,
        "penalty_components": penalty_components,
        "behavior_update_applied": behavior_update_applied,
        "strategy_confidence_adjustment": strategy_confidence_adjustment,
        "sleeve_bias_adjustment": sleeve_bias_adjustment,
        "engine_weight_adjustment": engine_weight_adjustment,
    }


def _build_ai_forecast(row: dict) -> dict:
    price = max(_safe_float(row.get("analysis_payload", {}).get("close"), _safe_float(row.get("analysis_payload", {}).get("price"), _safe_float(row.get("analysis_score"), 0.0))), 0.0)
    if price <= 0.0:
        price = max(_safe_float(row.get("target_position_value"), 0.0), 0.0)
    price = max(_safe_float(row.get("analysis_payload", {}).get("close"), _safe_float(row.get("current_position_avg_price"), price)), price)
    if price <= 0.0:
        price = max(_safe_float(row.get("analysis_payload", {}).get("close"), 0.0), _safe_float(row.get("analysis_payload", {}).get("support"), 0.0))
    if price <= 0.0:
        price = max(_safe_float(row.get("analysis_payload", {}).get("close"), 0.0), _safe_float(row.get("analysis_payload", {}).get("resistance"), 0.0))
    if price <= 0.0:
        price = max(_safe_float(row.get("analysis_payload", {}).get("close"), 0.0), _safe_float(row.get("analysis_payload", {}).get("atr_target"), 0.0))
    price = max(price, _safe_float(row.get("analysis_payload", {}).get("close"), 0.0), _safe_float(row.get("analysis_payload", {}).get("support"), 0.0), 0.0)
    if price <= 0.0:
        return {
            "ai_forecast_available": False,
            "ai_forecast_reason": "price_unavailable",
        }

    session_score = _safe_float(row.get("session_adjusted_opportunity_score"), _safe_float(row.get("opportunity_score"), 50.0))
    volatility_score = _safe_float(row.get("volatility_risk_score"), 50.0)
    engine_alignment = _safe_float(row.get("engine_alignment_score"), 50.0)
    news_confidence = _safe_float(row.get("news_confidence"), 0.0)
    base_return_pct = _clamp((session_score - 50.0) * 0.08 + (_safe_float(row.get("kronos_contribution_to_score"), 0.0) * 0.4), -6.0, 6.0)
    range_pct = _clamp(1.4 + volatility_score * 0.055 + max(0.0, 65.0 - engine_alignment) * 0.015, 1.2, 10.0)
    base_price = round(price * (1.0 + base_return_pct / 100.0), 4)
    bullish_price = round(price * (1.0 + (base_return_pct + range_pct * 0.55) / 100.0), 4)
    bearish_price = round(price * (1.0 + (base_return_pct - range_pct * 0.75) / 100.0), 4)
    support_low = round(price * (1.0 - (range_pct * 0.35) / 100.0), 4)
    invalidation_low = round(price * (1.0 - (range_pct * 0.65) / 100.0), 4)
    upside_low = round(price * (1.0 + max(base_return_pct, 0.4) / 100.0), 4)
    upside_high = round(bullish_price, 4)
    downside_low = round(bearish_price, 4)
    downside_high = round(price * (1.0 - max(range_pct * 0.25, 0.4) / 100.0), 4)
    forecast_confidence = round(_clamp(session_score * 0.42 + engine_alignment * 0.28 + news_confidence * 0.14 + (100.0 - volatility_score) * 0.16, 0.0, 100.0), 4)
    risk_level = "high" if volatility_score >= 70.0 else "medium" if volatility_score >= 42.0 else "low"
    return {
        "ai_forecast_available": True,
        "ai_current_price": round(price, 4),
        "ai_base_scenario_price": base_price,
        "ai_bullish_scenario_price": bullish_price,
        "ai_bearish_scenario_price": bearish_price,
        "ai_expected_range_low": bearish_price,
        "ai_expected_range_high": bullish_price,
        "ai_forecast_horizon": "2_10d",
        "ai_forecast_confidence": forecast_confidence,
        "ai_forecast_risk_level": risk_level,
        "ai_support_zone_low": support_low,
        "ai_invalidation_zone_low": invalidation_low,
        "ai_upside_target_zone_low": upside_low,
        "ai_upside_target_zone_high": upside_high,
        "ai_downside_risk_zone_low": downside_low,
        "ai_downside_risk_zone_high": downside_high,
        "ai_engine_contribution_chart": [
            {"engine": "classic", "value": _safe_float(row.get("classic_contribution_to_score"), 0.0)},
            {"engine": "ranking", "value": _safe_float(row.get("ranking_contribution_to_score"), 0.0)},
            {"engine": "ml", "value": _safe_float(row.get("ml_contribution_to_score"), 0.0)},
            {"engine": "dl", "value": _safe_float(row.get("dl_contribution_to_score"), 0.0)},
            {"engine": "kronos", "value": _safe_float(row.get("kronos_contribution_to_score"), 0.0)},
            {"engine": "news", "value": _safe_float(row.get("news_contribution_to_score"), 0.0)},
            {"engine": "market_context", "value": _safe_float(row.get("market_context_contribution_to_score"), 0.0)},
        ],
        "ai_previous_forecast_vs_actual": {
            "available": False,
            "reason": "comparison_not_computed_in_cycle_scope",
        },
    }

def _extract_intent_metadata(symbol_audit_events: list[dict], symbol_order_events: list[dict]) -> dict:
    for event in (symbol_audit_events or []):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        metadata = payload.get("intent_metadata") if isinstance(payload.get("intent_metadata"), dict) else None
        if metadata:
            return metadata
    for event in (symbol_order_events or []):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        metadata = payload.get("intent_metadata") if isinstance(payload.get("intent_metadata"), dict) else None
        if metadata:
            return metadata
    return {}


def _extract_broker_fields(payload: dict | None) -> dict:
    body = payload if isinstance(payload, dict) else {}
    broker = body.get("broker") if isinstance(body.get("broker"), dict) else {}
    order = broker.get("order") if isinstance(broker.get("order"), dict) else {}
    fill = body.get("fill") if isinstance(body.get("fill"), dict) else {}

    return {
        "broker_skipped": bool(broker.get("skipped")),
        "broker_order_id": order.get("id") or broker.get("order_id"),
        "broker_status": order.get("status") or broker.get("status") or body.get("status") or body.get("execution_state"),
        "broker_rejection_code": broker.get("code") or broker.get("error_code") or body.get("rejection_code"),
        "broker_rejection_message": broker.get("error") or body.get("rejection_message"),
        "broker_skip_reason": broker.get("reason") or broker.get("skip_reason") or body.get("skip_reason"),
        "broker_client_order_id": body.get("client_order_id"),
        "fill_qty": fill.get("filled_quantity") or fill.get("quantity") or fill.get("qty"),
        "fill_price": fill.get("fill_price") or fill.get("avg_fill_price") or fill.get("price"),
        "fill_ratio": fill.get("fill_ratio"),
        "raw_broker_payload": broker if broker else {},
    }


def _normalize_broker_outcome_code(
    *,
    broker_order_submitted: bool,
    broker_order_status: str | None,
    broker_rejection_message: str | None,
    trade_fill_status: str,
    broker_cancelled: bool,
) -> str:
    if not broker_order_submitted:
        return "broker_not_called"
    if trade_fill_status == "order_filled":
        return "order_filled"
    if trade_fill_status == "order_partially_filled":
        return "order_partially_filled"
    if broker_rejection_message:
        return "order_rejected"
    if broker_cancelled:
        return "order_cancelled"

    normalized_status = str(broker_order_status or "").strip().lower()
    if normalized_status in {"filled", "fill", "executed"}:
        return "order_filled"
    if normalized_status in {"partially_filled", "partial_fill", "partial"}:
        return "order_partially_filled"
    if normalized_status in {"rejected", "error", "failed"}:
        return "order_rejected"
    if normalized_status in {"canceled", "cancelled"}:
        return "order_cancelled"
    if normalized_status in {"accepted", "acknowledged", "new"}:
        return "order_accepted"
    if normalized_status in {"pending", "open", "submitted", "queued"}:
        return "order_pending"
    return "order_submitted"


def _derive_why_no_broker_order(
    *,
    broker_order_submitted: bool,
    market_open: bool,
    guardrail_result: str,
    guardrail_reason_code: str | None,
    derived_reason_code: str,
    final_outcome_code: str,
    final_outcome_detail: str,
) -> tuple[str, str]:
    if broker_order_submitted:
        return ("order_submitted", "Broker order was submitted.")
    if not market_open:
        return ("market_closed", "Market is closed; broker submission skipped.")
    if guardrail_result == "blocked":
        return (
            guardrail_reason_code or "risk_gate_blocked",
            final_outcome_detail or "Blocked by execution guardrails.",
        )
    if derived_reason_code in {"existing_long_position", "existing_short_position", "no_action_from_signal", "existing_long_position_no_add"} or derived_reason_code in _NO_BROKER_ADD_LONG_REASON_CODES:
        return (derived_reason_code, final_outcome_detail)
    if final_outcome_code in {
        "duplicate_intent_suppressed",
        "insufficient_cash",
        "insufficient_margin",
        "risk_gate_blocked",
        "market_closed",
    } or final_outcome_code in _NO_BROKER_ADD_LONG_REASON_CODES:
        return (final_outcome_code, final_outcome_detail)
    return ("broker_not_called", final_outcome_detail or "Broker was not called.")


def _infer_existing_position_reason(row: dict) -> tuple[str | None, str | None]:
    signal = _normalize_signal(row.get("analysis_signal"))
    derived_intent = str(row.get("derived_intent") or "").strip().upper()
    has_open_long = bool(row.get("has_open_long"))
    has_open_short = bool(row.get("has_open_short"))
    explicit_code = str(
        row.get("add_block_reason")
        or row.get("why_no_broker_order_code")
        or row.get("final_outcome_code")
        or ""
    ).strip().lower()

    if explicit_code in _NO_BROKER_ADD_LONG_REASON_CODES:
        detail = str(row.get("final_outcome_detail") or row.get("intent_reason") or "")
        return (explicit_code, detail or explicit_code)

    if signal == "BUY" and has_open_long and derived_intent in {"NONE", "SUPPRESSED", "NO_ACTION"}:
        return ("existing_long_position", "BUY not added because LONG is already open")
    if signal == "SELL" and has_open_short and derived_intent in {"NONE", "SUPPRESSED", "NO_ACTION"}:
        return ("existing_short_position", "SELL suppressed because SHORT already open")
    return (None, None)


def _infer_no_broker_reason(row: dict) -> tuple[str, str]:
    existing_reason_code, existing_reason_detail = _infer_existing_position_reason(row)
    if existing_reason_code:
        return (
            existing_reason_code,
            str(row.get("final_outcome_detail") or row.get("intent_reason") or existing_reason_detail),
        )

    final_code = str(row.get("final_outcome_code") or "").strip().lower()
    final_detail = str(row.get("final_outcome_detail") or "").strip()
    if final_code in {
        "existing_long_position",
        "existing_short_position",
        "insufficient_cash",
        "insufficient_margin",
        "risk_gate_blocked",
        "market_closed",
        "duplicate_intent_suppressed",
        "no_action_from_signal",
        "broker_not_called",
    } or final_code in _NO_BROKER_ADD_LONG_REASON_CODES:
        return (final_code, final_detail or "No broker order in this cycle.")

    rejection_text = str(
        row.get("broker_rejection_message")
        or row.get("broker_rejection_reason")
        or ""
    ).strip()
    rejection_lower = rejection_text.lower()
    if "market_closed" in rejection_lower:
        return ("market_closed", rejection_text or "Market closed; no broker call was made.")
    if "not_called" in rejection_lower:
        return ("broker_not_called", rejection_text or "Broker was not called.")

    if str(row.get("market_hours_check_result") or "").strip().lower() == "blocked":
        return ("market_closed", final_detail or "Market closed; no broker order submitted.")
    if str(row.get("guardrail_result") or "").strip().lower() == "blocked":
        reason_code = str(row.get("guardrail_reason_code") or "risk_gate_blocked").strip().lower()
        reason_detail = str(row.get("guardrail_reason_detail") or final_detail or "Blocked by guardrails").strip()
        return (reason_code or "risk_gate_blocked", reason_detail)

    return ("broker_not_called", final_detail or "No broker call in this cycle.")


def _normalize_skip_reason(value: str | None) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if "market_closed" in raw or ("market" in raw and "closed" in raw):
        return "market_closed"
    if raw in {"broker_not_ready", "not_ready", "broker_disabled"}:
        return "broker_skip_policy"
    if "halt" in raw:
        return "execution_halted"
    if "risk" in raw and "block" in raw:
        return "risk_gate_blocked"
    if "cash" in raw:
        return "insufficient_cash"
    return raw


def _infer_execution_skip_reason(row: dict, fallback_code: str | None = None) -> str:
    normalized_raw_reason = _normalize_skip_reason(
        row.get("execution_skip_reason")
        or row.get("broker_skip_reason")
        or row.get("broker_rejection_message")
        or row.get("broker_rejection_reason")
    )
    if normalized_raw_reason:
        return normalized_raw_reason

    if str(row.get("market_hours_check_result") or "").strip().lower() == "blocked":
        return "market_closed"

    if str(row.get("guardrail_result") or "").strip().lower() == "blocked":
        reason_code = str(row.get("guardrail_reason_code") or fallback_code or "risk_gate_blocked").strip().lower()
        return reason_code or "risk_gate_blocked"

    if fallback_code:
        return str(fallback_code).strip().lower() or "broker_skip_policy"

    return "broker_skip_policy"


def _compact_prior_broker_context(row: dict) -> dict | None:
    context = {
        "broker_order_id": row.get("broker_order_id"),
        "broker_client_order_id": row.get("broker_client_order_id"),
        "broker_order_status": row.get("broker_order_status"),
        "broker_submission_at": row.get("broker_submission_at"),
        "broker_last_status_at": row.get("broker_last_status_at"),
        "broker_rejection_code": row.get("broker_rejection_code"),
        "broker_rejection_message": row.get("broker_rejection_message") or row.get("broker_rejection_reason"),
        "broker_skip_reason": row.get("broker_skip_reason"),
        "filled_qty": row.get("filled_qty"),
        "average_fill_price": row.get("average_fill_price"),
        "broker_outcome_code": row.get("broker_outcome_code"),
    }
    timeline = row.get("broker_event_timeline")
    if isinstance(timeline, list) and timeline:
        context["broker_event_timeline"] = timeline
    raw_payload = row.get("raw_broker_payload")
    if isinstance(raw_payload, dict) and raw_payload:
        context["raw_broker_payload"] = raw_payload

    has_signal = any(
        value not in {None, "", 0, 0.0}
        for key, value in context.items()
        if key != "broker_event_timeline" and key != "raw_broker_payload"
    )
    if not has_signal and not context.get("broker_event_timeline") and not context.get("raw_broker_payload"):
        return None
    return context


def _clear_cycle_broker_fields(row: dict) -> None:
    row["broker_order_submitted"] = False
    row["broker_order_id"] = None
    row["broker_client_order_id"] = None
    row["broker_order_status"] = None
    row["broker_submission_at"] = None
    row["broker_last_status_at"] = None
    row["broker_rejection_code"] = None
    row["broker_rejection_message"] = None
    row["broker_rejection_reason"] = None
    row["broker_skip_reason"] = None
    row["broker_cancelled"] = False
    row["broker_outcome_code"] = "broker_not_called"
    row["execution_outcome_code"] = "broker_not_called"
    row["trade_fill_status"] = "none"
    row["filled_qty"] = None
    row["average_fill_price"] = None
    row["executed_qty"] = None
    row["executed_price"] = None
    row["actual_execution_action"] = None
    row["final_execution_action"] = None
    row["broker_event_timeline"] = []
    row["first_fill_at"] = None
    row["final_fill_at"] = None


def _enforce_cycle_broker_invariants(row: dict) -> dict:
    normalized = dict(row)
    derived_intent = str(normalized.get("derived_intent") or "").strip().upper()
    requested_action = str(normalized.get("requested_execution_action") or "").strip().upper()
    if not requested_action:
        requested_action = str(normalized.get("final_execution_action") or "").strip().upper()
    if not requested_action and derived_intent and derived_intent != "NONE":
        requested_action = derived_intent
    normalized["requested_execution_action"] = requested_action or None
    normalized["decision_outcome_code"] = str(
        normalized.get("decision_outcome_code")
        or normalized.get("final_outcome_code")
        or "no_action_from_signal"
    ).strip().lower()
    normalized["decision_outcome_detail"] = str(
        normalized.get("decision_outcome_detail")
        or normalized.get("final_outcome_detail")
        or normalized.get("intent_reason")
        or ""
    ).strip() or None
    normalized["execution_outcome_code"] = str(
        normalized.get("execution_outcome_code")
        or normalized.get("broker_outcome_code")
        or "broker_not_called"
    ).strip().lower()
    broker_submitted = bool(normalized.get("broker_order_submitted"))
    existing_reason_code, _ = _infer_existing_position_reason(normalized)
    must_be_no_broker = not broker_submitted or existing_reason_code is not None

    if must_be_no_broker:
        prior_context = _compact_prior_broker_context(normalized)
        if prior_context:
            normalized["prior_broker_context"] = {
                **prior_context,
                "note": "Historical/non-current broker context retained for debugging only.",
            }
        if bool(normalized.get("has_open_long")) or bool(normalized.get("has_open_short")):
            normalized["historical_position_context"] = {
                "side": normalized.get("current_position_side"),
                "qty": normalized.get("current_position_qty"),
                "avg_price": normalized.get("current_position_avg_price"),
                "note": "Existing position carried into this cycle.",
            }

        no_broker_code, no_broker_detail = _infer_no_broker_reason(normalized)
        skip_reason = _infer_execution_skip_reason(normalized, no_broker_code)
        _clear_cycle_broker_fields(normalized)
        normalized["why_no_broker_order_code"] = no_broker_code
        normalized["why_no_broker_order_detail"] = no_broker_detail
        normalized["execution_outcome_code"] = "broker_not_called"
        normalized["execution_skip_reason"] = skip_reason

        final_code = str(normalized.get("final_outcome_code") or "").strip().lower()
        if final_code in {
            "order_submitted",
            "order_accepted",
            "order_pending",
            "order_filled",
            "order_partially_filled",
            "order_rejected",
            "broker_rejected",
            "order_cancelled",
            "broker_not_called",
            "",
        }:
            normalized["final_outcome_code"] = no_broker_code
            normalized["final_outcome_detail"] = no_broker_detail
    else:
        # Invariant: if broker call happened this cycle, "why no broker order" must be empty.
        normalized["why_no_broker_order_code"] = None
        normalized["why_no_broker_order_detail"] = None
        normalized["execution_skip_reason"] = None
        actual_action = str(
            normalized.get("actual_execution_action")
            or normalized.get("final_execution_action")
            or normalized.get("requested_execution_action")
            or ""
        ).strip().upper()
        normalized["actual_execution_action"] = actual_action or None
        normalized["final_execution_action"] = actual_action or None
        broker_outcome = str(
            normalized.get("broker_outcome_code")
            or normalized.get("execution_outcome_code")
            or "order_submitted"
        ).strip().lower()
        if broker_outcome == "broker_not_called":
            broker_outcome = "order_submitted"
        execution_outcome = str(
            normalized.get("execution_outcome_code")
            or broker_outcome
            or "order_submitted"
        ).strip().lower()
        if execution_outcome == "broker_not_called":
            execution_outcome = broker_outcome
        normalized["broker_outcome_code"] = broker_outcome
        normalized["execution_outcome_code"] = execution_outcome
        if str(normalized.get("final_outcome_code") or "").strip().lower() == "broker_not_called":
            normalized["final_outcome_code"] = normalized["execution_outcome_code"]

    return normalized


def _build_broker_timeline(order_events: list[dict], *, include_details: bool) -> dict:
    broker_order_submitted = False
    broker_order_id = None
    broker_client_order_id = None
    broker_order_status = None
    broker_rejection_code = None
    broker_rejection_message = None
    broker_skip_reason = None
    broker_submission_at = None
    broker_last_status_at = None
    broker_cancelled = False
    filled_qty = 0.0
    average_fill_price = 0.0
    trade_fill_status = "none"
    raw_broker_payload: dict[str, Any] = {}

    timeline: list[dict] = []

    for event in order_events:
        event_type = str(event.get("event_type") or "").strip().lower()
        created_at = event.get("created_at")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        extracted = _extract_broker_fields(payload)

        broker_client_order_id = broker_client_order_id or extracted["broker_client_order_id"]
        broker_order_id = broker_order_id or extracted["broker_order_id"]
        broker_order_status = extracted["broker_status"] or broker_order_status
        broker_rejection_code = broker_rejection_code or extracted["broker_rejection_code"]
        broker_rejection_message = broker_rejection_message or extracted["broker_rejection_message"]
        broker_skip_reason = broker_skip_reason or extracted["broker_skip_reason"]

        if extracted["raw_broker_payload"]:
            raw_broker_payload = extracted["raw_broker_payload"]

        if event_type == "execution.order.submitted":
            broker_submission_at = broker_submission_at or created_at
            if not extracted["broker_skipped"]:
                broker_order_submitted = True
        if extracted["broker_status"] and created_at:
            broker_last_status_at = created_at
        if created_at and event_type in {"execution.fill.received", "execution.order.acknowledged", "execution.order.canceled"}:
            broker_last_status_at = created_at

        if event_type == "execution.order.canceled":
            broker_cancelled = True

        filled_qty = _safe_float(extracted["fill_qty"], filled_qty)
        average_fill_price = _safe_float(extracted["fill_price"], average_fill_price)
        fill_ratio = _safe_float(extracted["fill_ratio"], 1.0)

        if filled_qty > 0:
            trade_fill_status = "order_partially_filled" if fill_ratio < 0.999 else "order_filled"

        if include_details:
            timeline.append(
                {
                    "event_type": event_type,
                    "created_at": created_at,
                    "status": extracted["broker_status"],
                    "skipped": extracted["broker_skipped"],
                    "skip_reason": extracted["broker_skip_reason"],
                    "rejection_code": extracted["broker_rejection_code"],
                    "rejection_message": extracted["broker_rejection_message"],
                }
            )

    if not broker_order_submitted and broker_submission_at and not broker_skip_reason:
        # Submission event exists but broker call was intentionally skipped.
        broker_skip_reason = "broker_not_called"
    if not broker_order_submitted:
        # No cycle-scoped broker call: rejection message must not masquerade as execution failure.
        broker_rejection_message = None

    broker_outcome_code = _normalize_broker_outcome_code(
        broker_order_submitted=broker_order_submitted,
        broker_order_status=broker_order_status,
        broker_rejection_message=broker_rejection_message,
        trade_fill_status=trade_fill_status,
        broker_cancelled=broker_cancelled,
    )

    return {
        "broker_order_submitted": broker_order_submitted,
        "broker_order_id": broker_order_id,
        "broker_client_order_id": broker_client_order_id,
        "broker_order_status": broker_order_status,
        "broker_submission_at": broker_submission_at,
        "broker_last_status_at": broker_last_status_at,
        "broker_rejection_code": broker_rejection_code,
        "broker_rejection_message": broker_rejection_message,
        "broker_skip_reason": broker_skip_reason,
        "broker_cancelled": broker_cancelled,
        "trade_fill_status": trade_fill_status,
        "filled_qty": round(_safe_float(filled_qty, 0.0), 4),
        "average_fill_price": round(_safe_float(average_fill_price, 0.0), 4),
        "broker_outcome_code": broker_outcome_code,
        "broker_event_timeline": timeline,
        "raw_broker_payload": raw_broker_payload,
    }


def diagnostics_retention_policy() -> dict:
    return {
        "retention_policy": "keep_last_cycles",
        "retention_cycle_limit": max(_safe_int(AUTO_TRADING_DIAGNOSTICS_RETENTION_CYCLES, 200), 1),
        "retention_delete_batch_size": max(_safe_int(AUTO_TRADING_DIAGNOSTICS_RETENTION_DELETE_BATCH_SIZE, 500), 50),
    }


def cleanup_auto_trading_diagnostics_artifacts() -> dict:
    policy = diagnostics_retention_policy()
    retention_cycle_limit = int(policy["retention_cycle_limit"])
    delete_batch_size = int(policy["retention_delete_batch_size"])

    with session_scope() as session:
        stale_run_rows = (
            session.query(AutomationRun.run_id)
            .filter(AutomationRun.job_name == _DIAGNOSTICS_JOB_NAME)
            .order_by(AutomationRun.started_at.desc())
            .offset(retention_cycle_limit)
            .limit(delete_batch_size)
            .all()
        )
        stale_run_ids = [str(row[0]) for row in stale_run_rows if row and row[0]]

        deleted_artifacts = 0
        if stale_run_ids:
            deleted_artifacts = (
                session.query(AutomationArtifact)
                .filter(
                    AutomationArtifact.job_name == _DIAGNOSTICS_JOB_NAME,
                    AutomationArtifact.artifact_type == _DIAGNOSTICS_ARTIFACT_TYPE,
                    AutomationArtifact.run_id.in_(stale_run_ids),
                )
                .delete(synchronize_session=False)
            )

    payload = {
        **policy,
        "cycles_scanned": len(stale_run_ids),
        "artifacts_deleted": int(deleted_artifacts or 0),
    }
    log_event(
        logger,
        logging.INFO,
        "diagnostics.auto_trading.cleanup",
        **payload,
    )
    return payload


def build_auto_trading_diagnostics_payload(
    *,
    cycle_id: str,
    cycle_started_at: str,
    cycle_completed_at: str,
    runtime_state: str,
    delegated: bool,
    symbols: list[str],
    signal_items: list[dict],
    preview_items: list[dict] | None,
    held_positions: dict[str, dict],
    strategy_mode: str,
    trade_direction: str,
    margin_enabled: bool,
    market_open: bool,
    correlation_id: str | None,
    portfolio_summary: dict | None = None,
    auto_trading_config: dict | None = None,
    portfolio_brain: dict | None = None,
    market_session: dict | None = None,
    market_readiness: dict | None = None,
    kronos_payload: dict | None = None,
) -> dict:
    analysis_map = _symbol_analysis_map(signal_items=signal_items, preview_items=preview_items)
    audit_event_map = _collect_events_by_symbol(correlation_id)
    order_event_map = _collect_order_events_by_symbol(correlation_id)
    portfolio = portfolio_summary if isinstance(portfolio_summary, dict) else {}
    portfolio_value = max(_safe_float(portfolio.get("total_equity") or portfolio.get("portfolio_value"), 0.0), 0.0)
    portfolio_brain_payload = portfolio_brain if isinstance(portfolio_brain, dict) else {}
    brain_regime = portfolio_brain_payload.get("regime") if isinstance(portfolio_brain_payload.get("regime"), dict) else {}
    brain_allocation = portfolio_brain_payload.get("allocation") if isinstance(portfolio_brain_payload.get("allocation"), dict) else {}
    market_session_payload = market_session if isinstance(market_session, dict) else (portfolio_brain_payload.get("session") if isinstance(portfolio_brain_payload.get("session"), dict) else {})
    market_readiness_payload = market_readiness if isinstance(market_readiness, dict) else (portfolio_brain_payload.get("market_readiness") if isinstance(portfolio_brain_payload.get("market_readiness"), dict) else {})
    kronos_cycle_payload = kronos_payload if isinstance(kronos_payload, dict) else (portfolio_brain_payload.get("kronos") if isinstance(portfolio_brain_payload.get("kronos"), dict) else {})
    brain_decisions = brain_allocation.get("decisions") if isinstance(brain_allocation.get("decisions"), list) else []
    brain_decision_map: dict[str, dict] = {
        _normalize_symbol(item.get("symbol")): item
        for item in brain_decisions
        if isinstance(item, dict) and _normalize_symbol(item.get("symbol"))
    }
    brain_execution_orchestrator = (
        portfolio_brain_payload.get("execution_orchestrator")
        if isinstance(portfolio_brain_payload.get("execution_orchestrator"), dict)
        else {}
    )
    brain_execution_queue = []
    if isinstance(brain_execution_orchestrator.get("queue_items"), list):
        brain_execution_queue = brain_execution_orchestrator.get("queue_items") or []
    elif isinstance(brain_allocation.get("execution_queue"), list):
        brain_execution_queue = brain_allocation.get("execution_queue") or []
    brain_execution_timeline = []
    if isinstance(brain_execution_orchestrator.get("timeline"), list):
        brain_execution_timeline = brain_execution_orchestrator.get("timeline") or []
    elif isinstance(brain_allocation.get("execution_timeline"), list):
        brain_execution_timeline = brain_allocation.get("execution_timeline") or []
    brain_execution_summary = {}
    if isinstance(brain_execution_orchestrator.get("summary"), dict):
        brain_execution_summary = brain_execution_orchestrator.get("summary") or {}
    elif isinstance(brain_allocation.get("execution_queue_summary"), dict):
        brain_execution_summary = brain_allocation.get("execution_queue_summary") or {}
    brain_queue_map: dict[str, dict] = {
        _normalize_symbol(item.get("symbol")): item
        for item in (brain_execution_queue or [])
        if isinstance(item, dict) and _normalize_symbol(item.get("symbol"))
    }
    retry_config = _cycle_retry_config(auto_trading_config)

    symbol_order: list[str] = []
    for symbol in symbols:
        normalized = _normalize_symbol(symbol)
        if normalized and normalized not in symbol_order:
            symbol_order.append(normalized)
    for symbol in analysis_map.keys():
        if symbol not in symbol_order:
            symbol_order.append(symbol)

    rows: list[dict] = []
    reason_counter: Counter[str] = Counter()

    for symbol in symbol_order:
        analysis = analysis_map.get(symbol, {})
        brain_row = brain_decision_map.get(symbol, {})
        queue_row = brain_queue_map.get(symbol, {}) if isinstance(brain_queue_map.get(symbol, {}), dict) else {}
        position = held_positions.get(symbol, {}) if isinstance(held_positions, dict) else {}
        current_side = _normalize_side(position.get("side"))
        current_qty = _safe_float(position.get("quantity") or position.get("qty"), 0.0)
        current_avg_price = _safe_float(position.get("avg_entry_price") or position.get("avg_entry"), 0.0)
        signal = _normalize_signal(analysis.get("analysis_signal"))

        derived_intent, derived_reason_code, intent_reason, duplicate_check = _derive_intent(
            signal=signal,
            current_side=current_side,
            trade_direction=trade_direction,
            margin_enabled=margin_enabled,
        )
        brain_action = str(brain_row.get("requested_execution_action") or brain_row.get("action_decision") or "").strip().upper()
        if brain_action:
            derived_intent = brain_action
            duplicate_check = "passed" if brain_action not in {"HOLD", "NONE"} else "blocked"
        brain_reason_code = str(brain_row.get("decision_outcome_code") or "").strip().lower()
        if brain_reason_code:
            derived_reason_code = brain_reason_code
        brain_reason_detail = str(brain_row.get("decision_outcome_detail") or "").strip()
        if brain_reason_detail:
            intent_reason = brain_reason_detail

        symbol_audit_events = audit_event_map.get(symbol, [])
        blocked_event = next((e for e in symbol_audit_events if e.get("event_type") == "execution_guardrails_blocked"), None)
        short_blocked_event = next((e for e in symbol_audit_events if e.get("event_type") == "short_open_blocked"), None)
        action_events = [
            e
            for e in symbol_audit_events
            if e.get("event_type") in {"open_long", "add_long", "open_short", "close_long", "close_short"}
        ]
        skipped_event = next((e for e in symbol_audit_events if e.get("event_type") == "execution_intent_skipped"), None)
        symbol_order_events = order_event_map.get(symbol, [])
        intent_metadata = _extract_intent_metadata(symbol_audit_events, symbol_order_events)

        if any(str(event.get("event_type") or "").lower() == "add_long" for event in symbol_audit_events):
            derived_intent = "ADD_LONG"
            derived_reason_code = "add_long_allowed"
            intent_reason = "BUY added to existing LONG based on target-size policy"
            duplicate_check = "passed"
        elif skipped_event and signal == "BUY" and current_side == "LONG":
            skip_payload = skipped_event.get("payload") if isinstance(skipped_event.get("payload"), dict) else {}
            skip_meta = skip_payload.get("intent_metadata") if isinstance(skip_payload.get("intent_metadata"), dict) else intent_metadata
            add_block_reason = str(skip_meta.get("add_block_reason") or "").strip().lower()
            if add_block_reason:
                derived_intent = "NONE"
                derived_reason_code = add_block_reason
                intent_reason = str(skip_payload.get("reason") or intent_reason or add_block_reason)
                duplicate_check = "blocked"

        final_execution_action = "NONE"
        executed_qty = 0.0
        executed_price = 0.0
        if action_events:
            mapped_actions = []
            for event in action_events:
                event_type = str(event.get("event_type") or "").lower()
                mapped_actions.append(event_type.upper())
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                executed_qty = _safe_float(payload.get("quantity") or executed_qty, executed_qty)
                executed_price = _safe_float(payload.get("price") or executed_price, executed_price)
            final_execution_action = "+".join(sorted(set(mapped_actions))) if mapped_actions else "NONE"

        broker_enrichment = _build_broker_timeline(symbol_order_events, include_details=True)
        trade_fill_status = str(broker_enrichment.get("trade_fill_status") or "none")

        guardrail_result = "not_checked"
        guardrail_reason_code = None
        guardrail_reason_detail = None
        risk_check_result = None
        cash_check_result = None
        margin_check_result = "passed" if margin_enabled else "cash_mode"

        if blocked_event:
            payload = blocked_event.get("payload") if isinstance(blocked_event.get("payload"), dict) else {}
            block_reason = payload.get("blocked_reason")
            blocking_reasons = payload.get("blocking_reasons") if isinstance(payload.get("blocking_reasons"), list) else []
            guardrail_reason_code, guardrail_reason_detail = _map_block_reason_to_code(str(block_reason or ""), blocking_reasons)
            guardrail_result = "blocked"
            risk_check = payload.get("risk_check") if isinstance(payload.get("risk_check"), dict) else {}
            cash_check = payload.get("cash_check") if isinstance(payload.get("cash_check"), dict) else {}
            risk_check_result = "blocked" if risk_check and not bool(risk_check.get("allowed", True)) else "passed"
            cash_check_result = "blocked" if cash_check and not bool(cash_check.get("allowed", True)) else "passed"
        elif short_blocked_event:
            guardrail_result = "blocked"
            guardrail_reason_code = "insufficient_margin"
            guardrail_reason_detail = "Cash-only execution blocks opening short positions."
            risk_check_result = "passed"
            cash_check_result = "blocked"
        elif action_events:
            guardrail_result = "passed"
            guardrail_reason_code = "order_submitted"
            guardrail_reason_detail = "Execution guardrails passed"
            risk_check_result = "passed"
            cash_check_result = "passed"

        if derived_reason_code in {"add_blocked_by_cash", "add_blocked_by_risk", "add_blocked_by_market_hours"} and guardrail_result != "blocked":
            guardrail_result = "blocked"
            guardrail_reason_code = derived_reason_code
            guardrail_reason_detail = intent_reason
            if derived_reason_code == "add_blocked_by_cash":
                cash_check_result = "blocked"
            elif derived_reason_code == "add_blocked_by_risk":
                risk_check_result = "blocked"
            else:
                risk_check_result = risk_check_result or "blocked"

        market_hours_check_result = "passed" if market_open else "blocked"

        final_outcome_code = "no_action_from_signal"
        final_outcome_detail = intent_reason

        if not market_open:
            final_outcome_code = "market_closed"
            final_outcome_detail = "Cycle blocked by market hours"
        elif guardrail_result == "blocked":
            final_outcome_code = guardrail_reason_code or "risk_gate_blocked"
            final_outcome_detail = guardrail_reason_detail or "Blocked by execution guardrails"
        elif derived_reason_code in {"existing_long_position", "existing_short_position"} or derived_reason_code in _ADD_LONG_REASON_CODES:
            final_outcome_code = derived_reason_code
            final_outcome_detail = intent_reason
        elif skipped_event:
            skip_payload = skipped_event.get("payload") if isinstance(skipped_event.get("payload"), dict) else {}
            final_outcome_code = "duplicate_intent_suppressed"
            final_outcome_detail = str(skip_payload.get("reason") or intent_reason)
        else:
            final_outcome_code = str(broker_enrichment.get("broker_outcome_code") or "no_action_from_signal")
            if final_outcome_code == "order_rejected":
                final_outcome_detail = str(
                    broker_enrichment.get("broker_rejection_message")
                    or "Broker rejected the order."
                )
            elif final_outcome_code == "order_cancelled":
                final_outcome_detail = "Order was cancelled."
            elif final_outcome_code == "order_pending":
                final_outcome_detail = "Order is pending broker completion."
            elif final_outcome_code == "order_accepted":
                final_outcome_detail = "Order accepted by broker."
            elif final_outcome_code == "order_submitted":
                final_outcome_detail = "Order submitted to broker."
            elif final_outcome_code == "broker_not_called":
                final_outcome_detail = "Broker was not called."
            elif final_outcome_code == "order_filled":
                final_outcome_detail = "Order filled."
            elif final_outcome_code == "order_partially_filled":
                final_outcome_detail = "Order partially filled."

        why_no_broker_order_code, why_no_broker_order_detail = _derive_why_no_broker_order(
            broker_order_submitted=bool(broker_enrichment.get("broker_order_submitted")),
            market_open=market_open,
            guardrail_result=guardrail_result,
            guardrail_reason_code=guardrail_reason_code,
            derived_reason_code=derived_reason_code,
            final_outcome_code=final_outcome_code,
            final_outcome_detail=final_outcome_detail,
        )
        requested_execution_action = derived_intent if derived_intent not in {"", "NONE"} else None
        if not requested_execution_action and str(brain_row.get("requested_execution_action") or "").strip():
            requested_execution_action = str(brain_row.get("requested_execution_action")).strip().upper()
        actual_execution_action = final_execution_action if final_execution_action not in {"", "NONE"} else None

        row_payload = {
            "cycle_id": cycle_id,
            "cycle_started_at": cycle_started_at,
            "cycle_completed_at": cycle_completed_at,
            "runtime_state": runtime_state,
            "delegated": bool(delegated),
            "symbol": symbol,
            "analysis_signal": signal,
            "analysis_score": _safe_float(analysis.get("analysis_score"), 0.0),
            "confidence": _safe_float(analysis.get("confidence"), 0.0),
            "model_source_breakdown": analysis.get("analysis_payload") or {},
            "analysis_payload": analysis.get("analysis_payload") if isinstance(analysis.get("analysis_payload"), dict) else {},
            "current_position_side": current_side,
            "current_position_qty": round(current_qty, 4),
            "current_position_avg_price": round(current_avg_price, 4),
            "current_position_value": round(_safe_float(intent_metadata.get("current_position_value"), _safe_float(brain_row.get("current_position_value"), round(current_qty * _safe_float(analysis.get("price") or current_avg_price, 0.0), 4))), 4),
            "current_position_pct": round(_safe_float(intent_metadata.get("current_position_pct"), _safe_float(brain_row.get("current_position_pct"), ((current_qty * _safe_float(analysis.get("price") or current_avg_price, 0.0)) / portfolio_value * 100.0 if portfolio_value > 0 else 0.0))), 4),
            "target_position_value": round(_safe_float(intent_metadata.get("target_position_value"), _safe_float(brain_row.get("target_position_value"), 0.0)), 4),
            "target_position_pct": round(_safe_float(intent_metadata.get("target_position_pct"), _safe_float(brain_row.get("target_position_pct"), 0.0)), 4),
            "desired_delta_pct": round(_safe_float(brain_row.get("desired_delta_pct"), 0.0), 4),
            "addable_value": round(_safe_float(intent_metadata.get("addable_value"), _safe_float(brain_row.get("desired_delta_value"), 0.0)), 4),
            "proposed_add_qty": round(_safe_float(intent_metadata.get("proposed_add_qty"), _safe_float(brain_row.get("proposed_order_qty"), 0.0)), 4),
            "add_block_reason": str(intent_metadata.get("add_block_reason") or brain_row.get("decision_outcome_code") or "").strip().lower() or None,
            "opportunity_score": round(_safe_float(brain_row.get("opportunity_score"), analysis.get("opportunity_score")), 4),
            "session_adjusted_opportunity_score": round(_safe_float(brain_row.get("session_adjusted_opportunity_score"), brain_row.get("opportunity_score")), 4),
            "conviction_tier": str(brain_row.get("conviction_tier") or analysis.get("conviction_tier") or "").strip().lower() or None,
            "setup_type": str(brain_row.get("setup_type") or analysis.get("setup_type") or "").strip() or None,
            "expected_direction": str(brain_row.get("expected_direction") or analysis.get("expected_direction") or "").strip().upper() or None,
            "preferred_action_candidate": str(brain_row.get("preferred_action_candidate") or analysis.get("preferred_action_candidate") or "").strip().upper() or None,
            "preferred_holding_horizon": str(brain_row.get("preferred_holding_horizon") or analysis.get("preferred_holding_horizon") or "").strip() or None,
            "risk_reward_estimate": round(_safe_float(brain_row.get("risk_reward_estimate"), analysis.get("risk_reward_estimate")), 4),
            "security_name": str(brain_row.get("security_name") or "").strip() or None,
            "market_cap": round(_safe_float(brain_row.get("market_cap"), 0.0), 4),
            "market_cap_bucket": str(brain_row.get("market_cap_bucket") or "").strip().lower() or None,
            "listed_exchange": str(brain_row.get("listed_exchange") or "").strip() or None,
            "us_equity_eligible": bool(brain_row.get("us_equity_eligible", True)),
            "is_etf": bool(brain_row.get("is_etf", False)),
            "stock_quality_score": round(_safe_float(brain_row.get("stock_quality_score"), 0.0), 4),
            "technical_score": round(_safe_float(brain_row.get("technical_score"), analysis.get("technical_score")), 4),
            "ranking_score": round(_safe_float(brain_row.get("ranking_score"), analysis.get("rank_score")), 4),
            "multi_timeframe_score": round(_safe_float(brain_row.get("multi_timeframe_score"), analysis.get("multi_timeframe_score")), 4),
            "relative_strength_score": round(_safe_float(brain_row.get("relative_strength_score"), analysis.get("relative_strength_score")), 4),
            "sector_strength_score": round(_safe_float(brain_row.get("sector_strength_score"), analysis.get("sector_strength_score")), 4),
            "gap_pct": round(_safe_float(brain_row.get("gap_pct"), analysis.get("gap_pct")), 4),
            "gap_type": str(brain_row.get("gap_type") or analysis.get("gap_type") or "").strip().lower() or None,
            "gap_quality_score": round(_safe_float(brain_row.get("gap_quality_score"), analysis.get("gap_quality_score")), 4),
            "volatility_risk": str(brain_row.get("volatility_risk") or analysis.get("volatility_risk") or "").strip().lower() or None,
            "volatility_risk_score": round(_safe_float(brain_row.get("volatility_risk_score"), analysis.get("volatility_risk_score")), 4),
            "spread_risk": str(brain_row.get("spread_risk") or analysis.get("spread_risk") or "").strip().lower() or None,
            "spread_risk_score": round(_safe_float(brain_row.get("spread_risk_score"), analysis.get("spread_risk_score")), 4),
            "liquidity_score": round(_safe_float(brain_row.get("liquidity_score"), analysis.get("liquidity_score")), 4),
            "volume_ratio": round(_safe_float(brain_row.get("volume_ratio"), analysis.get("volume_ratio")), 4),
            "opening_score": round(_safe_float(brain_row.get("opening_score"), analysis.get("opening_score")), 4),
            "premarket_score": round(_safe_float(brain_row.get("premarket_score"), analysis.get("premarket_score")), 4),
            "open_confirmation_score": round(_safe_float(brain_row.get("open_confirmation_score"), analysis.get("open_confirmation_score")), 4),
            "breakout_quality_score": round(_safe_float(brain_row.get("breakout_quality_score"), 0.0), 4),
            "pullback_quality_score": round(_safe_float(brain_row.get("pullback_quality_score"), 0.0), 4),
            "continuation_score": round(_safe_float(brain_row.get("continuation_score"), 0.0), 4),
            "fade_risk": round(_safe_float(brain_row.get("fade_risk"), 0.0), 4),
            "add_quality_score": round(_safe_float(brain_row.get("add_quality_score"), analysis.get("add_quality_score")), 4),
            "reduce_pressure_score": round(_safe_float(brain_row.get("reduce_pressure_score"), analysis.get("reduce_pressure_score")), 4),
            "exit_pressure_score": round(_safe_float(brain_row.get("exit_pressure_score"), analysis.get("exit_pressure_score")), 4),
            "news_relevance_score": round(_safe_float(brain_row.get("news_relevance_score"), 0.0), 4),
            "news_sentiment_score": round(_safe_float(brain_row.get("news_sentiment_score"), 0.0), 4),
            "news_strength_score": round(_safe_float(brain_row.get("news_strength_score"), 0.0), 4),
            "catalyst_type": str(brain_row.get("catalyst_type") or "").strip().lower() or None,
            "catalyst_horizon": str(brain_row.get("catalyst_horizon") or "").strip().lower() or None,
            "catalyst_scope": str(brain_row.get("catalyst_scope") or "").strip().lower() or None,
            "catalyst_alignment_with_price": str(brain_row.get("catalyst_alignment_with_price") or "").strip().lower() or None,
            "news_confidence": round(_safe_float(brain_row.get("news_confidence"), 0.0), 4),
            "news_warning_flags": brain_row.get("news_warning_flags") if isinstance(brain_row.get("news_warning_flags"), list) else [],
            "news_action_bias": str(brain_row.get("news_action_bias") or "").strip().upper() or None,
            "news_supports_entry": bool(brain_row.get("news_supports_entry", False)),
            "news_supports_add": bool(brain_row.get("news_supports_add", False)),
            "news_supports_reduce": bool(brain_row.get("news_supports_reduce", False)),
            "news_supports_exit": bool(brain_row.get("news_supports_exit", False)),
            "news_requires_wait": bool(brain_row.get("news_requires_wait", False)),
            "news_no_trade_reason": str(brain_row.get("news_no_trade_reason") or "").strip().lower() or None,
            "news_contribution_to_score": round(_safe_float(brain_row.get("news_contribution_to_score"), 0.0), 4),
            "market_context_contribution_to_score": round(_safe_float(brain_row.get("market_context_contribution_to_score"), 0.0), 4),
            "judgment_size_multiplier": round(_safe_float(brain_row.get("judgment_size_multiplier"), 1.0), 4),
            "tactical_small_cap_candidate": bool(brain_row.get("tactical_small_cap_candidate", False)),
            "tactical_small_cap_score": round(_safe_float(brain_row.get("tactical_small_cap_score"), 0.0), 4),
            "tactical_small_cap_allowed": bool(brain_row.get("tactical_small_cap_allowed", False)),
            "small_cap_liquidity_quality": str(brain_row.get("small_cap_liquidity_quality") or "").strip().lower() or None,
            "small_cap_spread_risk": str(brain_row.get("small_cap_spread_risk") or "").strip().lower() or None,
            "small_cap_catalyst_quality": round(_safe_float(brain_row.get("small_cap_catalyst_quality"), 0.0), 4),
            "small_cap_position_size_multiplier": round(_safe_float(brain_row.get("small_cap_position_size_multiplier"), 1.0), 4),
            "small_cap_no_trade_reason": str(brain_row.get("small_cap_no_trade_reason") or "").strip().lower() or None,
            "engine_conflicts_present": bool(brain_row.get("engine_conflicts_present", False)),
            "engine_conflict_reason": str(brain_row.get("engine_conflict_reason") or "").strip().lower() or None,
            "engine_alignment_score": round(_safe_float(brain_row.get("engine_alignment_score"), 0.0), 4),
            "portfolio_priority_rank": _safe_int(brain_row.get("portfolio_priority_rank"), 0) or None,
            "capital_competition_reason": str(brain_row.get("capital_competition_reason") or "").strip() or None,
            "better_use_of_capital_reason": str(brain_row.get("better_use_of_capital_reason") or "").strip() or None,
            "replacement_candidate": str(brain_row.get("replacement_candidate") or "").strip() or None,
            "displaced_symbol": str(brain_row.get("displaced_symbol") or "").strip() or None,
            "funded": bool(brain_row.get("funded", False)),
            "funded_partially": bool(brain_row.get("funded_partially", False)),
            "partial_funding_applied": bool(brain_row.get("partial_funding_applied", False)),
            "funding_status": str(brain_row.get("funding_status") or "").strip().lower() or None,
            "funding_decision": str(brain_row.get("funding_decision") or "").strip().lower() or None,
            "funding_ratio": round(_safe_float(brain_row.get("funding_ratio"), 0.0), 4),
            "partial_funding_reason": str(brain_row.get("partial_funding_reason") or "").strip().lower() or None,
            "capital_requested_value": round(_safe_float(brain_row.get("capital_requested_value"), 0.0), 4),
            "capital_approved_value": round(_safe_float(brain_row.get("capital_approved_value"), 0.0), 4),
            "remaining_unfunded_value": round(_safe_float(brain_row.get("remaining_unfunded_value"), 0.0), 4),
            "requested_order_qty": round(_safe_float(brain_row.get("requested_order_qty"), brain_row.get("proposed_order_qty")), 4),
            "approved_order_qty": round(_safe_float(brain_row.get("approved_order_qty"), 0.0), 4),
            "approved_position_pct": round(_safe_float(brain_row.get("approved_position_pct"), brain_row.get("current_position_pct")), 4),
            "capital_reserved_value": round(_safe_float(brain_row.get("capital_reserved_value"), 0.0), 4),
            "available_cash_before": round(_safe_float(brain_row.get("available_cash_before"), 0.0), 4),
            "available_cash_after": round(_safe_float(brain_row.get("available_cash_after"), 0.0), 4),
            "regime_adjusted_budget": round(_safe_float(brain_row.get("regime_adjusted_budget"), 0.0), 4),
            "portfolio_slot_consumed": _safe_int(brain_row.get("portfolio_slot_consumed"), 0),
            "portfolio_slot_available": _safe_int(brain_row.get("portfolio_slot_available"), 0),
            "planned_execution_action": str(brain_row.get("planned_execution_action") or "").strip().upper() or None,
            "execution_priority_band": str(brain_row.get("execution_priority_band") or "deferred").strip().lower(),
            "execution_priority": str(brain_row.get("execution_priority") or analysis.get("execution_priority") or "normal").strip().lower(),
            "order_style_preference": str(brain_row.get("order_style_preference") or queue_row.get("order_style_preference") or analysis.get("order_style_preference") or "market").strip().lower(),
            "session_state": str(brain_row.get("session_state") or market_session_payload.get("session_state") or market_session_payload.get("session_code") or "").strip().lower() or None,
            "session_order_plan": str(brain_row.get("session_order_plan") or "").strip().lower() or None,
            "order_session_type": str(brain_row.get("order_session_type") or "").strip().lower() or None,
            "session_order_style_preference": str(brain_row.get("session_order_style_preference") or "").strip().lower() or None,
            "session_time_in_force_preference": str(brain_row.get("session_time_in_force_preference") or "").strip().lower() or None,
            "order_session_route": str(brain_row.get("order_session_route") or "").strip().lower() or None,
            "extended_hours_eligible": bool(brain_row.get("extended_hours_eligible", False)),
            "queued_for_open": bool(brain_row.get("queued_for_open", False)),
            "opening_auction_candidate": bool(brain_row.get("opening_auction_candidate", False)),
            "premarket_live_candidate": bool(brain_row.get("premarket_live_candidate", False)),
            "submit_before_open": bool(brain_row.get("submit_before_open", False)),
            "submit_after_open": bool(brain_row.get("submit_after_open", False)),
            "wait_for_open_confirmation": bool(brain_row.get("wait_for_open_confirmation", False)),
            "session_preferred_action": str(brain_row.get("session_preferred_action") or "").strip().upper() or None,
            "session_reason": str(brain_row.get("session_reason") or "").strip().lower() or None,
            "premarket_submit_reason": str(brain_row.get("premarket_submit_reason") or "").strip().lower() or None,
            "queued_for_open_reason": str(brain_row.get("queued_for_open_reason") or "").strip().lower() or None,
            "wait_for_open_reason": str(brain_row.get("wait_for_open_reason") or "").strip().lower() or None,
            "no_trade_before_open_reason": str(brain_row.get("no_trade_before_open_reason") or "").strip().lower() or None,
            "premarket_submission_allowed": bool(brain_row.get("premarket_submission_allowed", False)),
            "premarket_submission_block_reason": str(brain_row.get("premarket_submission_block_reason") or "").strip().lower() or None,
            "session_queue_type": str(brain_row.get("session_queue_type") or "").strip().lower() or None,
            "queue_activation_time": brain_row.get("queue_activation_time"),
            "queue_expiration_time": brain_row.get("queue_expiration_time"),
            "waiting_for_market_open": bool(brain_row.get("waiting_for_market_open", False)),
            "waiting_for_open_revalidation": bool(brain_row.get("waiting_for_open_revalidation", False)),
            "session_go_no_go": str(brain_row.get("session_go_no_go") or "").strip().lower() or None,
            "session_gate_result": str(brain_row.get("session_gate_result") or "").strip().lower() or None,
            "session_queue_reason": str(brain_row.get("session_queue_reason") or "").strip().lower() or None,
            "session_order_risk_flags": brain_row.get("session_order_risk_flags") if isinstance(brain_row.get("session_order_risk_flags"), list) else [],
            "session_quality": str(brain_row.get("session_quality") or queue_row.get("session_quality") or "normal").strip().lower(),
            "estimated_slippage_risk": str(brain_row.get("estimated_slippage_risk") or queue_row.get("estimated_slippage_risk") or "low").strip().lower(),
            "queue_item_id": str(brain_row.get("queue_item_id") or queue_row.get("queue_item_id") or "").strip() or None,
            "execution_stage": str(brain_row.get("execution_stage") or queue_row.get("execution_stage") or "").strip().lower() or None,
            "queue_rank": _safe_int(brain_row.get("queue_rank") or queue_row.get("queue_rank"), 0) or None,
            "queue_reason": str(brain_row.get("queue_reason") or queue_row.get("queue_reason") or "").strip().lower() or None,
            "queue_status": str(brain_row.get("queue_status") or queue_row.get("queue_status") or "").strip().lower() or None,
            "queue_gate_result": str(brain_row.get("queue_gate_result") or queue_row.get("queue_gate_result") or "").strip().lower() or None,
            "queue_gate_reason": str(brain_row.get("queue_gate_reason") or queue_row.get("queue_gate_reason") or "").strip().lower() or None,
            "execution_go_no_go": str(brain_row.get("execution_go_no_go") or queue_row.get("execution_go_no_go") or "").strip().lower() or None,
            "defer_reason": str(brain_row.get("defer_reason") or queue_row.get("defer_reason") or "").strip().lower() or None,
            "blocking_reason": str(brain_row.get("blocking_reason") or queue_row.get("blocking_reason") or "").strip().lower() or None,
            "dependency_type": str(brain_row.get("dependency_type") or queue_row.get("dependency_type") or "").strip().lower() or None,
            "depends_on_queue_item_ids": (
                brain_row.get("depends_on_queue_item_ids")
                if isinstance(brain_row.get("depends_on_queue_item_ids"), list)
                else (queue_row.get("depends_on_queue_item_ids") if isinstance(queue_row.get("depends_on_queue_item_ids"), list) else [])
            ),
            "requires_capital_release": bool(brain_row.get("requires_capital_release", queue_row.get("requires_capital_release", False))),
            "dependency_satisfied": bool(brain_row.get("dependency_satisfied", queue_row.get("dependency_satisfied", False))),
            "dependency_outcome": str(brain_row.get("dependency_outcome") or queue_row.get("dependency_outcome") or "").strip().lower() or None,
            "resized_after_capital_release": bool(brain_row.get("resized_after_capital_release", queue_row.get("resized_after_capital_release", False))),
            "funding_recomputed": bool(brain_row.get("funding_recomputed", queue_row.get("funding_recomputed", False))),
            "submission_order": _safe_int(brain_row.get("submission_order") or queue_row.get("submission_order"), 0) or None,
            "queue_wait_seconds": _safe_float(brain_row.get("queue_wait_seconds") or queue_row.get("queue_wait_seconds"), 0.0),
            "queue_submitted_at_offset_seconds": _safe_float(brain_row.get("queue_submitted_at_offset_seconds") or queue_row.get("queue_submitted_at_offset_seconds"), 0.0),
            "liquidity_quality": str(brain_row.get("liquidity_quality") or queue_row.get("liquidity_quality") or "").strip().lower() or None,
            "execution_engine_status": str(brain_row.get("execution_engine_status") or queue_row.get("execution_engine_status") or "").strip().lower() or None,
            "broker_submission_status": str(brain_row.get("broker_submission_status") or queue_row.get("broker_submission_status") or "").strip().lower() or None,
            "broker_lifecycle_status": str(brain_row.get("broker_lifecycle_status") or queue_row.get("broker_lifecycle_status") or "").strip().lower() or None,
            "execution_final_status": str(brain_row.get("execution_final_status") or queue_row.get("execution_final_status") or "").strip().lower() or None,
            "submitted_to_execution_engine_at": (
                brain_row.get("submitted_to_execution_engine_at")
                or queue_row.get("submitted_to_execution_engine_at")
                or _iso_with_offset(cycle_started_at, brain_row.get("queue_submitted_at_offset_seconds") or queue_row.get("queue_submitted_at_offset_seconds"))
            ),
            "broker_submission_attempted_at": brain_row.get("broker_submission_attempted_at") or queue_row.get("broker_submission_attempted_at"),
            "broker_acknowledged_at": brain_row.get("broker_acknowledged_at") or queue_row.get("broker_acknowledged_at"),
            "broker_last_update_at": brain_row.get("broker_last_update_at") or queue_row.get("broker_last_update_at"),
            "execution_completed_at": brain_row.get("execution_completed_at") or queue_row.get("execution_completed_at"),
            "retry_eligible": bool(brain_row.get("retry_eligible", queue_row.get("retry_eligible", False))),
            "retry_reason": str(brain_row.get("retry_reason") or queue_row.get("retry_reason") or "").strip().lower() or None,
            "retry_attempt_count": _safe_int(brain_row.get("retry_attempt_count") or queue_row.get("retry_attempt_count"), 0),
            "retry_max_attempts": _safe_int(brain_row.get("retry_max_attempts") or queue_row.get("retry_max_attempts"), _safe_int(retry_config.get("retry_max_attempts"), 1)),
            "retry_next_attempt_at": brain_row.get("retry_next_attempt_at") or queue_row.get("retry_next_attempt_at"),
            "backoff_seconds": _safe_float(brain_row.get("backoff_seconds") or queue_row.get("backoff_seconds"), 0.0),
            "backoff_strategy": str(brain_row.get("backoff_strategy") or queue_row.get("backoff_strategy") or "").strip().lower() or ("exponential_jitter" if retry_config.get("retry_jitter_enabled") else "exponential"),
            "retry_exhausted": bool(brain_row.get("retry_exhausted", queue_row.get("retry_exhausted", False))),
            "backoff_active": bool(brain_row.get("backoff_active", queue_row.get("backoff_active", False))),
            "permanent_failure": bool(brain_row.get("permanent_failure", queue_row.get("permanent_failure", False))),
            "reconciliation_started_at": brain_row.get("reconciliation_started_at") or queue_row.get("reconciliation_started_at"),
            "reconciliation_last_polled_at": brain_row.get("reconciliation_last_polled_at") or queue_row.get("reconciliation_last_polled_at"),
            "reconciliation_completed_at": brain_row.get("reconciliation_completed_at") or queue_row.get("reconciliation_completed_at"),
            "reconciliation_poll_count": _safe_int(brain_row.get("reconciliation_poll_count") or queue_row.get("reconciliation_poll_count"), 0),
            "reconciliation_terminal": bool(brain_row.get("reconciliation_terminal", queue_row.get("reconciliation_terminal", False))),
            "reconciliation_window_expired": bool(brain_row.get("reconciliation_window_expired", queue_row.get("reconciliation_window_expired", False))),
            "reconciliation_stop_reason": str(brain_row.get("reconciliation_stop_reason") or queue_row.get("reconciliation_stop_reason") or "").strip().lower() or None,
            "dependency_expected_release_value": _safe_float(brain_row.get("dependency_expected_release_value") or queue_row.get("dependency_expected_release_value"), 0.0),
            "dependency_actual_release_value": _safe_float(brain_row.get("dependency_actual_release_value") or queue_row.get("dependency_actual_release_value"), 0.0),
            "dependency_release_delta": _safe_float(brain_row.get("dependency_release_delta") or queue_row.get("dependency_release_delta"), 0.0),
            "dependency_release_progress_pct": _safe_float(brain_row.get("dependency_release_progress_pct") or queue_row.get("dependency_release_progress_pct"), 0.0),
            "dependency_wait_started_at": brain_row.get("dependency_wait_started_at") or queue_row.get("dependency_wait_started_at"),
            "dependency_resolved_at": brain_row.get("dependency_resolved_at") or queue_row.get("dependency_resolved_at"),
            "dependency_resolution_reason": str(brain_row.get("dependency_resolution_reason") or queue_row.get("dependency_resolution_reason") or "").strip().lower() or None,
            "dependency_final_outcome": str(brain_row.get("dependency_final_outcome") or queue_row.get("dependency_final_outcome") or "").strip().lower() or None,
            "resized_after_execution_result": bool(brain_row.get("resized_after_execution_result", queue_row.get("resized_after_execution_result", False))),
            "original_approved_order_qty": round(_safe_float(brain_row.get("original_approved_order_qty") or queue_row.get("original_approved_order_qty"), _safe_float(brain_row.get("approved_order_qty"), 0.0)), 4),
            "recomputed_approved_order_qty": round(_safe_float(brain_row.get("recomputed_approved_order_qty") or queue_row.get("recomputed_approved_order_qty"), _safe_float(brain_row.get("approved_order_qty"), 0.0)), 4),
            "recomputed_capital_approved_value": round(_safe_float(brain_row.get("recomputed_capital_approved_value") or queue_row.get("recomputed_capital_approved_value"), _safe_float(brain_row.get("capital_approved_value"), 0.0)), 4),
            "recompute_reason": str(brain_row.get("recompute_reason") or queue_row.get("recompute_reason") or "").strip().lower() or None,
            "kronos_ready": bool(brain_row.get("kronos_ready", False)),
            "kronos_score": _safe_float(brain_row.get("kronos_score"), 0.0),
            "kronos_confidence": _safe_float(brain_row.get("kronos_confidence"), 0.0),
            "kronos_premarket_score": _safe_float(brain_row.get("kronos_premarket_score"), 0.0),
            "kronos_opening_score": _safe_float(brain_row.get("kronos_opening_score"), 0.0),
            "kronos_session_preferred_action": str(brain_row.get("kronos_session_preferred_action") or "").strip().upper() or None,
            "kronos_execution_timing_bias": str(brain_row.get("kronos_execution_timing_bias") or "").strip().lower() or None,
            "kronos_wait_reason": str(brain_row.get("kronos_wait_reason") or "").strip().lower() or None,
            "kronos_weight": _safe_float(brain_row.get("kronos_weight"), 0.0),
            "kronos_contribution_to_score": _safe_float(brain_row.get("kronos_contribution_to_score"), 0.0),
            "kronos_contribution_reason": str(brain_row.get("kronos_contribution_reason") or "").strip().lower() or None,
            "kronos_modified_target_position_pct": _safe_float(brain_row.get("kronos_modified_target_position_pct"), _safe_float(brain_row.get("target_position_pct"), 0.0)),
            "kronos_modified_funding_ratio": _safe_float(brain_row.get("kronos_modified_funding_ratio"), _safe_float(brain_row.get("funding_ratio"), 0.0)),
            "kronos_modified_execution_priority": str(brain_row.get("kronos_modified_execution_priority") or "").strip().lower() or None,
            "kronos_expected_volatility": _safe_float(brain_row.get("kronos_expected_volatility"), 0.0),
            "kronos_volatility_risk": str(brain_row.get("kronos_volatility_risk") or "").strip().lower() or None,
            "kronos_warning_flags": brain_row.get("kronos_warning_flags") if isinstance(brain_row.get("kronos_warning_flags"), list) else [],
            "quality_flags": brain_row.get("quality_flags") if isinstance(brain_row.get("quality_flags"), list) else (analysis.get("quality_flags") if isinstance(analysis.get("quality_flags"), list) else []),
            "warning_flags": brain_row.get("warning_flags") if isinstance(brain_row.get("warning_flags"), list) else (analysis.get("warning_flags") if isinstance(analysis.get("warning_flags"), list) else []),
            "has_open_long": current_side == "LONG",
            "has_open_short": current_side == "SHORT",
            "derived_intent": derived_intent,
            "intent_reason": intent_reason,
            "requested_execution_action": requested_execution_action,
            "actual_execution_action": actual_execution_action,
            "decision_outcome_code": str(derived_reason_code or final_outcome_code or "no_action_from_signal").strip().lower(),
            "decision_outcome_detail": intent_reason or final_outcome_detail,
            "guardrail_result": guardrail_result,
            "guardrail_reason_code": guardrail_reason_code,
            "guardrail_reason_detail": guardrail_reason_detail,
            "risk_check_result": risk_check_result,
            "cash_check_result": cash_check_result,
            "margin_check_result": margin_check_result,
            "market_hours_check_result": market_hours_check_result,
            "duplicate_position_check_result": duplicate_check,
            "final_execution_action": final_execution_action,
            "broker_order_submitted": bool(brain_row.get("broker_order_submitted", queue_row.get("broker_order_submitted", broker_enrichment.get("broker_order_submitted")))),
            "broker_order_id": brain_row.get("broker_order_id") or queue_row.get("broker_order_id") or broker_enrichment.get("broker_order_id"),
            "broker_client_order_id": brain_row.get("broker_client_order_id") or queue_row.get("broker_client_order_id") or broker_enrichment.get("broker_client_order_id"),
            "broker_order_status": brain_row.get("broker_order_status") or queue_row.get("broker_order_status") or broker_enrichment.get("broker_order_status"),
            "broker_submission_at": brain_row.get("broker_submission_at") or queue_row.get("broker_submission_at") or broker_enrichment.get("broker_submission_at"),
            "broker_last_status_at": brain_row.get("broker_last_status_at") or queue_row.get("broker_last_status_at") or broker_enrichment.get("broker_last_status_at"),
            "broker_rejection_code": brain_row.get("broker_rejection_code") or queue_row.get("broker_rejection_code") or broker_enrichment.get("broker_rejection_code"),
            "broker_rejection_reason": brain_row.get("broker_rejection_reason") or queue_row.get("broker_rejection_reason") or broker_enrichment.get("broker_rejection_message"),
            "broker_rejection_message": brain_row.get("broker_rejection_message") or queue_row.get("broker_rejection_message") or broker_enrichment.get("broker_rejection_message"),
            "broker_skip_reason": brain_row.get("broker_skip_reason") or queue_row.get("broker_skip_reason") or broker_enrichment.get("broker_skip_reason"),
            "broker_cancelled": bool(brain_row.get("broker_cancelled", queue_row.get("broker_cancelled", broker_enrichment.get("broker_cancelled")))),
            "trade_fill_status": trade_fill_status,
            "filled_qty": round(_safe_float(brain_row.get("filled_qty") or queue_row.get("filled_qty"), _safe_float(broker_enrichment.get("filled_qty"), executed_qty)), 4),
            "average_fill_price": round(_safe_float(brain_row.get("average_fill_price") or queue_row.get("average_fill_price"), _safe_float(broker_enrichment.get("average_fill_price"), executed_price)), 4),
            "executed_qty": round(executed_qty, 4),
            "executed_price": round(executed_price, 4),
            "broker_outcome_code": broker_enrichment.get("broker_outcome_code"),
            "execution_outcome_code": str(broker_enrichment.get("broker_outcome_code") or "broker_not_called").strip().lower(),
            "execution_skip_reason": broker_enrichment.get("broker_skip_reason"),
            "first_fill_at": brain_row.get("first_fill_at") or queue_row.get("first_fill_at"),
            "final_fill_at": brain_row.get("final_fill_at") or queue_row.get("final_fill_at"),
            "why_no_broker_order_code": why_no_broker_order_code,
            "why_no_broker_order_detail": why_no_broker_order_detail,
            "final_outcome_code": final_outcome_code,
            "final_outcome_detail": final_outcome_detail,
            "strategy_mode": strategy_mode,
            "broker_event_timeline": broker_enrichment.get("broker_event_timeline", []),
            "raw_broker_payload": broker_enrichment.get("raw_broker_payload", {}),
            "raw_audit_events": symbol_audit_events,
            "raw_order_events": symbol_order_events,
        }
        row_payload.update(_derive_engine_contribution_fields(row_payload, strategy_mode=strategy_mode))
        execution_state_fields = _derive_execution_state_fields(
            row=row_payload,
            queue_row=queue_row if isinstance(queue_row, dict) else {},
            order_events=symbol_order_events,
            broker_enrichment=broker_enrichment,
            cycle_started_at=cycle_started_at,
            cycle_completed_at=cycle_completed_at,
            retry_config=retry_config,
        )
        row_payload.update(execution_state_fields)
        row_payload = _enforce_cycle_broker_invariants(row_payload)
        autonomous_action, final_decision_reason = _derive_autonomous_action(row_payload)
        row_payload["autonomous_action"] = autonomous_action
        row_payload["final_decision_reason"] = final_decision_reason
        row_payload["hold_reason"] = final_decision_reason if autonomous_action == "HOLD" else None
        row_payload["add_reason"] = final_decision_reason if autonomous_action == "ADD_LONG" else None
        row_payload["reduce_reason"] = final_decision_reason if autonomous_action in {"REDUCE_LONG", "ROTATE_OUT"} else None
        row_payload["exit_reason"] = final_decision_reason if autonomous_action == "EXIT_LONG" else None
        row_payload["capital_preservation_reason"] = (
            str(row_payload.get("capital_competition_reason") or row_payload.get("news_no_trade_reason") or row_payload.get("no_trade_before_open_reason") or "").strip() or None
        ) if autonomous_action in {"NO_ACTION", "WAIT_FOR_CONFIRMATION", "QUEUE_FOR_OPEN"} else None
        row_payload["rotation_candidate"] = bool(str(row_payload.get("replacement_candidate") or row_payload.get("displaced_symbol") or "").strip())
        row_payload["rotation_from_symbol"] = row_payload.get("displaced_symbol") if row_payload.get("replacement_candidate") else None
        row_payload["rotation_to_symbol"] = row_payload.get("replacement_candidate") if row_payload.get("replacement_candidate") else None
        row_payload.update(_build_reward_penalty_profile(row_payload))
        row_payload.update(_build_ai_forecast(row_payload))
        reason_counter.update([str(row_payload.get("final_outcome_code") or "unknown")])
        rows.append(row_payload)

    _apply_dependency_resizing(rows, cycle_completed_at=cycle_completed_at)
    enriched_execution_queue, enriched_execution_timeline, derived_execution_summary = _enrich_execution_queue_and_timeline(
        rows=rows,
        base_queue=brain_execution_queue,
        base_timeline=brain_execution_timeline,
    )
    execution_summary_payload = {
        **(brain_execution_summary if isinstance(brain_execution_summary, dict) else {}),
        **derived_execution_summary,
    }

    summary_counts = summarize_auto_trading_decision_counts(rows)

    return {
        "cycle_id": cycle_id,
        "cycle_started_at": cycle_started_at,
        "cycle_completed_at": cycle_completed_at,
        "runtime_state": runtime_state,
        "delegated": bool(delegated),
        "correlation_id": correlation_id,
        "summary_counts": summary_counts,
        "totals_by_reason_code": dict(reason_counter),
        "retention": diagnostics_retention_policy(),
        "regime": brain_regime,
        "market_judgment": portfolio_brain_payload.get("market_judgment") if isinstance(portfolio_brain_payload.get("market_judgment"), dict) else {},
        "portfolio_sleeves": portfolio_brain_payload.get("portfolio_sleeves") if isinstance(portfolio_brain_payload.get("portfolio_sleeves"), dict) else {},
        "self_governed_limits": portfolio_brain_payload.get("self_governed_limits") if isinstance(portfolio_brain_payload.get("self_governed_limits"), dict) else {},
        "judgment_summary": portfolio_brain_payload.get("judgment_summary") if isinstance(portfolio_brain_payload.get("judgment_summary"), dict) else {},
        "allocation_summary": brain_allocation.get("summary") if isinstance(brain_allocation.get("summary"), dict) else {},
        "allocation_ledger": brain_allocation.get("ledger") if isinstance(brain_allocation.get("ledger"), dict) else {},
        "reconciliation": portfolio_brain_payload.get("reconciliation")
        if isinstance(portfolio_brain_payload.get("reconciliation"), dict)
        else {},
        "self_review": portfolio_brain_payload.get("self_review") if isinstance(portfolio_brain_payload.get("self_review"), dict) else {},
        "market_session": market_session_payload if isinstance(market_session_payload, dict) else {},
        "market_readiness": market_readiness_payload if isinstance(market_readiness_payload, dict) else {},
        "kronos": kronos_cycle_payload if isinstance(kronos_cycle_payload, dict) else {},
        "analysis_engines": {
            "strategy_mode": strategy_mode,
            "classic_used_count": summary_counts.get("classic_used_count", 0),
            "ranking_used_count": summary_counts.get("ranking_used_count", 0),
            "ml_used_count": summary_counts.get("ml_used_count", 0),
            "dl_used_count": summary_counts.get("dl_used_count", 0),
            "kronos_used_count": summary_counts.get("kronos_used_count", 0),
            "dl_fallback_count": summary_counts.get("dl_fallback_count", 0),
            "kronos_fallback_count": summary_counts.get("kronos_fallback_count", 0),
            "symbols_with_dl_contribution": summary_counts.get("symbols_with_dl_contribution", 0),
            "symbols_with_kronos_contribution": summary_counts.get("symbols_with_kronos_contribution", 0),
        },
        "execution_queue_summary": execution_summary_payload,
        "execution_queue": enriched_execution_queue,
        "execution_timeline": enriched_execution_timeline,
        "rows": rows,
        "warnings": [] if rows else ["decision_capture_empty"],
        "partial_capture": not bool(rows),
    }


def summarize_auto_trading_decision_counts(rows: list[dict]) -> dict:
    counts = {
        "signal_buy_count": 0,
        "signal_sell_count": 0,
        "signal_hold_count": 0,
        "derived_open_long_count": 0,
        "derived_add_long_count": 0,
        "derived_reduce_long_count": 0,
        "derived_exit_long_count": 0,
        "derived_hold_count": 0,
        "derived_close_long_count": 0,
        "derived_open_short_count": 0,
        "derived_close_short_count": 0,
        "blocked_count": 0,
        "blocked_existing_position_count": 0,
        "blocked_risk_count": 0,
        "blocked_cash_count": 0,
        "blocked_market_hours_count": 0,
        "submitted_order_count": 0,
        "accepted_order_count": 0,
        "rejected_order_count": 0,
        "filled_order_count": 0,
        "partially_filled_order_count": 0,
        "no_action_count": 0,
        "classic_used_count": 0,
        "ranking_used_count": 0,
        "ml_used_count": 0,
        "dl_used_count": 0,
        "kronos_used_count": 0,
        "dl_fallback_count": 0,
        "kronos_fallback_count": 0,
        "symbols_with_dl_contribution": 0,
        "symbols_with_kronos_contribution": 0,
    }

    for row in rows:
        signal = _normalize_signal(row.get("analysis_signal"))
        if signal == "BUY":
            counts["signal_buy_count"] += 1
        elif signal == "SELL":
            counts["signal_sell_count"] += 1
        else:
            counts["signal_hold_count"] += 1

        derived = str(row.get("derived_intent") or "").upper()
        if "OPEN_LONG" in derived or "ADD_LONG" in derived:
            counts["derived_open_long_count"] += 1
        if "ADD_LONG" in derived:
            counts["derived_add_long_count"] += 1
        if "REDUCE_LONG" in derived:
            counts["derived_reduce_long_count"] += 1
        if "EXIT_LONG" in derived:
            counts["derived_exit_long_count"] += 1
        if derived in {"HOLD", "NONE"}:
            counts["derived_hold_count"] += 1
        if "CLOSE_LONG" in derived:
            counts["derived_close_long_count"] += 1
        if "OPEN_SHORT" in derived:
            counts["derived_open_short_count"] += 1
        if "CLOSE_SHORT" in derived:
            counts["derived_close_short_count"] += 1

        if row.get("classic_signal"):
            counts["classic_used_count"] += 1
        if row.get("ranking_signal"):
            counts["ranking_used_count"] += 1
        if bool(row.get("ml_contributed")):
            counts["ml_used_count"] += 1
        if bool(row.get("dl_contributed")):
            counts["dl_used_count"] += 1
            counts["symbols_with_dl_contribution"] += 1
        if bool(row.get("kronos_contributed")):
            counts["kronos_used_count"] += 1
            counts["symbols_with_kronos_contribution"] += 1
        if bool(row.get("dl_fallback_used")):
            counts["dl_fallback_count"] += 1
        if bool(row.get("kronos_fallback_used")):
            counts["kronos_fallback_count"] += 1

        final_code = str(row.get("final_outcome_code") or "").strip().lower()
        guardrail_code = str(row.get("guardrail_reason_code") or "").strip().lower()
        broker_submitted = bool(row.get("broker_order_submitted"))

        if broker_submitted:
            counts["submitted_order_count"] += 1
            if final_code in {"order_rejected", "broker_rejected"}:
                counts["rejected_order_count"] += 1
            else:
                counts["accepted_order_count"] += 1

        if final_code == "order_filled":
            counts["filled_order_count"] += 1
        if final_code == "order_partially_filled":
            counts["partially_filled_order_count"] += 1

        if final_code in {
            "existing_long_position",
            "existing_short_position",
            "insufficient_cash",
            "insufficient_margin",
            "risk_gate_blocked",
            "market_closed",
            "duplicate_intent_suppressed",
            "order_rejected",
        } or final_code in _NO_BROKER_ADD_LONG_REASON_CODES:
            counts["blocked_count"] += 1

        if final_code in {"existing_long_position", "existing_short_position", "duplicate_intent_suppressed", "existing_long_position_no_add", "at_target_position_size"}:
            counts["blocked_existing_position_count"] += 1

        if final_code in {"risk_gate_blocked", "add_blocked_by_risk"} or guardrail_code in {"risk_gate_blocked", "add_blocked_by_risk"}:
            counts["blocked_risk_count"] += 1

        if final_code in {"insufficient_cash", "insufficient_margin", "add_blocked_by_cash"} or guardrail_code in {"insufficient_cash", "insufficient_margin", "add_blocked_by_cash"}:
            counts["blocked_cash_count"] += 1

        if final_code in {"market_closed", "add_blocked_by_market_hours"}:
            counts["blocked_market_hours_count"] += 1

        if final_code in {
            "no_action_from_signal",
            "existing_long_position",
            "existing_short_position",
            "duplicate_intent_suppressed",
            "broker_not_called",
        } or final_code in _NO_BROKER_ADD_LONG_REASON_CODES:
            counts["no_action_count"] += 1

    counts["symbols_total"] = len(rows)
    return counts


def _default_summary_counts() -> dict:
    return summarize_auto_trading_decision_counts([])


def _summary_counts_from_payloads(decision_payload: dict | None, summary_payload: dict | None) -> dict:
    defaults = _default_summary_counts()
    if isinstance(decision_payload, dict) and isinstance(decision_payload.get("summary_counts"), dict):
        merged = {**defaults, **decision_payload.get("summary_counts", {})}
        merged["symbols_total"] = _safe_int(merged.get("symbols_total"), len(decision_payload.get("rows") or []))
        return merged

    summary = summary_payload if isinstance(summary_payload, dict) else {}
    counts = dict(defaults)
    counts["signal_buy_count"] = _safe_int(summary.get("signal_buy_count"), _safe_int(summary.get("buy_signals"), 0))
    counts["signal_sell_count"] = _safe_int(summary.get("signal_sell_count"), _safe_int(summary.get("sell_signals"), 0))
    counts["signal_hold_count"] = _safe_int(summary.get("signal_hold_count"), _safe_int(summary.get("hold_signals"), 0))

    for key in (
        "derived_open_long_count",
        "derived_add_long_count",
        "derived_close_long_count",
        "derived_open_short_count",
        "derived_close_short_count",
        "blocked_count",
        "blocked_existing_position_count",
        "blocked_risk_count",
        "blocked_cash_count",
        "blocked_market_hours_count",
        "submitted_order_count",
        "accepted_order_count",
        "rejected_order_count",
        "filled_order_count",
        "partially_filled_order_count",
        "no_action_count",
        "classic_used_count",
        "ranking_used_count",
        "ml_used_count",
        "dl_used_count",
        "kronos_used_count",
        "dl_fallback_count",
        "kronos_fallback_count",
        "symbols_with_dl_contribution",
        "symbols_with_kronos_contribution",
    ):
        counts[key] = _safe_int(summary.get(key), counts[key])

    counts["symbols_total"] = _safe_int(summary.get("symbols_scanned"), 0)
    return counts


def _normalize_row_for_response(
    row: dict,
    *,
    include_model_breakdown: bool,
    include_details: bool,
    include_raw: bool,
) -> tuple[dict, set[str], bool]:
    normalized = dict(row)
    omitted_fields: set[str] = set()
    slimmed = False

    if not include_model_breakdown and "model_source_breakdown" in normalized:
        normalized.pop("model_source_breakdown", None)
        omitted_fields.add("model_source_breakdown")
        slimmed = True

    if not include_details:
        for key in ("broker_event_timeline",):
            if key in normalized:
                normalized.pop(key, None)
                omitted_fields.add(key)
                slimmed = True

    if not include_raw:
        for key in _DEFAULT_RAW_FIELDS:
            if key in normalized:
                normalized.pop(key, None)
                omitted_fields.add(key)
                slimmed = True
        for key in ("raw_audit_events", "raw_order_events"):
            if key in normalized:
                normalized.pop(key, None)
                omitted_fields.add(key)
                slimmed = True

    return normalized, omitted_fields, slimmed


def _normalize_cycle_record(
    run_row: AutomationRun,
    decision_payload: dict | None,
    summary_payload: dict | None,
    status_payload: dict | None,
    *,
    include_rows: bool,
    include_details: bool,
    include_model_breakdown: bool,
    include_raw: bool,
    row_symbol: str | None = None,
) -> dict:
    decision = decision_payload if isinstance(decision_payload, dict) else {}
    summary = summary_payload if isinstance(summary_payload, dict) else {}
    status = status_payload if isinstance(status_payload, dict) else {}
    correlation_id = decision.get("correlation_id") or summary.get("correlation_id")

    rows = decision.get("rows") if isinstance(decision.get("rows"), list) else []
    requested_symbol = _normalize_symbol(row_symbol) if row_symbol else ""

    candidate_rows = rows
    truncated = False
    if requested_symbol:
        candidate_rows = [
            row
            for row in rows
            if isinstance(row, dict) and _normalize_symbol(row.get("symbol")) == requested_symbol
        ]
        truncated = len(candidate_rows) < len(rows)

    normalized_rows: list[dict] = []
    omitted_fields_set: set[str] = set()
    any_slimmed = False
    order_event_map = _collect_order_events_by_symbol(str(correlation_id)) if include_rows else {}
    if include_rows:
        for row in candidate_rows:
            if not isinstance(row, dict):
                continue
            normalized_row = dict(row)
            normalized_row["cycle_id"] = run_row.run_id
            if not normalized_row.get("cycle_started_at") and run_row.started_at:
                normalized_row["cycle_started_at"] = run_row.started_at.isoformat()
            if not normalized_row.get("cycle_completed_at") and run_row.completed_at:
                normalized_row["cycle_completed_at"] = run_row.completed_at.isoformat()

            symbol = _normalize_symbol(normalized_row.get("symbol"))
            broker_enrichment = _build_broker_timeline(
                order_event_map.get(symbol, []),
                include_details=include_details,
            )
            if "broker_client_order_id" not in normalized_row:
                normalized_row["broker_client_order_id"] = broker_enrichment.get("broker_client_order_id")
            if "broker_submission_at" not in normalized_row:
                normalized_row["broker_submission_at"] = broker_enrichment.get("broker_submission_at")
            if "broker_last_status_at" not in normalized_row:
                normalized_row["broker_last_status_at"] = broker_enrichment.get("broker_last_status_at")
            if "broker_rejection_code" not in normalized_row:
                normalized_row["broker_rejection_code"] = broker_enrichment.get("broker_rejection_code")
            if "broker_rejection_message" not in normalized_row:
                normalized_row["broker_rejection_message"] = (
                    normalized_row.get("broker_rejection_reason")
                    or broker_enrichment.get("broker_rejection_message")
                )
            if "broker_skip_reason" not in normalized_row:
                normalized_row["broker_skip_reason"] = broker_enrichment.get("broker_skip_reason")
            if "broker_cancelled" not in normalized_row:
                normalized_row["broker_cancelled"] = bool(broker_enrichment.get("broker_cancelled"))
            if "filled_qty" not in normalized_row:
                normalized_row["filled_qty"] = round(
                    _safe_float(
                        broker_enrichment.get("filled_qty"),
                        normalized_row.get("executed_qty"),
                    ),
                    4,
                )
            if "average_fill_price" not in normalized_row:
                normalized_row["average_fill_price"] = round(
                    _safe_float(
                        broker_enrichment.get("average_fill_price"),
                        normalized_row.get("executed_price"),
                    ),
                    4,
                )
            if "broker_outcome_code" not in normalized_row:
                normalized_row["broker_outcome_code"] = broker_enrichment.get("broker_outcome_code")
            if "execution_outcome_code" not in normalized_row:
                normalized_row["execution_outcome_code"] = broker_enrichment.get("broker_outcome_code")
            if "execution_skip_reason" not in normalized_row:
                normalized_row["execution_skip_reason"] = broker_enrichment.get("broker_skip_reason")
            if "broker_event_timeline" not in normalized_row:
                normalized_row["broker_event_timeline"] = broker_enrichment.get("broker_event_timeline", [])
            if "raw_order_events" not in normalized_row:
                normalized_row["raw_order_events"] = order_event_map.get(symbol, [])
            if "raw_broker_payload" not in normalized_row:
                normalized_row["raw_broker_payload"] = broker_enrichment.get("raw_broker_payload", {})
            if "requested_execution_action" not in normalized_row:
                derived = str(normalized_row.get("derived_intent") or "").strip().upper()
                normalized_row["requested_execution_action"] = derived if derived and derived != "NONE" else None
            if "actual_execution_action" not in normalized_row:
                action = str(normalized_row.get("final_execution_action") or "").strip().upper()
                normalized_row["actual_execution_action"] = action if action and action != "NONE" else None
            normalized_row.update(_derive_engine_contribution_fields(normalized_row, strategy_mode=str(normalized_row.get("strategy_mode") or "")))
            if "decision_outcome_code" not in normalized_row:
                normalized_row["decision_outcome_code"] = str(
                    normalized_row.get("final_outcome_code") or "no_action_from_signal"
                ).strip().lower()
            if "decision_outcome_detail" not in normalized_row:
                normalized_row["decision_outcome_detail"] = str(
                    normalized_row.get("final_outcome_detail")
                    or normalized_row.get("intent_reason")
                    or ""
                ).strip() or None

            normalized_row = _enforce_cycle_broker_invariants(normalized_row)

            compact_row, omitted, slimmed = _normalize_row_for_response(
                normalized_row,
                include_model_breakdown=include_model_breakdown,
                include_details=include_details,
                include_raw=include_raw,
            )
            normalized_rows.append(compact_row)
            omitted_fields_set.update(omitted)
            any_slimmed = any_slimmed or slimmed

    totals_by_reason_code = decision.get("totals_by_reason_code") if isinstance(decision.get("totals_by_reason_code"), dict) else {}
    if not totals_by_reason_code and rows:
        reason_counter: Counter[str] = Counter()
        for row in rows:
            if isinstance(row, dict):
                reason_counter.update([str(row.get("final_outcome_code") or "unknown")])
        totals_by_reason_code = dict(reason_counter)

    summary_counts = summarize_auto_trading_decision_counts(normalized_rows) if normalized_rows else _summary_counts_from_payloads(decision, summary)
    runtime_state = str(decision.get("runtime_state") or status.get("runtime_state") or "unknown")
    delegated = bool(decision.get("delegated") if "delegated" in decision else status.get("delegated", False))
    market_readiness_payload = decision.get("market_readiness") if isinstance(decision.get("market_readiness"), dict) else {}
    market_judgment_payload = (
        decision.get("market_judgment")
        if isinstance(decision.get("market_judgment"), dict)
        else (market_readiness_payload.get("market_judgment") if isinstance(market_readiness_payload.get("market_judgment"), dict) else {})
    )
    portfolio_sleeves_payload = (
        decision.get("portfolio_sleeves")
        if isinstance(decision.get("portfolio_sleeves"), dict)
        else (market_readiness_payload.get("portfolio_sleeves") if isinstance(market_readiness_payload.get("portfolio_sleeves"), dict) else {})
    )
    self_governed_limits_payload = (
        decision.get("self_governed_limits")
        if isinstance(decision.get("self_governed_limits"), dict)
        else (market_readiness_payload.get("self_governed_limits") if isinstance(market_readiness_payload.get("self_governed_limits"), dict) else {})
    )
    judgment_summary_payload = (
        decision.get("judgment_summary")
        if isinstance(decision.get("judgment_summary"), dict)
        else (market_readiness_payload.get("judgment_summary") if isinstance(market_readiness_payload.get("judgment_summary"), dict) else {})
    )
    desk_brief_payload = (
        decision.get("desk_brief")
        if isinstance(decision.get("desk_brief"), dict)
        else (market_readiness_payload.get("desk_brief") if isinstance(market_readiness_payload.get("desk_brief"), dict) else {})
    )

    cycle_payload = {
        "cycle_id": run_row.run_id,
        "run_id": run_row.run_id,
        "job_name": run_row.job_name,
        "status": run_row.status,
        "cycle_started_at": run_row.started_at.isoformat() if run_row.started_at else None,
        "cycle_completed_at": run_row.completed_at.isoformat() if run_row.completed_at else None,
        "duration_seconds": run_row.duration_seconds,
        "runtime_state": runtime_state,
        "delegated": delegated,
        "correlation_id": decision.get("correlation_id") or summary.get("correlation_id"),
        "summary_counts": summary_counts,
        "totals_by_reason_code": totals_by_reason_code,
        "regime": decision.get("regime") if isinstance(decision.get("regime"), dict) else {},
        "market_judgment": market_judgment_payload,
        "portfolio_sleeves": portfolio_sleeves_payload,
        "self_governed_limits": self_governed_limits_payload,
        "judgment_summary": judgment_summary_payload,
        "allocation_summary": decision.get("allocation_summary") if isinstance(decision.get("allocation_summary"), dict) else {},
        "allocation_ledger": decision.get("allocation_ledger") if isinstance(decision.get("allocation_ledger"), dict) else {},
        "self_review": decision.get("self_review") if isinstance(decision.get("self_review"), dict) else {},
        "reconciliation": decision.get("reconciliation") if isinstance(decision.get("reconciliation"), dict) else {},
        "market_session": decision.get("market_session") if isinstance(decision.get("market_session"), dict) else {},
        "market_readiness": market_readiness_payload,
        "desk_brief": desk_brief_payload,
        "kronos": decision.get("kronos") if isinstance(decision.get("kronos"), dict) else {},
        "analysis_engines": decision.get("analysis_engines") if isinstance(decision.get("analysis_engines"), dict) else {},
        "execution_queue_summary": decision.get("execution_queue_summary") if isinstance(decision.get("execution_queue_summary"), dict) else {},
        "execution_queue": decision.get("execution_queue") if isinstance(decision.get("execution_queue"), list) else [],
        "execution_timeline": decision.get("execution_timeline") if isinstance(decision.get("execution_timeline"), list) else [],
        "retention": decision.get("retention") if isinstance(decision.get("retention"), dict) else diagnostics_retention_policy(),
        "warnings": decision.get("warnings") if isinstance(decision.get("warnings"), list) else [],
        "partial_capture": bool(decision.get("partial_capture", not bool(rows))),
        "rows": normalized_rows,
        "rows_count": len(rows),
        "summary": summary,
        "status_payload": status,
        "response_meta": {
            "slimmed": bool(any_slimmed),
            "omitted_fields": sorted(omitted_fields_set),
            "row_count": len(normalized_rows),
            "total_rows": len(rows),
            "truncated": bool(truncated),
            "row_symbol": requested_symbol or None,
            "include_details": bool(include_details),
            "include_model_breakdown": bool(include_model_breakdown),
            "include_raw": bool(include_raw),
        },
    }

    if not cycle_payload["warnings"] and not rows:
        cycle_payload["warnings"] = ["decision_capture_missing"]

    return cycle_payload


def list_auto_trading_cycle_diagnostics(
    limit: int = 20,
    *,
    include_rows: bool = False,
    include_details: bool = False,
    include_model_breakdown: bool = False,
    include_raw: bool = False,
    row_symbol: str | None = None,
) -> dict:
    resolved_limit = max(1, min(_safe_int(limit, 20), 100))

    with session_scope() as session:
        runs = (
            session.query(AutomationRun)
            .filter(AutomationRun.job_name == _DIAGNOSTICS_JOB_NAME)
            .order_by(AutomationRun.started_at.desc())
            .limit(resolved_limit)
            .all()
        )
        run_ids = [row.run_id for row in runs if row.run_id]

        artifacts_by_run: dict[str, dict[str, dict]] = {run_id: {} for run_id in run_ids}
        if run_ids:
            artifacts = (
                session.query(AutomationArtifact)
                .filter(
                    AutomationArtifact.job_name == _DIAGNOSTICS_JOB_NAME,
                    AutomationArtifact.run_id.in_(run_ids),
                    AutomationArtifact.artifact_type.in_(
                        [
                            _DIAGNOSTICS_ARTIFACT_TYPE,
                            "auto_trading_summary",
                            "auto_trading_status",
                        ]
                    ),
                )
                .order_by(AutomationArtifact.created_at.desc())
                .all()
            )
            for artifact in artifacts:
                bucket = artifacts_by_run.setdefault(artifact.run_id, {})
                if artifact.artifact_type in bucket:
                    continue
                bucket[artifact.artifact_type] = loads_json(artifact.payload_json)

    cycles = [
        _normalize_cycle_record(
            run,
            artifacts_by_run.get(run.run_id, {}).get(_DIAGNOSTICS_ARTIFACT_TYPE),
            artifacts_by_run.get(run.run_id, {}).get("auto_trading_summary"),
            artifacts_by_run.get(run.run_id, {}).get("auto_trading_status"),
            include_rows=include_rows,
            include_details=include_details,
            include_model_breakdown=include_model_breakdown,
            include_raw=include_raw,
            row_symbol=row_symbol,
        )
        for run in runs
    ]

    return {
        "items": cycles,
        "limit": resolved_limit,
        "count": len(cycles),
        "retention": diagnostics_retention_policy(),
        "response_meta": {
            "slimmed": not (include_model_breakdown and include_details and include_raw),
            "omitted_fields": sorted(set(_DEFAULT_HEAVY_FIELDS + _DEFAULT_RAW_FIELDS)),
        },
    }


def get_latest_auto_trading_cycle_diagnostics(
    *,
    include_details: bool = False,
    include_model_breakdown: bool = False,
    include_raw: bool = False,
    row_symbol: str | None = None,
    latest_nonempty: bool = False,
) -> dict | None:
    resolved_limit = 25 if latest_nonempty else 1
    payload = list_auto_trading_cycle_diagnostics(
        limit=resolved_limit,
        include_rows=True,
        include_details=include_details,
        include_model_breakdown=include_model_breakdown,
        include_raw=include_raw,
        row_symbol=row_symbol,
    )
    items = payload.get("items") if isinstance(payload, dict) else []
    if not items:
        return None
    selected_index = 0
    if latest_nonempty:
        for idx, item in enumerate(items):
            if _safe_int(item.get("rows_count"), 0) > 0:
                selected_index = idx
                break

    selected = dict(items[selected_index])
    meta = dict(selected.get("response_meta") or {})
    meta["latest_nonempty_requested"] = bool(latest_nonempty)
    meta["latest_nonempty_scanned"] = len(items)
    meta["latest_nonempty_selected_offset"] = selected_index
    meta["latest_nonempty_applied"] = bool(latest_nonempty and selected_index > 0)
    meta["latest_nonempty_found"] = bool(_safe_int(selected.get("rows_count"), 0) > 0)
    selected["response_meta"] = meta
    return selected


def get_auto_trading_cycle_diagnostics(
    cycle_id: str,
    *,
    include_details: bool = False,
    include_model_breakdown: bool = False,
    include_raw: bool = False,
    row_symbol: str | None = None,
) -> dict | None:
    normalized_cycle_id = str(cycle_id or "").strip()
    if not normalized_cycle_id:
        return None

    with session_scope() as session:
        run = (
            session.query(AutomationRun)
            .filter(
                AutomationRun.job_name == _DIAGNOSTICS_JOB_NAME,
                AutomationRun.run_id == normalized_cycle_id,
            )
            .first()
        )
        if run is None:
            return None

        artifacts = (
            session.query(AutomationArtifact)
            .filter(
                AutomationArtifact.job_name == _DIAGNOSTICS_JOB_NAME,
                AutomationArtifact.run_id == normalized_cycle_id,
                AutomationArtifact.artifact_type.in_(
                    [
                        _DIAGNOSTICS_ARTIFACT_TYPE,
                        "auto_trading_summary",
                        "auto_trading_status",
                    ]
                ),
            )
            .order_by(AutomationArtifact.created_at.desc())
            .all()
        )

    artifact_map: dict[str, dict] = {}
    for artifact in artifacts:
        if artifact.artifact_type in artifact_map:
            continue
        artifact_map[artifact.artifact_type] = loads_json(artifact.payload_json)

    return _normalize_cycle_record(
        run,
        artifact_map.get(_DIAGNOSTICS_ARTIFACT_TYPE),
        artifact_map.get("auto_trading_summary"),
        artifact_map.get("auto_trading_status"),
        include_rows=True,
        include_details=include_details,
        include_model_breakdown=include_model_breakdown,
        include_raw=include_raw,
        row_symbol=row_symbol,
    )


def export_auto_trading_cycle_rows_csv(cycle_payload: dict) -> str:
    rows = cycle_payload.get("rows") if isinstance(cycle_payload, dict) else []
    if not isinstance(rows, list):
        rows = []

    fieldnames = [
        "cycle_id",
        "cycle_started_at",
        "cycle_completed_at",
        "runtime_state",
        "delegated",
        "symbol",
        "analysis_signal",
        "analysis_score",
        "confidence",
        "current_position_side",
        "current_position_qty",
        "current_position_avg_price",
        "current_position_value",
        "current_position_pct",
        "target_position_value",
        "target_position_pct",
        "addable_value",
        "proposed_add_qty",
        "add_block_reason",
        "has_open_long",
        "has_open_short",
        "derived_intent",
        "intent_reason",
        "requested_execution_action",
        "actual_execution_action",
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
        "reconciliation_started_at",
        "reconciliation_last_polled_at",
        "reconciliation_completed_at",
        "reconciliation_poll_count",
        "reconciliation_terminal",
        "reconciliation_window_expired",
        "reconciliation_stop_reason",
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
        "execution_priority_band",
        "funded",
        "funded_partially",
        "partial_funding_applied",
        "funding_status",
        "funding_decision",
        "funding_ratio",
        "partial_funding_reason",
        "capital_requested_value",
        "capital_approved_value",
        "remaining_unfunded_value",
        "requested_order_qty",
        "approved_order_qty",
        "original_approved_order_qty",
        "recomputed_approved_order_qty",
        "recomputed_capital_approved_value",
        "recompute_reason",
        "approved_position_pct",
        "decision_outcome_code",
        "decision_outcome_detail",
        "guardrail_result",
        "guardrail_reason_code",
        "guardrail_reason_detail",
        "risk_check_result",
        "cash_check_result",
        "margin_check_result",
        "market_hours_check_result",
        "duplicate_position_check_result",
        "dependency_expected_release_value",
        "dependency_actual_release_value",
        "dependency_release_delta",
        "dependency_release_progress_pct",
        "dependency_wait_started_at",
        "dependency_resolved_at",
        "dependency_resolution_reason",
        "dependency_final_outcome",
        "resized_after_execution_result",
        "final_execution_action",
        "broker_order_submitted",
        "broker_order_id",
        "broker_client_order_id",
        "broker_order_status",
        "broker_submission_at",
        "broker_last_status_at",
        "broker_rejection_code",
        "broker_rejection_reason",
        "broker_skip_reason",
        "trade_fill_status",
        "filled_qty",
        "average_fill_price",
        "executed_qty",
        "executed_price",
        "execution_outcome_code",
        "execution_skip_reason",
        "final_outcome_code",
        "final_outcome_detail",
        "why_no_broker_order_code",
        "why_no_broker_order_detail",
    ]

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row if isinstance(row, dict) else {})

    return buffer.getvalue()
