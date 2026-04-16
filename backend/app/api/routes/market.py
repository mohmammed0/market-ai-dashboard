from fastapi import APIRouter, HTTPException, Query

from backend.app.market_data.service import (
    get_market_data_provider_status,
    get_market_overview,
    get_market_symbol_snapshot,
    get_market_universe_facets,
    list_currency_references,
    refresh_market_universe,
    resolve_universe_preset,
    search_market_universe,
)
from backend.app.readmodels import build_market_readmodel


router = APIRouter(prefix="/market", tags=["market"])


@router.get("/universe/search")
def search_universe(
    q: str | None = Query(default=None),
    exchange: str | None = Query(default=None),
    type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    return search_market_universe(q=q, exchange=exchange, security_type=type, category=category, limit=limit, include_quotes=True)


@router.get("/universe/facets")
def universe_facets():
    return get_market_universe_facets()


@router.post("/universe/refresh")
def refresh_universe(force: bool = Query(default=True)):
    try:
        return refresh_market_universe(force=force)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/universe/preset")
def market_universe_preset(
    preset: str = Query(...),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        return resolve_universe_preset(preset=preset, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/currencies")
def market_currencies(
    limit: int = Query(default=100, ge=1, le=500),
    major_only: bool = Query(default=False),
):
    return list_currency_references(limit=limit, major_only=major_only)


@router.get("/overview")
def market_overview():
    return get_market_overview()


@router.get("/readmodel")
def market_readmodel(
    symbols: str | None = Query(default=None),
):
    symbol_list = [item.strip().upper() for item in str(symbols or "").split(",") if item.strip()]
    return build_market_readmodel(symbols=symbol_list or None)


@router.get("/symbol/{ticker}/snapshot")
def market_symbol_snapshot(ticker: str):
    return get_market_symbol_snapshot(ticker)

@router.get("/data-provider")
def market_data_provider_status():
    """Return the active market data provider chain and each provider's readiness."""
    return get_market_data_provider_status()
