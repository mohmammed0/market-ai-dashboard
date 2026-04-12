from __future__ import annotations

import logging

from backend.app.core.logging_utils import get_logger, log_event
from backend.app.config import MODEL_PROMOTION_MAX_DRAWDOWN_PCT, MODEL_PROMOTION_MIN_F1, MODEL_PROMOTION_MIN_TEST_ACCURACY
from backend.app.domain.model_lifecycle.contracts import PromotionReview
from backend.app.repositories.model_lifecycle import ModelLifecycleRepository
from backend.app.services.dl_lab import train_sequence_model
from backend.app.services.ml_lab import get_model_run, train_baseline_models
from backend.app.services.storage import session_scope

logger = get_logger(__name__)


def train_ml_models(**kwargs):
    log_event(logger, logging.INFO, "model_lifecycle.train_ml.started", symbols=len(kwargs.get("symbols") or []))
    result = train_baseline_models(**kwargs)
    log_event(logger, logging.INFO, "model_lifecycle.train_ml.completed", run_id=result.get("run_id"), status=result.get("status"), error=result.get("error"))
    return result


def train_dl_models(**kwargs):
    log_event(logger, logging.INFO, "model_lifecycle.train_dl.started", symbols=len(kwargs.get("symbols") or []))
    result = train_sequence_model(**kwargs)
    log_event(logger, logging.INFO, "model_lifecycle.train_dl.completed", run_id=result.get("run_id"), status=result.get("status"), error=result.get("error"))
    return result


def list_model_runs(model_type: str | None = None):
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        return [row.model_dump() for row in repo.list_runs(model_type=model_type)]


def get_model_run_details(run_id: str):
    return get_model_run(run_id)


def review_model_promotion(run_id: str) -> dict:
    details = get_model_run(run_id)
    if details.get("error"):
        return details

    metrics = details.get("metrics") or {}
    validation_f1 = float(metrics.get("validation_macro_f1") or metrics.get("precision_recall_f1_macro", {}).get("f1") or 0.0)
    test_accuracy = float(metrics.get("test_accuracy") or 0.0)
    drawdown = float((metrics.get("drawdown_stats") or {}).get("max_drawdown_pct") or 0.0)
    reasons = []
    approved = True

    if validation_f1 < MODEL_PROMOTION_MIN_F1:
        approved = False
        reasons.append(f"Validation F1 {validation_f1:.3f} is below the promotion floor of {MODEL_PROMOTION_MIN_F1:.2f}.")
    else:
        reasons.append(f"Validation F1 cleared the floor at {validation_f1:.3f}.")

    if test_accuracy and test_accuracy < MODEL_PROMOTION_MIN_TEST_ACCURACY:
        approved = False
        reasons.append(f"Test accuracy {test_accuracy:.3f} is below the promotion floor of {MODEL_PROMOTION_MIN_TEST_ACCURACY:.2f}.")
    elif test_accuracy:
        reasons.append(f"Test accuracy cleared the floor at {test_accuracy:.3f}.")

    if drawdown and drawdown > MODEL_PROMOTION_MAX_DRAWDOWN_PCT:
        approved = False
        reasons.append(f"Recorded drawdown {drawdown:.2f}% exceeds the promotion ceiling of {MODEL_PROMOTION_MAX_DRAWDOWN_PCT:.2f}%.")

    return PromotionReview(run_id=run_id, model_type=details.get("model_type"), approved=approved, reasons=reasons, metrics=metrics).model_dump()


def get_promotion_status() -> dict:
    runs = []
    for model_type in ("ml", "dl"):
        runs.extend(list_model_runs(model_type))
    reviews = [review_model_promotion(row["run_id"]) for row in runs[:10]]
    return {"items": reviews, "recommended": [item for item in reviews if item.get("approved")], "active_candidates": [row for row in runs if row.get("is_active")]}


def promote_model_run(run_id: str) -> dict:
    review = review_model_promotion(run_id)
    if review.get("error"):
        return review
    if not review.get("approved"):
        return {"error": "Model run did not pass promotion checks.", "review": review}
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        activation = repo.set_active(run_id, active=True)
        if activation is None:
            return {"error": f"Model run not found: {run_id}"}
        return {"review": review, "activation": activation.model_dump()}
