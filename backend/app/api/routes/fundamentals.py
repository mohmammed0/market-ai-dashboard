"""SEC EDGAR fundamentals endpoint."""
from __future__ import annotations

from fastapi import APIRouter
from backend.app.services import get_cache

router = APIRouter(prefix="/fundamentals", tags=["fundamentals"])

_TTL_SECONDS = 86400  # 24 hours — SEC data is quarterly


def _fundamentals_cache():
    return get_cache()


@router.get("/{ticker}")
def get_fundamentals(ticker: str):
    """Return SEC EDGAR fundamentals snapshot for a ticker (cached 24h)."""
    cache = _fundamentals_cache()
    cache_key = f"fundamentals:{ticker.upper()}"
    return cache.get_or_set(
        cache_key,
        lambda: _fetch_fundamentals(ticker),
        ttl_seconds=_TTL_SECONDS,
    )


@router.get("/{ticker}/facts")
def get_company_facts_endpoint(ticker: str):
    """Return detailed SEC EDGAR XBRL company facts for a ticker (cached 24h)."""
    cache = _fundamentals_cache()
    cache_key = f"fundamentals:facts:{ticker.upper()}"
    return cache.get_or_set(
        cache_key,
        lambda: _fetch_company_facts(ticker),
        ttl_seconds=_TTL_SECONDS,
    )


def _fetch_fundamentals(ticker: str) -> dict:
    from core.edgar_data import get_fundamentals_snapshot
    return get_fundamentals_snapshot(ticker)


def _fetch_company_facts(ticker: str) -> dict:
    from core.edgar_data import get_company_facts
    return get_company_facts(ticker)
