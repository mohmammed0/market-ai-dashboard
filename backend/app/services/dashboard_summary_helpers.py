from __future__ import annotations

from datetime import datetime

from backend.app.services.cached_analysis import get_base_analysis_result
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
    sample_rows = []

    for symbol in sample_symbols:
        try:
            result = get_base_analysis_result(symbol, "2024-01-01", current_end_date, ttl_seconds=600)
            if "error" not in result:
                sample_rows.append(result)
        except Exception:
            continue

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
