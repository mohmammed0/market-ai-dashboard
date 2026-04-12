from __future__ import annotations

from backend.app.api.error_handling import to_http_exception
from backend.app.application.model_lifecycle.training_jobs import start_training_job
from backend.app.services.background_jobs import submit_background_job


def submit_background_job_or_raise(*, job_type: str, payload: dict, requested_by: str | None = "api") -> dict:
    try:
        return submit_background_job(job_type=job_type, payload=payload, requested_by=requested_by)
    except Exception as exc:
        raise to_http_exception(exc, default_status=503) from exc


def start_training_job_or_raise(*, model_type: str, payload: dict, requested_by: str | None = "api") -> dict:
    try:
        return start_training_job(model_type=model_type, payload=payload, requested_by=requested_by)
    except Exception as exc:
        raise to_http_exception(exc, default_status=503) from exc
