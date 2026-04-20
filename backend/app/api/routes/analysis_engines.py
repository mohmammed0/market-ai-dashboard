from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.services.analysis_engines import get_analysis_engines_status


router = APIRouter(prefix="/analysis-engines", tags=["analysis-engines"])


@router.get("/status")
def analysis_engines_status(latest_nonempty: bool = Query(default=True)):
    return {
        "status": "ok",
        "item": get_analysis_engines_status(latest_nonempty=latest_nonempty),
    }
