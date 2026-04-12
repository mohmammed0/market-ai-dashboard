from fastapi import APIRouter, Query

from backend.app.api.job_submission import submit_background_job_or_raise
from backend.app.schemas.requests import AutomationRunRequest
from backend.app.services import get_scheduler_status
from backend.app.services.automation_hub import get_automation_status
from backend.app.services.background_jobs import JOB_TYPE_AUTOMATION
from backend.app.services.continuous_learning import get_continuous_learning_status
from backend.app.services.job_workflows import run_automation_workflow
from core.market_data_providers import get_market_data_provider_status


router = APIRouter(prefix="/automation", tags=["automation"])


@router.get("/status")
def automation_status(limit: int = Query(default=20, ge=1, le=100)):
    return {
        "automation": get_automation_status(limit=limit),
        "continuous_learning": get_continuous_learning_status(limit=limit),
        "scheduler": get_scheduler_status(),
        "market_data_provider": get_market_data_provider_status(),
    }


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
