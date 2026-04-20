from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.services.market_readiness import (
    get_latest_market_readiness,
    get_market_readiness_cycle,
    list_market_readiness_cycles,
)


router = APIRouter(prefix="/market-readiness", tags=["market-readiness"])


@router.get("/latest")
def market_readiness_latest():
    payload = get_latest_market_readiness()
    if payload is None:
        return {"status": "empty", "item": None}
    return {"status": "ok", "item": payload}


@router.get("/cycles")
def market_readiness_cycles(limit: int = Query(default=20, ge=1, le=100)):
    payload = list_market_readiness_cycles(limit=limit)
    return {
        "status": "ok",
        **payload,
    }


@router.get("/cycles/{cycle_id}")
def market_readiness_cycle(cycle_id: str):
    payload = get_market_readiness_cycle(cycle_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Market readiness cycle not found")
    return {
        "status": "ok",
        "item": payload,
    }
