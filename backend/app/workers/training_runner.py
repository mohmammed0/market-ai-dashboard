from __future__ import annotations

import json
import logging
import sys

from backend.app.application.model_lifecycle.service import train_dl_models, train_ml_models
from backend.app.core.logging_utils import configure_logging, get_logger, log_event
from backend.app.db.session import init_db
from backend.app.repositories.model_lifecycle import ModelLifecycleRepository
from backend.app.services.storage import dumps_json, loads_json, session_scope


configure_logging("INFO")
logger = get_logger(__name__)


def main(job_id: str) -> int:
    init_db(run_migrations=False)
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        job_row = repo.get_training_job_row(job_id)
        if job_row is None:
            log_event(logger, logging.ERROR, "training.job.missing", job_id=job_id)
            return 1
        payload = loads_json(job_row.payload_json)
        model_type = job_row.model_type

    try:
        if model_type == "dl":
            result = train_dl_models(**payload)
        else:
            result = train_ml_models(**payload)
        with session_scope() as session:
            repo = ModelLifecycleRepository(session)
            if result.get("error"):
                repo.mark_training_job_failed(job_id, error_message=result.get("error", "training failed"), result_json=dumps_json(result))
                log_event(logger, logging.ERROR, "training.job.failed", job_id=job_id, model_type=model_type, error=result.get("error"))
                return 1
            repo.mark_training_job_completed(job_id, result_json=dumps_json(result))
        log_event(logger, logging.INFO, "training.job.completed", job_id=job_id, model_type=model_type, run_id=result.get("run_id"))
        return 0
    except Exception as exc:
        with session_scope() as session:
            repo = ModelLifecycleRepository(session)
            repo.mark_training_job_failed(job_id, error_message=str(exc), result_json=json.dumps({"error": str(exc)}))
        log_event(logger, logging.ERROR, "training.job.exception", job_id=job_id, model_type=model_type, error=str(exc))
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("training_runner requires a job_id")
    raise SystemExit(main(sys.argv[1]))
