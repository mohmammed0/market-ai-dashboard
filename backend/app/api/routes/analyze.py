from fastapi import APIRouter

from backend.app.api.error_handling import raise_for_error_payload, to_http_exception
from backend.app.schemas.requests import AnalyzeRequest
from backend.app.services.cached_analysis import get_ranked_analysis_result


router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("")
def analyze(payload: AnalyzeRequest):
    try:
        result = get_ranked_analysis_result(
            instrument=payload.instrument,
            start_date=payload.start_date,
            end_date=payload.end_date,
            include_ml=True,
            include_dl=True,
        )
        return raise_for_error_payload(result, default_status=503)
    except Exception as exc:
        raise to_http_exception(exc, default_status=503) from exc
