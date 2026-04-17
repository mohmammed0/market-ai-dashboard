from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from backend.app.config import (
    DECISION_ACTION_ADD_CONFIDENCE,
    DECISION_ACTION_BUY_CONFIDENCE,
    DECISION_ACTION_EXIT_CONFIDENCE,
    DECISION_ACTION_HOLD_CONFIDENCE,
    DECISION_ACTION_TRIM_CONFIDENCE,
    DECISION_OPPORTUNITY_MIN_CONFIDENCE,
    LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
    LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS,
)
from backend.app.core.date_defaults import recent_start_date_iso
from backend.app.services.cached_analysis import get_base_analysis_results_batch, get_ranked_analysis_result
from backend.app.services.confidence_calibration import (
    apply_confidence_calibration_to_analysis,
    get_latest_confidence_calibration_profile,
)
from backend.app.services.explainability import build_signal_explanation
from core.ranking_service import rank_scan_results


def safe_service_call(factory, fallback):
    try:
        return factory()
    except Exception as exc:
        if isinstance(fallback, dict):
            payload = dict(fallback)
            payload.setdefault("error", str(exc))
            return payload
        return fallback


def build_sample_scan_snapshot(sample_symbols: list[str]) -> tuple[list[dict], dict | None, dict[str, int]]:
    current_end_date = datetime.utcnow().date().isoformat()

    all_results = get_base_analysis_results_batch(
        sample_symbols,
        recent_start_date_iso(),
        current_end_date,
        ttl_seconds=600,
        max_workers=4,
    )
    sample_rows = [r for r in all_results if "error" not in r]

    ranked_rows = rank_scan_results(sample_rows)
    signal_counts = {"BUY": 0, "HOLD": 0, "SELL": 0}
    for row in ranked_rows:
        signal = str(row.get("signal", "HOLD")).upper()
        if signal in signal_counts:
            signal_counts[signal] += 1

    sample_analyze = None
    if ranked_rows:
        top_row = ranked_rows[0]
        sample_analyze = {
            "instrument": top_row.get("instrument"),
            "signal": top_row.get("signal"),
            "enhanced_combined_score": top_row.get("enhanced_combined_score", top_row.get("combined_score")),
            "confidence": top_row.get("confidence"),
            "best_setup": top_row.get("best_setup"),
            "setup_type": top_row.get("setup_type"),
            "ai_error": top_row.get("ai_error"),
        }

    return ranked_rows, sample_analyze, signal_counts


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _derive_action(signal: str, confidence: float, ranked: dict) -> str:
    technical_score = _safe_float(ranked.get("technical_score"), 0.0)
    mtf_score = _safe_float(ranked.get("mtf_score"), 0.0)
    rs_score = _safe_float(ranked.get("rs_score"), 0.0)
    ensemble = ranked.get("ensemble_output") or {}
    ensemble_score = abs(_safe_float(ensemble.get("ensemble_score"), 0.0))
    news_items = ranked.get("news_items") or []
    lead_news = news_items[0] if news_items else {}
    news_tone = str(lead_news.get("sentiment") or "").upper()
    ml_output = ranked.get("ml_output") or {}
    ml_buy = _safe_float(ml_output.get("prob_buy"), 0.0)
    ml_sell = _safe_float(ml_output.get("prob_sell"), 0.0)

    normalized_signal = str(signal or "HOLD").upper().strip()
    if normalized_signal == "BUY":
        if confidence >= DECISION_ACTION_BUY_CONFIDENCE and technical_score >= 1 and (mtf_score >= 0 or rs_score >= 0):
            return "BUY"
        if confidence >= DECISION_ACTION_ADD_CONFIDENCE and (technical_score >= -0.5 or ensemble_score >= 0.2):
            return "ADD"
        return "WATCH"

    if normalized_signal == "SELL":
        if confidence >= DECISION_ACTION_EXIT_CONFIDENCE or (technical_score <= -3 and news_tone == "NEGATIVE"):
            return "EXIT"
        if confidence >= DECISION_ACTION_TRIM_CONFIDENCE or (technical_score <= -2 and ml_sell > ml_buy + 0.10):
            return "TRIM"
        return "WATCH"

    if technical_score <= -2 and (news_tone == "NEGATIVE" or ml_sell > ml_buy + 0.15):
        return "TRIM"
    if confidence >= DECISION_ACTION_HOLD_CONFIDENCE:
        return "HOLD"
    return "WATCH"


def _opportunity_quality(action: str, confidence: float, score: float, news_impact_score: float) -> float:
    action_weight = {
        "BUY": 100.0,
        "ADD": 92.0,
        "EXIT": 86.0,
        "TRIM": 76.0,
        "HOLD": 62.0,
        "WATCH": 54.0,
    }.get(str(action or "WATCH").upper(), 50.0)
    return round(action_weight + confidence * 0.7 + abs(score) * 8.0 + max(news_impact_score, 0.0) * 0.35, 4)


def _is_actionable_opportunity(action: str, confidence: float, score: float, news_event_type: str | None) -> bool:
    normalized = str(action or "WATCH").upper().strip()
    if normalized in {"BUY", "ADD", "TRIM", "EXIT"}:
        return confidence >= DECISION_OPPORTUNITY_MIN_CONFIDENCE
    if normalized == "HOLD":
        return confidence >= max(DECISION_ACTION_HOLD_CONFIDENCE, DECISION_OPPORTUNITY_MIN_CONFIDENCE)
    if normalized == "WATCH":
        if confidence >= 60.0:
            return True
        if confidence >= 55.0 and bool(news_event_type) and abs(score) >= 0.6:
            return True
        return False
    return False


def build_focused_opportunity_snapshot(sample_symbols: list[str]) -> list[dict]:
    current_end_date = datetime.utcnow().date().isoformat()
    selected_symbols = [
        str(symbol or "").strip().upper()
        for symbol in sample_symbols[:LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS]
        if str(symbol or "").strip()
    ]
    if not selected_symbols:
        return []
    calibration_profile = get_latest_confidence_calibration_profile()

    max_workers = max(1, min(int(os.environ.get("MARKET_AI_ANALYSIS_CONCURRENCY", "2") or 2), 2, len(selected_symbols)))

    def worker(symbol: str) -> dict | None:
        ranked = get_ranked_analysis_result(
            symbol,
            recent_start_date_iso(),
            current_end_date,
            ttl_seconds=600,
            include_ml=True,
            include_dl=LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
        )
        if "error" in ranked:
            return None
        ranked = apply_confidence_calibration_to_analysis(ranked, calibration_profile)

        ensemble = ranked.get("ensemble_output") or {}
        explanation = build_signal_explanation(ranked)
        signal = str(ensemble.get("signal") or ranked.get("enhanced_signal") or ranked.get("signal") or "HOLD").upper()
        confidence = float(ensemble.get("confidence") or ranked.get("confidence") or 0.0)
        news_items = ranked.get("news_items") or []
        latest_news = news_items[0] if news_items else {}
        reason = (
            explanation.get("summary")
            or ranked.get("ai_summary")
            or ranked.get("best_setup")
            or ranked.get("setup_type")
            or latest_news.get("title")
            or "No concise rationale available."
        )
        action = _derive_action(signal, confidence, ranked)
        quality_score = _opportunity_quality(
            action=action,
            confidence=confidence,
            score=_safe_float(ensemble.get("ensemble_score"), _safe_float(ranked.get("enhanced_combined_score"), _safe_float(ranked.get("combined_score"), 0.0))),
            news_impact_score=_safe_float(latest_news.get("impact_score"), 0.0),
        )
        if not _is_actionable_opportunity(
            action=action,
            confidence=confidence,
            score=_safe_float(ensemble.get("ensemble_score"), _safe_float(ranked.get("enhanced_combined_score"), _safe_float(ranked.get("combined_score"), 0.0))),
            news_event_type=latest_news.get("event_type"),
        ):
            return None

        return {
            "symbol": symbol,
            "signal": signal,
            "confidence": round(confidence, 2),
            "score": ensemble.get("ensemble_score", ranked.get("enhanced_combined_score", ranked.get("combined_score"))),
            "reason": reason,
            "setup_type": ranked.get("setup_type"),
            "best_setup": ranked.get("best_setup"),
            "risk_label": ranked.get("trend_mode") or ranked.get("market_regime") or "RANGE",
            "action": action,
            "news_event_type": latest_news.get("event_type"),
            "news_sentiment": latest_news.get("sentiment"),
            "news_impact_score": latest_news.get("impact_score"),
            "opportunity_score": quality_score,
        }

    if max_workers == 1:
        items = [worker(symbol) for symbol in selected_symbols]
    else:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="focused-opps") as executor:
            items = list(executor.map(worker, selected_symbols))

    priority = {"BUY": 0, "ADD": 1, "EXIT": 2, "TRIM": 3, "HOLD": 4, "WATCH": 5}
    candidates = [item for item in items if item]
    candidates.sort(
        key=lambda row: (
            priority.get(str(row.get("action") or "WATCH").upper(), 9),
            -float(row.get("opportunity_score") or 0.0),
            -float(row.get("confidence") or 0.0),
        )
    )
    return candidates[:4]
