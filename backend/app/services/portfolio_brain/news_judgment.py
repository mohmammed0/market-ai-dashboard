"""News judgment summarization for portfolio-brain payloads."""

from __future__ import annotations


def summarize_news_judgment(news_items: list[dict] | None) -> dict:
    rows = list(news_items or [])
    lead = rows[0] if rows else {}
    positive = sum(1 for row in rows if str(row.get("sentiment") or "").upper() in {"POSITIVE", "BUY", "BULLISH"})
    negative = sum(1 for row in rows if str(row.get("sentiment") or "").upper() in {"NEGATIVE", "SELL", "BEARISH"})
    neutral = max(len(rows) - positive - negative, 0)
    return {
        "lead": {
            "title": lead.get("title"),
            "sentiment": lead.get("sentiment"),
            "impact_score": lead.get("impact_score"),
            "event_type": lead.get("event_type"),
            "published": lead.get("published"),
        },
        "counts": {
            "total": len(rows),
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
        },
        "items": rows[:4],
    }
