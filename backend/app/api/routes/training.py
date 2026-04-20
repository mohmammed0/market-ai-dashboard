from fastapi import APIRouter, Query

from backend.app.api.error_handling import to_http_exception
from backend.app.api.job_submission import start_training_job_or_raise
from backend.app.application.model_lifecycle.training_payloads import (
    list_training_workflow_templates,
    resolve_training_job_config,
)
from backend.app.application.model_lifecycle.training_jobs import get_training_dashboard, get_training_job, list_training_jobs
from backend.app.schemas.requests import TrainingJobStartRequest


router = APIRouter(prefix="/training", tags=["training"])


@router.get("/jobs")
def training_jobs(limit: int = Query(default=20, ge=1, le=100)):
    return list_training_jobs(limit=limit)


@router.get("/dashboard")
def training_dashboard(limit: int = Query(default=25, ge=5, le=100)):
    return get_training_dashboard(limit=limit)


@router.get("/workflow-templates")
def training_workflow_templates(model_type: str | None = Query(default=None)):
    return list_training_workflow_templates(model_type=model_type)


@router.get("/jobs/{job_id}")
def training_job(job_id: str):
    try:
        return get_training_job(job_id)
    except Exception as exc:
        raise to_http_exception(exc, default_status=404) from exc


@router.post("/jobs/start")
def training_job_start(payload: TrainingJobStartRequest):
    resolved = resolve_training_job_config(payload.model_type, payload)
    response = start_training_job_or_raise(
        model_type=resolved["model_type"],
        payload=resolved["payload"],
        requested_by="anonymous",
    )
    response["workflow_template"] = resolved["template"]
    return response
