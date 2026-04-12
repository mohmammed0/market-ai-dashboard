from fastapi import APIRouter

from backend.app.api.error_handling import raise_for_error_payload
from backend.app.application.model_lifecycle.service import get_promotion_status, promote_model_run, review_model_promotion


router = APIRouter(prefix="/models/promotion", tags=["models-promotion"])


@router.get("/status")
def promotion_status():
    return get_promotion_status()


@router.get("/review/{run_id}")
def promotion_review(run_id: str):
    return raise_for_error_payload(review_model_promotion(run_id), default_status=404)


@router.post("/promote/{run_id}")
def promotion_apply(run_id: str):
    return raise_for_error_payload(promote_model_run(run_id), default_status=400)
