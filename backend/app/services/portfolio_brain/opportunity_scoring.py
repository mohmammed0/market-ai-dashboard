"""Opportunity scoring for portfolio-brain candidate ranking."""

from __future__ import annotations

from backend.app.services.portfolio_brain.signal_normalization import safe_float


_ACTION_WEIGHT = {
    "BUY": 100.0,
    "ADD": 92.0,
    "EXIT": 86.0,
    "TRIM": 76.0,
    "HOLD": 62.0,
    "WATCH": 54.0,
}


def compute_opportunity_score(analysis: dict) -> float:
    action = str(analysis.get("action") or analysis.get("resolved_action") or "WATCH").upper()
    confidence = safe_float(analysis.get("confidence"), 0.0) or 0.0
    ensemble = analysis.get("ensemble_output") or {}
    score = safe_float(
        ensemble.get("ensemble_score"),
        safe_float(analysis.get("enhanced_combined_score"), safe_float(analysis.get("combined_score"), 0.0)),
    ) or 0.0
    news_items = analysis.get("news_items") or []
    news_impact = safe_float((news_items[0] if news_items else {}).get("impact_score"), 0.0) or 0.0
    action_weight = _ACTION_WEIGHT.get(action, 50.0)
    return round(action_weight + confidence * 0.7 + abs(score) * 8.0 + max(news_impact, 0.0) * 0.35, 4)
