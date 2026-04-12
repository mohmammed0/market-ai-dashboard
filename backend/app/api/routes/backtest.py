from fastapi import APIRouter, Query

from backend.app.api.job_submission import submit_background_job_or_raise
from backend.app.schemas.requests import BacktestRequest
from backend.app.services.background_jobs import JOB_TYPE_BACKTEST, JOB_TYPE_BACKTEST_VECTORBT
from backend.app.services.job_workflows import run_backtest_workflow, run_vectorbt_backtest_workflow


router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("")
def run_backtest(payload: BacktestRequest, sync: bool = Query(default=False)):
    payload_dict = payload.model_dump()
    if sync:
        return run_backtest_workflow(payload_dict)
    return submit_background_job_or_raise(
        job_type=JOB_TYPE_BACKTEST,
        payload=payload_dict,
        requested_by="anonymous",
    )


@router.post("/vectorbt")
def run_backtest_vectorbt(payload: BacktestRequest, sync: bool = Query(default=False)):
    payload_dict = payload.model_dump()
    if sync:
        return run_vectorbt_backtest_workflow(payload_dict)
    return submit_background_job_or_raise(
        job_type=JOB_TYPE_BACKTEST_VECTORBT,
        payload=payload_dict,
        requested_by="anonymous",
    )
