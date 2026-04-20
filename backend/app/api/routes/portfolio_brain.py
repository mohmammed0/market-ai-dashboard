from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.services.analysis_engines import get_analysis_engines_status
from backend.app.services.auto_trading_diagnostics import (
    get_auto_trading_cycle_diagnostics,
    get_latest_auto_trading_cycle_diagnostics,
    list_auto_trading_cycle_diagnostics,
)


router = APIRouter(prefix="/portfolio-brain", tags=["portfolio-brain"])


_DECISION_FIELDS = [
    "symbol",
    "security_name",
    "market_cap",
    "market_cap_bucket",
    "listed_exchange",
    "us_equity_eligible",
    "is_etf",
    "analysis_signal",
    "analysis_score",
    "confidence",
    "opportunity_score",
    "stock_quality_score",
    "technical_score",
    "ranking_score",
    "multi_timeframe_score",
    "relative_strength_score",
    "sector_strength_score",
    "gap_pct",
    "gap_type",
    "gap_quality_score",
    "volatility_risk",
    "volatility_risk_score",
    "spread_risk",
    "spread_risk_score",
    "liquidity_score",
    "volume_ratio",
    "opening_score",
    "premarket_score",
    "open_confirmation_score",
    "breakout_quality_score",
    "pullback_quality_score",
    "continuation_score",
    "fade_risk",
    "add_quality_score",
    "reduce_pressure_score",
    "exit_pressure_score",
    "news_relevance_score",
    "news_sentiment_score",
    "news_strength_score",
    "catalyst_type",
    "catalyst_horizon",
    "catalyst_scope",
    "catalyst_alignment_with_price",
    "news_confidence",
    "news_warning_flags",
    "news_action_bias",
    "news_supports_entry",
    "news_supports_add",
    "news_supports_reduce",
    "news_supports_exit",
    "news_requires_wait",
    "news_no_trade_reason",
    "news_contribution_to_score",
    "market_context_contribution_to_score",
    "judgment_size_multiplier",
    "conviction_tier",
    "setup_type",
    "expected_direction",
    "preferred_action_candidate",
    "preferred_holding_horizon",
    "risk_reward_estimate",
    "session_adjusted_opportunity_score",
    "engine_conflicts_present",
    "engine_conflict_reason",
    "engine_alignment_score",
    "session_state",
    "session_preferred_action",
    "session_order_plan",
    "order_session_type",
    "session_order_style_preference",
    "session_time_in_force_preference",
    "order_session_route",
    "extended_hours_eligible",
    "queued_for_open",
    "opening_auction_candidate",
    "premarket_live_candidate",
    "submit_before_open",
    "submit_after_open",
    "wait_for_open_confirmation",
    "autonomous_action",
    "session_reason",
    "premarket_submit_reason",
    "queued_for_open_reason",
    "wait_for_open_reason",
    "no_trade_before_open_reason",
    "premarket_submission_allowed",
    "premarket_submission_block_reason",
    "session_queue_type",
    "queue_activation_time",
    "queue_expiration_time",
    "waiting_for_market_open",
    "waiting_for_open_revalidation",
    "session_go_no_go",
    "session_gate_result",
    "session_queue_reason",
    "kronos_ready",
    "kronos_score",
    "kronos_confidence",
    "kronos_premarket_score",
    "kronos_opening_score",
    "kronos_session_preferred_action",
    "kronos_execution_timing_bias",
    "kronos_wait_reason",
    "kronos_weight",
    "kronos_contribution_to_score",
    "kronos_contribution_reason",
    "kronos_modified_target_position_pct",
    "kronos_modified_funding_ratio",
    "kronos_modified_execution_priority",
    "kronos_expected_volatility",
    "kronos_volatility_risk",
    "portfolio_priority_rank",
    "current_position_pct",
    "target_position_pct",
    "desired_delta_pct",
    "planned_execution_action",
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
    "decision_outcome_code",
    "decision_outcome_detail",
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
    "capital_reserved_value",
    "available_cash_before",
    "available_cash_after",
    "regime_adjusted_budget",
    "capital_competition_reason",
    "better_use_of_capital_reason",
    "replacement_candidate",
    "displaced_symbol",
    "rotation_candidate",
    "rotation_from_symbol",
    "rotation_to_symbol",
    "hold_reason",
    "add_reason",
    "reduce_reason",
    "exit_reason",
    "capital_preservation_reason",
    "final_decision_reason",
    "portfolio_slot_consumed",
    "portfolio_slot_available",
    "execution_priority_band",
    "execution_priority",
    "order_style_preference",
    "session_quality",
    "estimated_slippage_risk",
    "broker_order_submitted",
    "execution_outcome_code",
    "execution_skip_reason",
    "final_outcome_code",
    "final_outcome_detail",
    "queue_item_id",
    "execution_stage",
    "queue_rank",
    "queue_reason",
    "queue_status",
    "queue_gate_result",
    "queue_gate_reason",
    "execution_go_no_go",
    "defer_reason",
    "blocking_reason",
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
    "resized_after_capital_release",
    "resized_after_execution_result",
    "funding_recomputed",
    "submission_order",
    "queue_wait_seconds",
    "queue_submitted_at_offset_seconds",
    "liquidity_quality",
    "classic_signal",
    "ranking_signal",
    "ml_enabled",
    "ml_ready",
    "ml_signal",
    "ml_confidence",
    "ml_model_resolution",
    "ml_contributed",
    "ml_contribution_to_score",
    "ml_reason_not_used",
    "dl_enabled",
    "dl_ready",
    "dl_signal",
    "dl_confidence",
    "dl_model_resolution",
    "dl_contributed",
    "dl_contribution_to_score",
    "dl_reason_not_used",
    "kronos_contributed",
    "kronos_reason_not_used",
    "kronos_fallback_used",
    "ensemble_components_available",
    "ensemble_components_used",
    "ensemble_components_skipped",
    "tactical_small_cap_candidate",
    "tactical_small_cap_score",
    "tactical_small_cap_allowed",
    "small_cap_liquidity_quality",
    "small_cap_spread_risk",
    "small_cap_catalyst_quality",
    "small_cap_position_size_multiplier",
    "small_cap_no_trade_reason",
    "trade_review_completed",
    "trade_quality_score",
    "timing_quality_score",
    "sizing_quality_score",
    "execution_quality_score",
    "capital_use_quality_score",
    "better_alternative_existed",
    "better_alternative_symbol",
    "trade_review_reward",
    "trade_review_penalty",
    "trade_review_summary",
    "lesson_learned",
    "behavior_adjustment_hint",
    "reward_score",
    "penalty_score",
    "reward_components",
    "penalty_components",
    "behavior_update_applied",
    "strategy_confidence_adjustment",
    "sleeve_bias_adjustment",
    "engine_weight_adjustment",
    "ai_forecast_available",
    "ai_forecast_reason",
    "ai_current_price",
    "ai_base_scenario_price",
    "ai_bullish_scenario_price",
    "ai_bearish_scenario_price",
    "ai_expected_range_low",
    "ai_expected_range_high",
    "ai_forecast_horizon",
    "ai_forecast_confidence",
    "ai_forecast_risk_level",
    "ai_support_zone_low",
    "ai_invalidation_zone_low",
    "ai_upside_target_zone_low",
    "ai_upside_target_zone_high",
    "ai_downside_risk_zone_low",
    "ai_downside_risk_zone_high",
    "ai_engine_contribution_chart",
    "ai_previous_forecast_vs_actual",
]


def _project_row(row: dict) -> dict:
    payload = {key: row.get(key) for key in _DECISION_FIELDS}
    payload["reason_code"] = (
        row.get("decision_outcome_code")
        or row.get("final_outcome_code")
        or row.get("why_no_broker_order_code")
    )
    payload["reason_detail"] = (
        row.get("decision_outcome_detail")
        or row.get("final_outcome_detail")
        or row.get("why_no_broker_order_detail")
    )
    return payload


def _cycle_to_brain_payload(cycle: dict | None, *, include_rows: bool) -> dict | None:
    if not isinstance(cycle, dict):
        return None

    rows = cycle.get("rows") if isinstance(cycle.get("rows"), list) else []
    decisions = [_project_row(row) for row in rows if isinstance(row, dict)] if include_rows else []
    market_readiness = cycle.get("market_readiness") if isinstance(cycle.get("market_readiness"), dict) else {}
    market_judgment = cycle.get("market_judgment") if isinstance(cycle.get("market_judgment"), dict) else {}
    portfolio_sleeves = cycle.get("portfolio_sleeves") if isinstance(cycle.get("portfolio_sleeves"), dict) else {}
    self_governed_limits = cycle.get("self_governed_limits") if isinstance(cycle.get("self_governed_limits"), dict) else {}
    judgment_summary = cycle.get("judgment_summary") if isinstance(cycle.get("judgment_summary"), dict) else {}
    desk_brief = cycle.get("desk_brief") if isinstance(cycle.get("desk_brief"), dict) else {}

    if not market_judgment and isinstance(market_readiness.get("market_judgment"), dict):
        market_judgment = market_readiness.get("market_judgment") or {}
    if not portfolio_sleeves and isinstance(market_readiness.get("portfolio_sleeves"), dict):
        portfolio_sleeves = market_readiness.get("portfolio_sleeves") or {}
    if not self_governed_limits and isinstance(market_readiness.get("self_governed_limits"), dict):
        self_governed_limits = market_readiness.get("self_governed_limits") or {}
    if not judgment_summary and isinstance(market_readiness.get("judgment_summary"), dict):
        judgment_summary = market_readiness.get("judgment_summary") or {}
    if not desk_brief and isinstance(market_readiness.get("desk_brief"), dict):
        desk_brief = market_readiness.get("desk_brief") or {}

    return {
        "cycle_id": cycle.get("cycle_id"),
        "cycle_started_at": cycle.get("cycle_started_at"),
        "cycle_completed_at": cycle.get("cycle_completed_at"),
        "runtime_state": cycle.get("runtime_state"),
        "delegated": bool(cycle.get("delegated", False)),
        "rows_count": cycle.get("rows_count", len(rows)),
        "regime": cycle.get("regime") if isinstance(cycle.get("regime"), dict) else {},
        "market_judgment": market_judgment,
        "portfolio_sleeves": portfolio_sleeves,
        "self_governed_limits": self_governed_limits,
        "judgment_summary": judgment_summary,
        "market_session": cycle.get("market_session") if isinstance(cycle.get("market_session"), dict) else {},
        "market_readiness": market_readiness,
        "desk_brief": desk_brief,
        "kronos": cycle.get("kronos") if isinstance(cycle.get("kronos"), dict) else {},
        "analysis_engines": cycle.get("analysis_engines") if isinstance(cycle.get("analysis_engines"), dict) else {},
        "allocation_summary": cycle.get("allocation_summary") if isinstance(cycle.get("allocation_summary"), dict) else {},
        "allocation_ledger": cycle.get("allocation_ledger") if isinstance(cycle.get("allocation_ledger"), dict) else {},
        "self_review": cycle.get("self_review") if isinstance(cycle.get("self_review"), dict) else {},
        "reconciliation": cycle.get("reconciliation") if isinstance(cycle.get("reconciliation"), dict) else {},
        "execution_queue_summary": cycle.get("execution_queue_summary") if isinstance(cycle.get("execution_queue_summary"), dict) else {},
        "execution_queue": cycle.get("execution_queue") if isinstance(cycle.get("execution_queue"), list) else [],
        "execution_timeline": cycle.get("execution_timeline") if isinstance(cycle.get("execution_timeline"), list) else [],
        "summary_counts": cycle.get("summary_counts") if isinstance(cycle.get("summary_counts"), dict) else {},
        "totals_by_reason_code": cycle.get("totals_by_reason_code") if isinstance(cycle.get("totals_by_reason_code"), dict) else {},
        "response_meta": cycle.get("response_meta") if isinstance(cycle.get("response_meta"), dict) else {},
        "rows": decisions,
        "decisions": decisions,
        "decisions_count": len(decisions) if include_rows else None,
    }


@router.get("/status")
def portfolio_brain_status(latest_nonempty: bool = Query(default=True)):
    latest = get_latest_auto_trading_cycle_diagnostics(
        include_details=False,
        include_model_breakdown=False,
        include_raw=False,
        latest_nonempty=latest_nonempty,
    )
    if latest is None:
        return {
            "status": "empty",
            "brain_ready": False,
            "detail": "No portfolio-brain cycle data available yet.",
            "item": None,
        }

    regime = latest.get("regime") if isinstance(latest.get("regime"), dict) else {}
    allocation = latest.get("allocation_summary") if isinstance(latest.get("allocation_summary"), dict) else {}
    ledger = latest.get("allocation_ledger") if isinstance(latest.get("allocation_ledger"), dict) else {}
    queue_summary = latest.get("execution_queue_summary") if isinstance(latest.get("execution_queue_summary"), dict) else {}
    analysis_engines = get_analysis_engines_status(latest_cycle=latest, latest_nonempty=latest_nonempty)
    return {
        "status": "ok",
        "brain_ready": bool(regime),
        "latest_cycle_id": latest.get("cycle_id"),
        "runtime_state": latest.get("runtime_state"),
        "delegated": bool(latest.get("delegated", False)),
        "analysis_engines": analysis_engines,
        "regime": {
            "regime_code": regime.get("regime_code"),
            "regime_bias": regime.get("regime_bias"),
            "regime_confidence": regime.get("regime_confidence"),
            "risk_multiplier": regime.get("risk_multiplier"),
            "max_new_positions": regime.get("max_new_positions"),
        },
        "session": latest.get("market_session") if isinstance(latest.get("market_session"), dict) else {},
        "market_judgment": latest.get("market_judgment") if isinstance(latest.get("market_judgment"), dict) else {},
        "portfolio_sleeves": latest.get("portfolio_sleeves") if isinstance(latest.get("portfolio_sleeves"), dict) else {},
        "self_governed_limits": latest.get("self_governed_limits") if isinstance(latest.get("self_governed_limits"), dict) else {},
        "kronos": latest.get("kronos") if isinstance(latest.get("kronos"), dict) else {},
        "allocation": {
            "symbols_considered": allocation.get("symbols_considered"),
            "funded_count": allocation.get("funded_count"),
            "funded_full_count": allocation.get("funded_full_count"),
            "funded_partial_count": allocation.get("funded_partial_count"),
            "partial_capital_total": allocation.get("partial_capital_total") or ledger.get("partial_capital_total"),
            "capital_left_unallocated": allocation.get("capital_left_unallocated") or ((allocation.get("capital") or {}).get("capital_left_unallocated") if isinstance(allocation.get("capital"), dict) else None),
            "execution_priority_band_counts": ledger.get("execution_priority_band_counts") if isinstance(ledger.get("execution_priority_band_counts"), dict) else {},
            "unfunded_count": ledger.get("unfunded_total"),
            "cash_used_for_allocations": ((allocation.get("capital") or {}).get("cash_used_for_allocations") if isinstance(allocation.get("capital"), dict) else None),
            "cash_remaining": ((allocation.get("capital") or {}).get("cash_remaining") if isinstance(allocation.get("capital"), dict) else None),
            "regime_adjusted_budget": ((allocation.get("capital") or {}).get("regime_adjusted_budget") if isinstance(allocation.get("capital"), dict) else None),
            "portfolio_slot_consumed": ledger.get("portfolio_slot_consumed"),
            "portfolio_slot_available": ledger.get("portfolio_slot_available"),
            "top_capital_competition_reasons": ledger.get("top_capital_competition_reasons") if isinstance(ledger.get("top_capital_competition_reasons"), dict) else {},
            "queue_total": queue_summary.get("queue_total"),
            "queue_submitted_count": queue_summary.get("submitted_count"),
            "queue_waiting_count": queue_summary.get("waiting_count"),
            "queue_deferred_count": queue_summary.get("deferred_count"),
            "queue_skipped_count": queue_summary.get("skipped_count"),
            "queue_gating_reason_counts": queue_summary.get("gating_reason_counts") if isinstance(queue_summary.get("gating_reason_counts"), dict) else {},
            "reconciliation_started_count": queue_summary.get("reconciliation_started_count"),
            "reconciliation_completed_count": queue_summary.get("reconciliation_completed_count"),
            "reconciliation_active_count": queue_summary.get("reconciliation_active_count"),
            "reconciliation_terminal_count": queue_summary.get("reconciliation_terminal_count"),
            "reconciliation_window_expired_count": queue_summary.get("reconciliation_window_expired_count"),
            "reconciliation_poll_count_total": queue_summary.get("reconciliation_poll_count_total"),
        },
    }


@router.get("/latest")
def portfolio_brain_latest(
    include_rows: bool = Query(default=True),
    include_details: bool = Query(default=False),
    latest_nonempty: bool = Query(default=True),
):
    latest = get_latest_auto_trading_cycle_diagnostics(
        include_details=include_details,
        include_model_breakdown=False,
        include_raw=False,
        latest_nonempty=latest_nonempty,
    )
    if latest is None:
        return {
            "status": "empty",
            "item": None,
        }
    item = _cycle_to_brain_payload(latest, include_rows=include_rows)
    if isinstance(item, dict):
        item["analysis_engines"] = get_analysis_engines_status(latest_cycle=latest, latest_nonempty=latest_nonempty)
    return {
        "status": "ok",
        "item": item,
    }


@router.get("/cycles")
def portfolio_brain_cycles(
    limit: int = Query(default=20, ge=1, le=100),
    include_rows: bool = Query(default=False),
):
    payload = list_auto_trading_cycle_diagnostics(
        limit=limit,
        include_rows=include_rows,
        include_details=False,
        include_model_breakdown=False,
        include_raw=False,
    )
    items = payload.get("items") if isinstance(payload, dict) else []
    normalized = [
        _cycle_to_brain_payload(item, include_rows=include_rows)
        for item in items
        if isinstance(item, dict)
    ]
    return {
        "status": "ok",
        "count": len(normalized),
        "limit": limit,
        "items": normalized,
    }




@router.get("/cycles/{cycle_id}/allocation-ledger")
def portfolio_brain_cycle_allocation_ledger(
    cycle_id: str,
    include_rows: bool = Query(default=True),
):
    payload = get_auto_trading_cycle_diagnostics(
        cycle_id,
        include_details=False,
        include_model_breakdown=False,
        include_raw=False,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Portfolio-brain cycle not found")

    ledger = payload.get("allocation_ledger") if isinstance(payload.get("allocation_ledger"), dict) else {}
    if include_rows:
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        ledger_rows = [
            {
                "symbol": row.get("symbol"),
                "portfolio_priority_rank": row.get("portfolio_priority_rank"),
                "planned_execution_action": row.get("planned_execution_action"),
                "requested_execution_action": row.get("requested_execution_action"),
                "funded": row.get("funded"),
                "funding_decision": row.get("funding_decision"),
                "funding_status": row.get("funding_status"),
                "funded_partially": row.get("funded_partially"),
                "partial_funding_applied": row.get("partial_funding_applied"),
                "funding_ratio": row.get("funding_ratio"),
                "partial_funding_reason": row.get("partial_funding_reason"),
                "capital_requested_value": row.get("capital_requested_value"),
                "capital_approved_value": row.get("capital_approved_value"),
                "remaining_unfunded_value": row.get("remaining_unfunded_value"),
                "requested_order_qty": row.get("requested_order_qty"),
                "approved_order_qty": row.get("approved_order_qty"),
                "approved_position_pct": row.get("approved_position_pct"),
                "execution_priority_band": row.get("execution_priority_band"),
                "capital_competition_reason": row.get("capital_competition_reason"),
                "better_use_of_capital_reason": row.get("better_use_of_capital_reason"),
                "replacement_candidate": row.get("replacement_candidate"),
                "displaced_symbol": row.get("displaced_symbol"),
                "decision_outcome_code": row.get("decision_outcome_code"),
                "execution_outcome_code": row.get("execution_outcome_code"),
                "execution_engine_status": row.get("execution_engine_status"),
                "broker_submission_status": row.get("broker_submission_status"),
                "broker_lifecycle_status": row.get("broker_lifecycle_status"),
                "execution_final_status": row.get("execution_final_status"),
                "submitted_to_execution_engine_at": row.get("submitted_to_execution_engine_at"),
                "broker_submission_attempted_at": row.get("broker_submission_attempted_at"),
                "broker_acknowledged_at": row.get("broker_acknowledged_at"),
                "broker_last_update_at": row.get("broker_last_update_at"),
                "execution_completed_at": row.get("execution_completed_at"),
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
                "queue_item_id": row.get("queue_item_id"),
                "execution_stage": row.get("execution_stage"),
                "queue_rank": row.get("queue_rank"),
                "queue_status": row.get("queue_status"),
                "queue_reason": row.get("queue_reason"),
                "queue_gate_result": row.get("queue_gate_result"),
                "queue_gate_reason": row.get("queue_gate_reason"),
                "execution_go_no_go": row.get("execution_go_no_go"),
                "defer_reason": row.get("defer_reason"),
                "dependency_type": row.get("dependency_type"),
                "depends_on_queue_item_ids": row.get("depends_on_queue_item_ids"),
                "dependency_satisfied": row.get("dependency_satisfied"),
                "dependency_outcome": row.get("dependency_outcome"),
                "dependency_expected_release_value": row.get("dependency_expected_release_value"),
                "dependency_actual_release_value": row.get("dependency_actual_release_value"),
                "dependency_release_delta": row.get("dependency_release_delta"),
                "dependency_wait_started_at": row.get("dependency_wait_started_at"),
                "dependency_resolved_at": row.get("dependency_resolved_at"),
                "dependency_resolution_reason": row.get("dependency_resolution_reason"),
                "dependency_final_outcome": row.get("dependency_final_outcome"),
                "requires_capital_release": row.get("requires_capital_release"),
                "resized_after_execution_result": row.get("resized_after_execution_result"),
                "original_approved_order_qty": row.get("original_approved_order_qty"),
                "recomputed_approved_order_qty": row.get("recomputed_approved_order_qty"),
                "recomputed_capital_approved_value": row.get("recomputed_capital_approved_value"),
                "recompute_reason": row.get("recompute_reason"),
                "submission_order": row.get("submission_order"),
            }
            for row in rows
            if isinstance(row, dict)
        ]
    else:
        ledger_rows = []

    return {
        "status": "ok",
        "cycle_id": cycle_id,
        "ledger": ledger,
        "rows": ledger_rows,
        "rows_count": len(ledger_rows),
    }


@router.get("/cycles/{cycle_id}/execution-queue")
def portfolio_brain_cycle_execution_queue(cycle_id: str):
    payload = get_auto_trading_cycle_diagnostics(
        cycle_id,
        include_details=False,
        include_model_breakdown=False,
        include_raw=False,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Portfolio-brain cycle not found")

    queue_summary = payload.get("execution_queue_summary") if isinstance(payload.get("execution_queue_summary"), dict) else {}
    queue_items = payload.get("execution_queue") if isinstance(payload.get("execution_queue"), list) else []

    return {
        "status": "ok",
        "cycle_id": cycle_id,
        "summary": queue_summary,
        "items": queue_items,
        "count": len(queue_items),
    }


@router.get("/cycles/{cycle_id}/execution-timeline")
def portfolio_brain_cycle_execution_timeline(cycle_id: str, limit: int = Query(default=200, ge=1, le=2000)):
    payload = get_auto_trading_cycle_diagnostics(
        cycle_id,
        include_details=False,
        include_model_breakdown=False,
        include_raw=False,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Portfolio-brain cycle not found")

    timeline = payload.get("execution_timeline") if isinstance(payload.get("execution_timeline"), list) else []
    if len(timeline) > limit:
        timeline = timeline[-limit:]

    return {
        "status": "ok",
        "cycle_id": cycle_id,
        "count": len(timeline),
        "items": timeline,
    }


@router.get("/cycles/{cycle_id}")
def portfolio_brain_cycle(
    cycle_id: str,
    include_rows: bool = Query(default=True),
    include_details: bool = Query(default=True),
):
    payload = get_auto_trading_cycle_diagnostics(
        cycle_id,
        include_details=include_details,
        include_model_breakdown=False,
        include_raw=False,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Portfolio-brain cycle not found")

    item = _cycle_to_brain_payload(payload, include_rows=include_rows)
    if isinstance(item, dict):
        item["analysis_engines"] = get_analysis_engines_status(latest_cycle=payload, latest_nonempty=False)
    return {
        "status": "ok",
        "item": item,
    }
