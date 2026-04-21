from __future__ import annotations

import logging
from datetime import date
from typing import Any

from backend.app.config import (
    DECISION_ACTION_ADD_CONFIDENCE,
    DECISION_ACTION_BUY_CONFIDENCE,
    DECISION_ACTION_EXIT_CONFIDENCE,
    DECISION_ACTION_HOLD_CONFIDENCE,
    DECISION_ACTION_TRIM_CONFIDENCE,
)
from backend.app.core.date_defaults import recent_end_date_iso, recent_start_date_iso
from backend.app.core.logging_utils import get_logger
from backend.app.services import get_cache
from backend.app.services.cached_analysis import get_ranked_analysis_result
from backend.app.services.confidence_calibration import (
    apply_confidence_calibration_to_analysis,
    get_latest_confidence_calibration_profile,
)
from backend.app.services.continuous_learning import list_generated_strategy_candidates
from backend.app.services.events_calendar import fetch_market_events
from backend.app.services.explainability import build_signal_explanation
from backend.app.services.portfolio_brain.decision_policy import resolve_action as _resolve_policy_action
from backend.app.services.portfolio_brain.explanation_payload import build_chart_plan as _build_brain_chart_plan
from backend.app.services.strategy_lab import list_strategy_evaluations
from core.source_data import normalize_symbol

logger = get_logger(__name__)

# Architecture-alignment additions (non-breaking)
try:
    from backend.app.services.deterministic_core import build_decision_package as _build_decision_package_typed
    _TYPED_PACKAGE_AVAILABLE = True
except Exception:
    _TYPED_PACKAGE_AVAILABLE = False

try:
    from backend.app.services.ai_overlay import enrich_with_ai_overlay as _enrich_with_ai_overlay
    _AI_OVERLAY_AVAILABLE = True
except Exception:
    _AI_OVERLAY_AVAILABLE = False

try:
    from backend.app.services.observability import record_analysis as _record_analysis
    _OBSERVABILITY_AVAILABLE = True
except Exception:
    _OBSERVABILITY_AVAILABLE = False


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _coerce_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "T" in text:
        return text.split("T", 1)[0]
    if len(text) >= 10:
        return text[:10]
    return text


def _normalize_band(low: float | None, high: float | None) -> tuple[float, float] | None:
    if low is None or high is None:
        return None
    lower = round(min(low, high), 4)
    upper = round(max(low, high), 4)
    if lower == upper:
        upper = round(upper + 0.01, 4)
    return lower, upper


def _sentiment_tone(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"BUY", "BULLISH", "POSITIVE"}:
        return "positive"
    if normalized in {"SELL", "BEARISH", "NEGATIVE"}:
        return "negative"
    if normalized in {"HOLD", "NEUTRAL"}:
        return "warning"
    return "subtle"


def _resolve_action(signal: str, confidence: float, analysis: dict) -> str:
    return _resolve_policy_action(signal, confidence, analysis)


def _build_chart_plan(analysis: dict, explanation: dict, events: list[dict]) -> dict:
    return _build_brain_chart_plan(analysis, explanation, events)


def _build_strategy_hooks(symbol: str) -> dict:
    latest_evaluation = None
    history_items = (list_strategy_evaluations(limit=30) or {}).get("items") or []
    for item in history_items:
        if str(item.get("instrument") or "").strip().upper() == symbol:
            leaderboard = item.get("leaderboard") or []
            metrics = item.get("metrics") or {}
            latest_evaluation = {
                "run_id": item.get("run_id"),
                "status": item.get("status"),
                "completed_at": item.get("completed_at"),
                "best_strategy": metrics.get("best_strategy") or (leaderboard[0].get("strategy") if leaderboard else None),
                "strategies_count": len(leaderboard),
                "top_score": leaderboard[0].get("robust_score") if leaderboard else None,
            }
            break

    generated_candidate = None
    candidate_rows = (list_generated_strategy_candidates(limit=10) or {}).get("latest_candidates") or []
    for item in candidate_rows:
        if str(item.get("anchor_symbol") or "").strip().upper() == symbol:
            generated_candidate = {
                "candidate_name": item.get("candidate_name"),
                "family": item.get("family"),
                "score": item.get("score"),
                "policy_weight": item.get("policy_weight"),
                "live_bias": item.get("live_bias"),
            }
            break

    return {
        "latest_evaluation": latest_evaluation,
        "generated_candidate": generated_candidate,
    }


def build_decision_payload(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    include_dl: bool = False,
    include_ensemble: bool = True,
) -> dict:
    normalized_symbol = normalize_symbol(symbol or "AAPL")
    resolved_start_date = start_date or recent_start_date_iso()
    resolved_end_date = end_date or recent_end_date_iso()
    cache_key = f"decision:symbol:{normalized_symbol}:{resolved_start_date}:{resolved_end_date}:{int(include_dl)}:{int(include_ensemble)}"

    def factory() -> dict:
        analysis = get_ranked_analysis_result(
            normalized_symbol,
            resolved_start_date,
            resolved_end_date,
            include_ml=True,
            include_dl=include_dl,
            ttl_seconds=300,
        )
        calibration_profile = get_latest_confidence_calibration_profile()
        analysis = apply_confidence_calibration_to_analysis(analysis, calibration_profile)
        explanation = build_signal_explanation(analysis)
        events = (fetch_market_events(symbols=[normalized_symbol], limit=4) or {}).get("items") or []
        strategy_hooks = _build_strategy_hooks(normalized_symbol)
        news_items = analysis.get("news_items") or []
        ai_summary = analysis.get("ai_summary")
        resolved_signal = str(explanation.get("signal") or analysis.get("enhanced_signal") or analysis.get("signal") or "HOLD").upper()
        resolved_confidence = round(float(explanation.get("confidence") or analysis.get("confidence", 0.0) or 0.0), 2)
        resolved_action = _resolve_action(resolved_signal, resolved_confidence, analysis)
        rationale = (
            ((analysis.get("ensemble_output") or {}).get("reasoning") if include_ensemble else None)
            or analysis.get("reasons")
            or explanation.get("summary")
        )

        # -- Typed DecisionPackage (architecture-alignment) ------------------
        decision_package_dict: dict | None = None
        decision_surface: dict | None = None
        pkg_evidence: list[str] = []
        pkg_targets: list[float] = []
        pkg_invalidation: float | None = _safe_float(analysis.get("atr_stop"))
        pkg_deterministic_only: bool = True
        ai_overlay_applied: bool = False
        if _TYPED_PACKAGE_AVAILABLE:
            try:
                decision_pkg = _build_decision_package_typed(
                    normalized_symbol,
                    resolved_start_date,
                    resolved_end_date,
                    include_dl=include_dl,
                    include_ensemble=include_ensemble,
                )

                # -- AI Overlay enrichment (non-blocking, fallback-safe) --------
                # The deterministic package is built first and independently.
                # AI overlay only enriches ai_layer; it never modifies
                # price_layer, signal_layer, or risk_layer.
                if _AI_OVERLAY_AVAILABLE:
                    try:
                        decision_pkg = _enrich_with_ai_overlay(decision_pkg)
                        ai_overlay_applied = not decision_pkg.deterministic_only
                    except Exception as ai_exc:
                        # AI failure must never break the main flow
                        logger.warning(
                            "ai_overlay.decision_support_fallback",
                            extra={"error": str(ai_exc)[:200]},
                        )

                decision_package_dict = decision_pkg.model_dump(mode="json")
                # Extract typed decision surface for chart rendering
                decision_surface = decision_package_dict.get("chart_surface")
                pkg_evidence = decision_package_dict.get("evidence", [])
                pkg_targets = decision_package_dict.get("targets", [])
                pkg_invalidation = decision_package_dict.get("invalidation") or pkg_invalidation
                pkg_deterministic_only = decision_package_dict.get("deterministic_only", True)
            except Exception:
                decision_package_dict = None

        # -- Observability ---------------------------------------------------
        if _OBSERVABILITY_AVAILABLE:
            try:
                _record_analysis(symbol=normalized_symbol, status="ok")
            except Exception:
                pass

        # -- Chart plan (existing raw dict path, always present) -----------
        chart_plan = _build_chart_plan(analysis, explanation, events)

        payload: dict = {
            "symbol": normalized_symbol,
            "stance": resolved_signal,
            "signal": str(analysis.get("signal") or "HOLD").upper(),
            "confidence": resolved_confidence,
            "action": resolved_action,
            "best_setup": analysis.get("best_setup"),
            "setup_type": analysis.get("setup_type"),
            "rationale": rationale,
            "summary": explanation.get("summary"),
            "bullish_factors": explanation.get("supporting_factors") or [],
            "bearish_factors": explanation.get("contradictory_factors") or [],
            "risks": explanation.get("invalidators") or [],
            "explainability": explanation,
            "news": {
                "sentiment": analysis.get("ai_news_sentiment") or analysis.get("news_sentiment"),
                "score": analysis.get("ai_news_score", analysis.get("news_score")),
                "summary": ai_summary,
                "items": news_items[:4],
            },
            "events": events[:4],
            "strategy_hooks": strategy_hooks,
            "backtest_hooks": {
                "risk_reward": analysis.get("risk_reward"),
                "support": analysis.get("support"),
                "resistance": analysis.get("resistance"),
                "atr_stop": analysis.get("atr_stop"),
                "atr_target": analysis.get("atr_target"),
                "technical_score": analysis.get("technical_score"),
                "mtf_score": analysis.get("mtf_score"),
                "rs_score": analysis.get("rs_score"),
            },
            "chart_plan": chart_plan,
            "analysis": analysis,
            # --- Architecture-alignment: end-to-end outputs ---
            # Typed decision surface (zones/levels/markers from typed contracts)
            "decision_surface": decision_surface or chart_plan,
            # Evidence, targets, invalidation from typed package
            "evidence": pkg_evidence,
            "targets": pkg_targets,
            "invalidation": pkg_invalidation,
            # Provenance: explicit source labelling
            "provenance": {
                "price_layer": "deterministic",
                "signal_layer": "deterministic",
                "risk_layer": "deterministic",
                "news_layer": "tool_derived",
                "ai_layer": "deterministic" if pkg_deterministic_only else "ai_enriched",
                "chart_surface": "deterministic",
                "deterministic_only": pkg_deterministic_only,
                "ai_overlay_applied": ai_overlay_applied,
                "ai_source": (decision_package_dict or {}).get("ai_layer", {}).get("source", "deterministic") if decision_package_dict else "deterministic",
                "ai_model": (decision_package_dict or {}).get("ai_layer", {}).get("model_used") if decision_package_dict else None,
                "ai_generated_at": (decision_package_dict or {}).get("ai_layer", {}).get("generated_at") if decision_package_dict else None,
            },
        }
        if decision_package_dict is not None:
            payload["decision_package"] = decision_package_dict
        return payload

    return get_cache().get_or_set(cache_key, factory, ttl_seconds=120)
