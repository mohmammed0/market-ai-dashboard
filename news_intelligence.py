from __future__ import annotations

import re
from typing import Any


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "stock",
    "shares",
    "that",
    "the",
    "to",
    "with",
}

EVENT_PATTERNS = {
    "earnings": (
        "earnings",
        "revenue",
        "eps",
        "guidance",
        "quarter",
        "q1",
        "q2",
        "q3",
        "q4",
    ),
    "analyst": (
        "price target",
        "upgraded",
        "downgraded",
        "buy rating",
        "sell rating",
        "outperform",
        "underperform",
        "initiated",
    ),
    "corporate_action": (
        "buyback",
        "dividend",
        "split",
        "offering",
        "secondary",
        "repurchase",
    ),
    "mna": (
        "acquire",
        "acquisition",
        "merger",
        "buying",
        "stake",
        "takeover",
    ),
    "product": (
        "launch",
        "product",
        "partnership",
        "deal",
        "contract",
        "expansion",
        "approval",
    ),
    "legal_regulatory": (
        "lawsuit",
        "investigation",
        "probe",
        "antitrust",
        "regulator",
        "sec",
        "fda",
        "fine",
    ),
    "macro": (
        "fed",
        "inflation",
        "rates",
        "treasury",
        "jobs report",
        "cpi",
        "ppi",
        "gdp",
    ),
}

SOURCE_QUALITY = {
    "reuters": 0.98,
    "bloomberg": 0.98,
    "associated press": 0.95,
    "ap": 0.95,
    "wsj": 0.95,
    "wall street journal": 0.95,
    "barrons": 0.9,
    "barron's": 0.9,
    "marketwatch": 0.88,
    "cnbc": 0.88,
    "investing.com": 0.78,
    "seeking alpha": 0.75,
    "the motley fool": 0.65,
    "motley fool": 0.65,
}

EVENT_WEIGHT = {
    "earnings": 2.0,
    "analyst": 1.5,
    "corporate_action": 1.0,
    "mna": 1.6,
    "product": 0.9,
    "legal_regulatory": 1.7,
    "macro": 0.7,
    "general": 0.5,
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_news_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return re.sub(r"[^a-z0-9%$ ]+", " ", text).strip()


def headline_signature(title: Any) -> str:
    text = normalize_news_text(title)
    tokens = [token for token in text.split() if len(token) > 2 and token not in STOPWORDS]
    return " ".join(tokens[:8])


def classify_event_type(title: Any, source: Any = None) -> str:
    haystack = f"{normalize_news_text(title)} {normalize_news_text(source)}".strip()
    for event_type, patterns in EVENT_PATTERNS.items():
        if any(pattern in haystack for pattern in patterns):
            return event_type
    return "general"


def source_quality_score(source: Any) -> float:
    normalized = normalize_news_text(source)
    for key, score in SOURCE_QUALITY.items():
        if key in normalized:
            return score
    return 0.55


def relevance_score(symbol: str | None, title: Any, event_type: str) -> float:
    normalized_title = normalize_news_text(title)
    score = 0.45 + EVENT_WEIGHT.get(event_type, 0.5) * 0.12
    if symbol and str(symbol).strip().lower() in normalized_title:
        score += 0.25
    if event_type in {"earnings", "analyst", "legal_regulatory", "mna"}:
        score += 0.12
    return round(clamp(score, 0.1, 1.0), 3)


def classify_news_item(symbol: str | None, title: Any, source: Any = None, *, novelty_score: float = 1.0, relation: str = "fresh") -> dict:
    event_type = classify_event_type(title, source)
    source_quality = source_quality_score(source)
    relevance = relevance_score(symbol, title, event_type)
    novelty = round(clamp(float(novelty_score or 0.0), 0.1, 1.0), 3)
    impact_score = round(clamp((relevance * 0.5) + (source_quality * 0.3) + (novelty * 0.2), 0.0, 1.0), 3)
    return {
        "event_type": event_type,
        "source_quality_score": source_quality,
        "relevance_score": relevance,
        "novelty_score": novelty,
        "impact_score": impact_score,
        "event_relation": relation,
        "semantic_signature": headline_signature(title),
    }
