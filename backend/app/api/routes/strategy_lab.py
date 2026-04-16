from fastapi import APIRouter, Query

from backend.app.automation.service import run_strategy_evaluation_workflow
from backend.app.api.job_submission import submit_background_job_or_raise
from backend.app.services.continuous_learning import list_generated_strategy_candidates
from backend.app.services.experiment_tracker import get_tracking_status, list_experiment_runs
from backend.app.schemas.requests import StrategyEvaluationRequest
from backend.app.services.background_jobs import JOB_TYPE_STRATEGY_EVALUATION
from backend.app.services.strategy_lab import list_strategy_evaluations


router = APIRouter(prefix="/strategy-lab", tags=["strategy-lab"])


@router.get("/history")
def strategy_lab_history(limit: int = Query(default=20, ge=1, le=100)):
    return list_strategy_evaluations(limit=limit)


@router.get("/generated-candidates")
def generated_strategy_candidates(limit: int = Query(default=10, ge=1, le=50)):
    return list_generated_strategy_candidates(limit=limit)


@router.post("/evaluate")
def evaluate_strategy(payload: StrategyEvaluationRequest, sync: bool = Query(default=False)):
    payload_dict = payload.model_dump()
    if sync:
        return run_strategy_evaluation_workflow(payload_dict)
    return submit_background_job_or_raise(
        job_type=JOB_TYPE_STRATEGY_EVALUATION,
        payload=payload_dict,
        requested_by="anonymous",
    )


@router.get("/tracking")
def strategy_lab_tracking():
    """Experiment tracking status and recent tracked runs."""
    return {
        "tracking_status": get_tracking_status(),
        "recent_runs": list_experiment_runs("strategy_lab", limit=10),
    }


@router.get("/readiness")
def strategy_lab_readiness(limit: int = Query(default=20, ge=1, le=100)):
    """Classify recent strategy evaluations into readiness states.

    Returns each evaluation with a deterministic classification:
    exploratory, candidate, review_ready, or rejected — with
    reasons and the thresholds used for the decision.
    """
    from backend.app.services.strategy_readiness import get_readiness_summary
    return get_readiness_summary(limit=limit)
