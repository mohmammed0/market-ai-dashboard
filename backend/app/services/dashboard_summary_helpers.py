from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from backend.app.config import LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL, LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS
from backend.app.core.date_defaults import recent_start_date_iso
from backend.app.services.cached_analysis import get_base_analysis_results_batch, get_ranked_analysis_result
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


def build_focused_opportunity_snapshot(sample_symbols: list[str]) -> list[dict]:
    current_end_date = datetime.utcnow().date().isoformat()
    selected_symbols = [
        str(symbol or "").strip().upper()
        for symbol in sample_symbols[:LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS]
        if str(symbol or "").strip()
    ]
    if not selected_symbols:
        return []

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
        return {
            "symbol": symbol,
            "signal": signal,
            "confidence": round(confidence, 2),
            "score": ensemble.get("ensemble_score", ranked.get("enhanced_combined_score", ranked.get("combined_score"))),
            "reason": reason,
            "setup_type": ranked.get("setup_type"),
            "best_setup": ranked.get("best_setup"),
            "risk_label": ranked.get("trend_mode") or ranked.get("market_regime") or "RANGE",
            "action": signal if signal in {"BUY", "SELL", "HOLD"} else "WATCH",
            "news_event_type": latest_news.get("event_type"),
            "news_sentiment": latest_news.get("sentiment"),
            "news_impact_score": latest_news.get("impact_score"),
        }

    if max_workers == 1:
        items = [worker(symbol) for symbol in selected_symbols]
    else:
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="focused-opps") as executor:
            items = list(executor.map(worker, selected_symbols))

    priority = {"BUY": 0, "SELL": 1, "HOLD": 2}
    candidates = [item for item in items if item]
    candidates.sort(
        key=lambda row: (
            priority.get(str(row.get("signal") or "HOLD").upper(), 9),
            -float(row.get("confidence") or 0.0),
        )
    )
    return candidates[:6]
