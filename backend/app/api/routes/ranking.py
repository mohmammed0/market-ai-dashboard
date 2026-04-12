from fastapi import APIRouter, Query

from backend.app.api.error_handling import raise_for_error_payload, to_http_exception
from backend.app.api.job_submission import submit_background_job_or_raise
from backend.app.schemas.requests import AnalyzeRequest, ScanRequest
from backend.app.services.cached_analysis import get_base_analysis_result, get_base_analysis_results_batch
from backend.app.services.background_jobs import JOB_TYPE_RANKING_SCAN
from backend.app.services.job_workflows import run_ranking_scan_workflow
from core.ranking_service import rank_analysis, rank_scan_results, summarize_long_short


router = APIRouter(prefix="/ranking", tags=["ranking"])


@router.post("/analyze")
def rank_single(payload: AnalyzeRequest):
    try:
        result = get_base_analysis_result(payload.instrument, payload.start_date, payload.end_date)
        raise_for_error_payload(result, default_status=503)
        return rank_analysis(result)
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
