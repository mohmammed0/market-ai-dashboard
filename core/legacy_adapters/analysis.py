from legacy.engines.analysis_engine import (
    _combined_signal,
    _fallback_news_payload,
    _ml_score_from_result,
    _safe_round,
    run_analysis,
)


def analyze_stock(symbol: str, start_date: str | None = None, end_date: str | None = None, **kwargs):
    return run_analysis(instrument=symbol, start_date=start_date, end_date=end_date, **kwargs)


def combined_signal(score: int) -> str:
    return _combined_signal(score)


def fallback_news_payload(error: str) -> dict:
    return _fallback_news_payload(error)


def ml_score_from_result(payload: dict | None) -> int:
    return _ml_score_from_result(payload)


def safe_round(value: float | None, digits: int = 2):
    return _safe_round(value, digits)


__all__ = [
    "analyze_stock",
    "combined_signal",
    "fallback_news_payload",
    "ml_score_from_result",
    "run_analysis",
    "safe_round",
]
