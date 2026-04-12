from fastapi import APIRouter

from backend.app.schemas.requests import OptimizerRequest
from core.optimizer_service import optimize_symbol


router = APIRouter(prefix="/optimizer", tags=["optimizer"])


@router.post("/light")
def run_light_optimizer(payload: OptimizerRequest):
    df = optimize_symbol(
        instrument=payload.instrument,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    return {
        "instrument": payload.instrument,
        "items": [] if df is None or df.empty else df.to_dict(orient="records"),
    }
