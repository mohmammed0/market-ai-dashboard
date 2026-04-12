from fastapi import APIRouter, Query

from backend.app.api.job_submission import submit_background_job_or_raise
from backend.app.schemas.requests import ScanRequest
from backend.app.services.background_jobs import JOB_TYPE_SCAN
from backend.app.services.job_workflows import run_scan_workflow


router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("")
def scan_watchlist(payload: ScanRequest, sync: bool = Query(default=False)):
    payload_dict = payload.model_dump()
    if sync:
        return run_scan_workflow(payload_dict)
    return submit_background_job_or_raise(
        job_type=JOB_TYPE_SCAN,
        payload=payload_dict,
        requested_by="anonymous",
    )
