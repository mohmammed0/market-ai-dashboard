"""Action decision policy for portfolio-brain outputs."""

from __future__ import annotations

from backend.app.config import (
    DECISION_ACTION_ADD_CONFIDENCE,
    DECISION_ACTION_BUY_CONFIDENCE,
    DECISION_ACTION_EXIT_CONFIDENCE,
    DECISION_ACTION_HOLD_CONFIDENCE,
    DECISION_ACTION_TRIM_CONFIDENCE,
)
from backend.app.services.portfolio_brain.signal_normalization import safe_float


def resolve_action(signal: str, confidence: float, analysis: dict) -> str:
    normalized_signal = str(signal or "HOLD").upper().strip()
    technical_score = safe_float(analysis.get("technical_score"), 0.0) or 0.0
    ensemble_output = analysis.get("ensemble_output") or {}
    ensemble_score = abs(safe_float(ensemble_output.get("ensemble_score"), 0.0) or 0.0)
    news_items = analysis.get("news_items") or []
    news_tone = str((news_items[0] if news_items else {}).get("sentiment") or "").upper()
    ml_output = analysis.get("ml_output") or {}
    ml_buy = safe_float(ml_output.get("prob_buy"), 0.0) or 0.0
    ml_sell = safe_float(ml_output.get("prob_sell"), 0.0) or 0.0

    if normalized_signal == "BUY":
        if (
            confidence >= DECISION_ACTION_BUY_CONFIDENCE
            and technical_score >= 1
            and (ml_buy >= ml_sell or news_tone != "NEGATIVE")
        ):
            return "BUY"
        if (
            confidence >= DECISION_ACTION_ADD_CONFIDENCE
            and (technical_score >= -0.5 or ensemble_score >= 0.2)
        ):
            return "ADD"
        return "WATCH"
    if normalized_signal == "SELL":
        if confidence >= DECISION_ACTION_EXIT_CONFIDENCE or (technical_score <= -3 and news_tone == "NEGATIVE"):
            return "EXIT"
        if confidence >= DECISION_ACTION_TRIM_CONFIDENCE or ml_sell > ml_buy + 0.10:
            return "TRIM"
        return "WATCH"
    if technical_score <= -2 and (news_tone == "NEGATIVE" or ml_sell > ml_buy + 0.15):
        return "TRIM"
    if confidence >= DECISION_ACTION_HOLD_CONFIDENCE:
        return "HOLD"
    return "WATCH"
