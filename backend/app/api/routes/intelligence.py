from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.api.error_handling import raise_for_error_payload
from backend.app.api.job_submission import start_training_job_or_raise, submit_background_job_or_raise
from backend.app.application.model_lifecycle.training_payloads import build_dl_training_payload, build_ml_training_payload
from backend.app.application.model_lifecycle.service import (
    get_model_run_details,
    list_model_runs,
)
from backend.app.schemas.requests import (
    BatchInferenceRequest,
    InferenceRequest,
    ModelBacktestRequest,
    TrainDLRequest,
    TrainMLRequest,
)
from backend.app.services.background_jobs import JOB_TYPE_INFERENCE_BATCH, submit_background_job
from backend.app.services.ai_overlay import get_overlay_status
from backend.app.services.decision_support import build_decision_payload
from backend.app.services.explainability import build_signal_explanation
from backend.app.services.job_workflows import run_batch_inference_workflow
from backend.app.services.signal_runtime import build_smart_analysis
from backend.app.services.tool_gateway import get_tool_gateway
from core.backtest_service import backtest_symbol_enhanced, run_vectorbt_backtest


router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/status")
def intelligence_status():
    ml_runs = list_model_runs("ml")
    dl_runs = list_model_runs("dl")
    return {
        "ml_ready": any(row.get("is_active") for row in ml_runs),
        "dl_ready": any(row.get("is_active") for row in dl_runs),
        "latest_ml_run": ml_runs[0] if ml_runs else None,
        "latest_dl_run": dl_runs[0] if dl_runs else None,
    }


@router.get("/overlay/status")
def ai_overlay_status():
    """AI overlay runtime status: provider state, call counts, latency, fallback stats."""
    overlay = get_overlay_status()
    gw = get_tool_gateway()
    return {
        "overlay": overlay,
        "tool_gateway": {
            "registered_tools": gw.list_tools(),
            "call_counters": gw.get_counters(),
        },
    }


@router.post("/train/ml")
def train_ml(payload: TrainMLRequest):
    return start_training_job_or_raise(
        model_type="ml",
        payload=build_ml_training_payload(payload),
        requested_by="anonymous",
    )


@router.post("/train/dl")
def train_dl(payload: TrainDLRequest):
    return start_training_job_or_raise(
        model_type="dl",
        payload=build_dl_training_payload(payload),
        requested_by="anonymous",
    )


@router.get("/models")
def get_models():
    return {
        "ml_runs": list_model_runs("ml"),
        "dl_runs": list_model_runs("dl"),
    }


@router.get("/models/{run_id}")
def get_model_details(run_id: str):
    payload = get_model_run_details(run_id)
    return raise_for_error_payload(payload, default_status=404)


@router.post("/infer")
def infer(payload: InferenceRequest):
    return build_smart_analysis(
        payload.symbol,
        payload.start_date,
        payload.end_date,
        include_dl=payload.include_dl,
        include_ensemble=payload.include_ensemble,
    )


@router.post("/explain")
def explain_signal(payload: InferenceRequest):
    result = build_smart_analysis(
        payload.symbol,
        payload.start_date,
        payload.end_date,
        include_dl=payload.include_dl,
        include_ensemble=payload.include_ensemble,
    )
    return {
        "analysis": result,
        "explanation": build_signal_explanation(result),
    }


@router.post("/decision")
def decision_surface(payload: InferenceRequest):
    return build_decision_payload(
        payload.symbol,
        payload.start_date,
        payload.end_date,
        include_dl=payload.include_dl,
        include_ensemble=payload.include_ensemble,
    )


@router.post("/infer/batch")
def infer_batch(payload: BatchInferenceRequest, sync: bool = Query(default=False)):
    payload_dict = payload.model_dump()
    if sync:
        return run_batch_inference_workflow(payload_dict)
    return submit_background_job_or_raise(
        job_type=JOB_TYPE_INFERENCE_BATCH,
        payload=payload_dict,
        requested_by="anonymous",
    )


@router.post("/backtest")
def model_aware_backtest(payload: ModelBacktestRequest):
    mode = str(payload.mode or "ml").lower().strip()
    classic = backtest_symbol_enhanced(
        instrument=payload.instrument,
        start_date=payload.start_date,
        end_date=payload.end_date,
        hold_days=payload.hold_days,
    )
    vectorbt = run_vectorbt_backtest(
        instrument=payload.instrument,
        start_date=payload.start_date,
        end_date=payload.end_date,
        hold_days=payload.hold_days,
    )
    smart = build_smart_analysis(payload.instrument, payload.start_date, payload.end_date, include_dl=True, include_ensemble=True)
    selected = smart.get("ml_output") if mode == "ml" else smart.get("dl_output") if mode == "dl" else smart.get("ensemble_output")
    return {
        "instrument": payload.instrument,
        "mode": mode,
        "classic_summary": {
            "trades": classic.get("trades"),
            "overall_win_rate_pct": classic.get("overall_win_rate_pct"),
            "avg_trade_return_pct": classic.get("avg_trade_return_pct"),
        },
        "vectorbt_summary": {
            "trades": vectorbt.get("trades"),
            "total_return_pct": (vectorbt.get("returns_stats") or {}).get("total_return_pct"),
            "max_drawdown_pct": (vectorbt.get("drawdown_stats") or {}).get("max_drawdown_pct"),
        },
        "smart_output": selected,
        "smart_analysis": {
            "ml_output": smart.get("ml_output"),
            "dl_output": smart.get("dl_output"),
            "ensemble_output": smart.get("ensemble_output"),
        },
    }
