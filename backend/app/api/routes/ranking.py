from fastapi import APIRouter, Query

from backend.app.api.error_handling import raise_for_error_payload, to_http_exception
from backend.app.api.job_submission import submit_background_job_or_raise
from backend.app.schemas.requests import AnalyzeRequest, ScanRequest
from backend.app.services.background_jobs import JOB_TYPE_RANKING_SCAN
from backend.app.strategy.service import rank_single_analysis, run_ranking_scan_workflow


router = APIRouter(prefix="/ranking", tags=["ranking"])


@router.post("/analyze")
def rank_single(payload: AnalyzeRequest):
    try:
        result = rank_single_analysis(payload.instrument, payload.start_date, payload.end_date)
        return raise_for_error_payload(result, default_status=503)
    except Exception as exc:
        raise to_http_exception(exc, default_status=503) from exc


@router.post("/scan")
def rank_scan(payload: ScanRequest, sync: bool = Query(default=False)):
    payload_dict = payload.model_dump()
    if sync:
        return run_ranking_scan_workflow(payload_dict)
    return submit_background_job_or_raise(
        job_type=JOB_TYPE_RANKING_SCAN,
        payload=payload_dict,
        requested_by="anonymous",
    )
