from fastapi import APIRouter, Query

from backend.app.services.market_data import fetch_quote_snapshots


router = APIRouter(prefix="/live", tags=["live"])


@router.get("/quotes")
def get_live_quotes(symbols: list[str] = Query(default=[])):
    return fetch_quote_snapshots(symbols)
