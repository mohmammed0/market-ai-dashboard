from fastapi import APIRouter, Query

from backend.app.api.job_submission import submit_background_job_or_raise
from backend.app.automation.service import (
    get_automation_runtime_status,
    run_automation_workflow,
)
from backend.app.schemas.requests import AutomationRunRequest
from backend.app.services.background_jobs import JOB_TYPE_AUTOMATION


router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/status")
def automation_status(limit: int = Query(default=20, ge=1, le=100)):
    return get_automation_runtime_status(limit=limit)


@router.post("/run")
def automation_run(payload: AutomationRunRequest, sync: bool = Query(default=False)):
    payload_dict = payload.model_dump()
    if sync:
        return run_automation_workflow(payload_dict)
    return submit_background_job_or_raise(
        job_type=JOB_TYPE_AUTOMATION,
        payload=payload_dict,
        requested_by="anonymous",
    )
