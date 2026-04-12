"""Macro economic data endpoints backed by FRED."""
from __future__ import annotations

from fastapi import APIRouter
from backend.app.services import get_cache

router = APIRouter(prefix="/macro", tags=["macro"])


def _macro_cache():
    return get_cache()


@router.get("/snapshot")
def macro_snapshot():
    """Latest values for key macro indicators from FRED."""
    cache = _macro_cache()
    return cache.get_or_set(
        "macro:snapshot",
        lambda: _fetch_macro_snapshot(),
        ttl_seconds=3600,  # 1 hour — FRED updates daily
    )


@router.get("/calendar")
def macro_calendar():
    """Macro regime assessment: VIX regime, yield curve, credit conditions."""
    cache = _macro_cache()
    return cache.get_or_set(
        "macro:calendar",
        lambda: _fetch_macro_calendar(),
        ttl_seconds=3600,
    )


def _fetch_macro_snapshot():
    from core.fred_data import get_macro_snapshot
    return get_macro_snapshot()


def _fetch_macro_calendar():
    from core.fred_data import get_macro_calendar
    return get_macro_calendar()
