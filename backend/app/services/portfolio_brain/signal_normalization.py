"""Signal and payload normalization helpers for portfolio-brain modules."""

from __future__ import annotations

from typing import Any


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def coerce_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "T" in text:
        return text.split("T", 1)[0]
    if len(text) >= 10:
        return text[:10]
    return text


def normalize_band(low: float | None, high: float | None) -> tuple[float, float] | None:
    if low is None or high is None:
        return None
    lower = round(min(low, high), 4)
    upper = round(max(low, high), 4)
    if lower == upper:
        upper = round(upper + 0.01, 4)
    return lower, upper


def sentiment_tone(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"BUY", "BULLISH", "POSITIVE"}:
        return "positive"
    if normalized in {"SELL", "BEARISH", "NEGATIVE"}:
        return "negative"
    if normalized in {"HOLD", "NEUTRAL"}:
        return "warning"
    return "subtle"
