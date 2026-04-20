from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.services.market_session_intelligence import get_market_session_snapshot


router = APIRouter(prefix="/market-session", tags=["market-session"])


@router.get("/status")
def market_session_status(refresh: bool = Query(default=False)):
    snapshot = get_market_session_snapshot(refresh=refresh)
    return {
        "status": "ok",
        "item": snapshot,
    }
