from fastapi import APIRouter

from backend.app.api.error_handling import raise_for_error_payload
from backend.app.api.job_submission import start_training_job_or_raise
from backend.app.application.model_lifecycle.training_payloads import build_dl_training_payload, build_ml_training_payload
from backend.app.application.model_lifecycle.service import (
    get_model_run_details,
    get_promotion_status,
    list_model_runs,
    promote_model_run,
    review_model_promotion,
)
from backend.app.schemas.requests import TrainDLRequest, TrainMLRequest


router = APIRouter(prefix="/model-lifecycle", tags=["model-lifecycle"])


@router.get("/status")
def model_lifecycle_status():
    ml_runs = list_model_runs("ml")
    dl_runs = list_model_runs("dl")
    return {
        "ml_ready": any(row.get("is_active") for row in ml_runs),
        "dl_ready": any(row.get("is_active") for row in dl_runs),
        "latest_ml_run": ml_runs[0] if ml_runs else None,
        "latest_dl_run": dl_runs[0] if dl_runs else None,
        "promotion": get_promotion_status(),
    }


@router.post("/train/ml")
def model_lifecycle_train_ml(payload: TrainMLRequest):
    return start_training_job_or_raise(
        model_type="ml",
        payload=build_ml_training_payload(payload),
        requested_by="anonymous",
    )


@router.post("/train/dl")
def model_lifecycle_train_dl(payload: TrainDLRequest):
    return start_training_job_or_raise(
        model_type="dl",
        payload=build_dl_training_payload(payload),
        requested_by="anonymous",
    )


@router.get("/runs")
def model_lifecycle_runs(model_type: str | None = None):
    if model_type:
        return {"items": list_model_runs(model_type)}
    return {"ml_runs": list_model_runs("ml"), "dl_runs": list_model_runs("dl")}


@router.get("/runs/{run_id}")
def model_lifecycle_run_details(run_id: str):
    return raise_for_error_payload(get_model_run_details(run_id), default_status=404)


@router.get("/promotion/status")
def model_lifecycle_promotion_status():
    return get_promotion_status()


@router.get("/promotion/review/{run_id}")
def model_lifecycle_promotion_review(run_id: str):
    return raise_for_error_payload(review_model_promotion(run_id), default_status=404)


@router.post("/promotion/activate/{run_id}")
def model_lifecycle_activate(run_id: str):
    return raise_for_error_payload(promote_model_run(run_id), default_status=400)
