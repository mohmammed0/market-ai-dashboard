from fastapi import APIRouter, Query

from backend.app.market_data.service import fetch_quote_snapshots
from backend.app.services.pipeline_live import get_pipeline_feed


router = APIRouter(prefix="/live", tags=["live"])


@router.get("/quotes")
def get_live_quotes(symbols: list[str] = Query(default=[])):
    return fetch_quote_snapshots(symbols)


@router.get("/pipeline")
def get_live_pipeline(
    limit_events: int = Query(default=40, ge=5, le=120),
    limit_cycles: int = Query(default=8, ge=1, le=30),
):
    return get_pipeline_feed(limit_events=limit_events, limit_cycles=limit_cycles)
