"""Portfolio-brain payload assembly service."""

from __future__ import annotations

from .explanation_payload import build_chart_plan
from .news_judgment import summarize_news_judgment
from .opportunity_scoring import compute_opportunity_score


def build_portfolio_brain_payload(*, symbol: str, action: str, confidence: float, analysis: dict) -> dict:
    opportunity_score = compute_opportunity_score(analysis)
    chart_plan = build_chart_plan(analysis, {"summary": analysis.get("reasons")}, [])
    news = summarize_news_judgment(analysis.get("news_items") or [])
    return {
        "symbol": str(symbol or "").upper(),
        "action": str(action or "WATCH").upper(),
        "confidence": round(float(confidence or 0.0), 2),
        "opportunity_score": opportunity_score,
        "news_judgment": news,
        "chart_plan": chart_plan,
    }
