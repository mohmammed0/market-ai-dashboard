from fastapi import APIRouter, Query

from backend.app.services.breadth_engine import compute_market_breadth, compute_sector_rotation


router = APIRouter(prefix="/breadth", tags=["breadth"])


@router.get("/overview")
def breadth_overview(preset: str = "ALL_US_EQUITIES", limit: int = Query(default=40, ge=5, le=100)):
    return {
        "breadth": compute_market_breadth(preset=preset, limit=limit),
        "sector_rotation": compute_sector_rotation(),
    }
