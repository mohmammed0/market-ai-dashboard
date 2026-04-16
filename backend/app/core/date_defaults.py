from __future__ import annotations

from datetime import date, timedelta

from backend.app.config import DEFAULT_ANALYSIS_LOOKBACK_DAYS, DEFAULT_TRAINING_LOOKBACK_DAYS


def recent_end_date_iso() -> str:
    return date.today().isoformat()


def recent_start_date_iso(lookback_days: int | None = None) -> str:
    days = max(int(lookback_days or DEFAULT_ANALYSIS_LOOKBACK_DAYS), 7)
    return (date.today() - timedelta(days=days)).isoformat()


def training_start_date_iso(lookback_days: int | None = None) -> str:
    days = max(int(lookback_days or DEFAULT_TRAINING_LOOKBACK_DAYS), 90)
    return (date.today() - timedelta(days=days)).isoformat()


def analysis_window_iso(
    start_date_or_lookback: str | int | None = None,
    end_date: str | None = None,
) -> tuple[str, str]:
    if isinstance(start_date_or_lookback, str):
        return start_date_or_lookback, end_date or recent_end_date_iso()
    return recent_start_date_iso(start_date_or_lookback), end_date or recent_end_date_iso()


def training_window_iso(
    start_date_or_lookback: str | int | None = None,
    end_date: str | None = None,
) -> tuple[str, str]:
    if isinstance(start_date_or_lookback, str):
        return start_date_or_lookback, end_date or recent_end_date_iso()
    return training_start_date_iso(start_date_or_lookback), end_date or recent_end_date_iso()
