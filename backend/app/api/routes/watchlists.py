from fastapi import APIRouter

from backend.app.schemas.requests import SmartWatchlistRequest
from backend.app.services.smart_watchlists import build_dynamic_watchlists


router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.post("/dynamic")
def dynamic_watchlists(payload: SmartWatchlistRequest):
    return build_dynamic_watchlists(preset=payload.preset, limit=payload.limit)
