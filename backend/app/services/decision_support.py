from __future__ import annotations

import logging
from datetime import date
from typing import Any

from backend.app.core.logging_utils import get_logger
from backend.app.services import get_cache
from backend.app.services.cached_analysis import get_ranked_analysis_result
from backend.app.services.continuous_learning import list_generated_strategy_candidates
from backend.app.services.events_calendar import fetch_market_events
from backend.app.services.explainability import build_signal_explanation
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


def _build_chart_plan(analysis: dict, explanation: dict, events: list[dict]) -> dict:
    signal = str(analysis.get("enhanced_signal") or analysis.get("signal") or "HOLD").upper()
    close = _safe_float(analysis.get("close"))
    atr = abs(_safe_float(analysis.get("atr14"), 0.0) or 0.0)
    support = _safe_float(analysis.get("support"))
    resistance = _safe_float(analysis.get("resistance"))
    atr_stop = _safe_float(analysis.get("atr_stop"))
    atr_target = _safe_float(analysis.get("atr_target"))
    analysis_date = _coerce_date(analysis.get("date"))
    zones: list[dict] = []
    levels: list[dict] = []
    markers: list[dict] = []

    if close is not None:
        if signal == "BUY":
            entry = _normalize_band(
                support if support is not None else close - (atr * 0.4),
                close,
            )
            target = _normalize_band(
                close + (atr * 0.35),
                resistance if resistance is not None else atr_target if atr_target is not None else close + (atr * 1.2),
            )
        elif signal == "SELL":
            entry = _normalize_band(
                close,
                resistance if resistance is not None else close + (atr * 0.4),
            )
            target = _normalize_band(
                support if support is not None else close - (atr * 1.2),
                close - (atr * 0.35),
            )
        else:
            entry = _normalize_band(close - (atr * 0.25), close + (atr * 0.25))
            target = _normalize_band(
                support if support is not None else close - (atr * 0.5),
                resistance if resistance is not None else close + (atr * 0.5),
            )

        if entry is not None:
            zones.append(
                {
                    "kind": "entry_zone",
                    "label": "منطقة الدخول",
                    "tone": "accent" if signal == "BUY" else "warning" if signal == "SELL" else "subtle",
                    "low": entry[0],
                    "high": entry[1],
                    "source": "derived_from_close_support_resistance_atr",
                }
            )
        if target is not None:
            zones.append(
                {
                    "kind": "target_zone",
                    "label": "منطقة الهدف",
                    "tone": "positive",
                    "low": target[0],
                    "high": target[1],
                    "source": "derived_from_resistance_support_atr_target",
                }
            )

        markers.append(
            {
                "kind": "signal_marker",
                "label": signal,
                "tone": _sentiment_tone(signal),
                "date": analysis_date,
                "value": round(close, 4),
                "detail": explanation.get("summary") or analysis.get("reasons"),
            }
        )

    for kind, label, value, tone in (
        ("support", "الدعم", support, "subtle"),
        ("resistance", "المقاومة", resistance, "warning"),
        ("invalidation", "الإبطال / الوقف", atr_stop, "negative"),
        ("target", "هدف ATR", atr_target, "positive"),
    ):
        if value is not None:
            levels.append(
                {
                    "kind": kind,
                    "label": label,
                    "value": round(value, 4),
                    "tone": tone,
                }
            )

    for row in (analysis.get("news_items") or [])[:3]:
        published_at = _coerce_date(row.get("published"))
        markers.append(
            {
                "kind": "news_marker",
                "label": row.get("source") or "خبر",
                "tone": _sentiment_tone(row.get("sentiment")),
                "date": published_at,
                "value": round(close, 4) if close is not None else None,
                "detail": row.get("title"),
            }
        )

    for row in events[:2]:
        event_date = _coerce_date(row.get("event_at"))
        markers.append(
            {
                "kind": "event_marker",
                "label": row.get("event_type") or row.get("title") or "حدث",
                "tone": "subtle",
                "date": event_date,
                "value": round(close, 4) if close is not None else None,
                "detail": row.get("summary") or row.get("description") or row.get("event_type"),
            }
        )

    return {
        "note": "المناطق والمستويات مشتقة من الدعم والمقاومة وATR والإشارة الحالية، وليست توصية مستقلة جديدة.",
        "zones": zones,
        "levels": levels,
        "markers": markers[:6],
    }


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
    start_date: str = "2024-01-01",
    end_date: str | None = None,
    *,
    include_dl: bool = True,
    include_ensemble: bool = True,
) -> dict:
    normalized_symbol = normalize_symbol(symbol or "AAPL")
    resolved_end_date = end_date or date.today().isoformat()
    cache_key = f"decision:symbol:{normalized_symbol}:{start_date}:{resolved_end_date}:{int(include_dl)}:{int(include_ensemble)}"

    def factory() -> dict:
        analysis = get_ranked_analysis_result(
            normalized_symbol,
            start_date,
            resolved_end_date,
            include_ml=True,
            include_dl=include_dl,
            ttl_seconds=300,
        )
        explanation = build_signal_explanation(analysis)
        events = (fetch_market_events(symbols=[normalized_symbol], limit=4) or {}).get("items") or []
        strategy_hooks = _build_strategy_hooks(normalized_symbol)
        news_items = analysis.get("news_items") or []
        ai_summary = analysis.get("ai_summary")
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
                    start_date,
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
            "stance": str(analysis.get("enhanced_signal") or analysis.get("signal") or "HOLD").upper(),
            "signal": str(analysis.get("signal") or "HOLD").upper(),
            "confidence": round(float(analysis.get("confidence", 0.0) or 0.0), 2),
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
