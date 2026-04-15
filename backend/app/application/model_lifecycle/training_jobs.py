from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from backend.app.config import (
    REMOTE_TRAINING_ENABLED,
    REMOTE_WORKER_STALE_SECONDS,
    ROOT_DIR,
    TRAINING_JOB_MAX_ACTIVE,
    TRAINING_JOB_STALE_PENDING_SECONDS,
    TRAINING_RUNNER_PYTHON,
    TRAINING_SUBPROCESS_ENABLED,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.repositories.model_lifecycle import ModelLifecycleRepository
from backend.app.services.process_guardrails import is_process_running
from backend.app.services.storage import dumps_json, session_scope
from core.runtime_paths import TRAINING_LOGS_DIR


logger = get_logger(__name__)


class TrainingJobSubmissionError(RuntimeError):
    status_code = 400


class TrainingJobCapacityError(TrainingJobSubmissionError):
    status_code = 429


class TrainingJobLaunchError(TrainingJobSubmissionError):
    status_code = 503


def _training_job_log_path(job_id: str) -> Path:
    TRAINING_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return TRAINING_LOGS_DIR / f"{job_id}.log"


def _normalize_training_payload(payload: dict) -> str:
    return json.dumps(payload or {}, default=str, sort_keys=True, separators=(",", ":"))


def _reconcile_active_training_jobs(repo: ModelLifecycleRepository) -> int:
    stale_before = datetime.utcnow() - timedelta(seconds=max(int(TRAINING_JOB_STALE_PENDING_SECONDS), 30))
    changed = 0
    for row in repo.list_active_training_job_rows():
        normalized_status = str(row.status or "").strip().lower()
        # Remote-claimed jobs (worker_id set) use heartbeat-based timeout, not PID checks.
        if normalized_status == "running" and getattr(row, "worker_id", None):
            continue
        if normalized_status == "running" and row.pid and not is_process_running(row.pid):
            repo.mark_training_job_failed(
                row.job_id,
                error_message="Training worker process is no longer running.",
                result_json=dumps_json({"error": "Training worker process is no longer running."}),
            )
            changed += 1
        elif normalized_status == "queued" and row.requested_at and row.requested_at <= stale_before:
            # Remote mode: jobs can sit in queued indefinitely waiting for a worker.
            # Only time out queued jobs in local-subprocess mode.
            if REMOTE_TRAINING_ENABLED:
                continue
            repo.mark_training_job_failed(
                row.job_id,
                error_message="Training job launch timed out before the worker started.",
                result_json=dumps_json({"error": "Training job launch timed out before the worker started."}),
            )
            changed += 1
    # Heartbeat reconciliation for remote workers (independent of subprocess mode).
    changed += repo.release_stale_remote_jobs(stale_seconds=REMOTE_WORKER_STALE_SECONDS)
    return changed


def start_training_job(*, model_type: str, payload: dict, requested_by: str | None = "api") -> dict:
    normalized_type = str(model_type or "ml").strip().lower()
    if normalized_type not in {"ml", "dl"}:
        raise TrainingJobSubmissionError(f"Unsupported model type: {model_type}")
    if not REMOTE_TRAINING_ENABLED and not TRAINING_SUBPROCESS_ENABLED:
        raise TrainingJobLaunchError("Training subprocess execution is disabled by configuration.")

    payload_json = _normalize_training_payload(payload)

    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        _reconcile_active_training_jobs(repo)
        existing = repo.find_active_training_job(model_type=normalized_type, payload_json=payload_json)
        if existing is not None:
            return {
                "accepted": True,
                "deduplicated": True,
                "job": existing.model_dump(),
                "log_path": str(_training_job_log_path(existing.job_id)),
            }

        active_jobs = repo.count_active_training_jobs()
        if active_jobs >= TRAINING_JOB_MAX_ACTIVE:
            raise TrainingJobCapacityError(
                f"Training job capacity reached ({active_jobs}/{TRAINING_JOB_MAX_ACTIVE})."
            )

        job_id = f"train-{normalized_type}-{uuid4().hex[:12]}"
        created = repo.create_training_job(
            job_id=job_id,
            model_type=normalized_type,
            payload_json=payload_json,
            requested_by=requested_by,
        )

    # Remote GPU worker mode: just leave the job in 'queued' state; the remote
    # worker polls /api/training/worker/next-job and executes it there.
    if REMOTE_TRAINING_ENABLED:
        log_event(
            logger,
            logging.INFO,
            "training.job.queued_for_remote_worker",
            job_id=job_id,
            model_type=normalized_type,
        )
        return {
            "accepted": True,
            "deduplicated": False,
            "remote": True,
            "job": created.model_dump(),
            "log_path": str(_training_job_log_path(job_id)),
        }

    command = [TRAINING_RUNNER_PYTHON, "-m", "backend.app.workers.training_runner", job_id]
    log_path = _training_job_log_path(job_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(f"[launcher] job_id={job_id} model_type={normalized_type}\n")
    creationflags = 0
    stdout_handle = log_path.open("a", encoding="utf-8")
    popen_kwargs = {
        "cwd": str(ROOT_DIR),
        "stdout": stdout_handle,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "env": os.environ.copy(),
    }
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **popen_kwargs)
    except Exception as exc:
        with session_scope() as session:
            repo = ModelLifecycleRepository(session)
            repo.mark_training_job_failed(
                job_id,
                error_message=str(exc),
                result_json=dumps_json({"error": str(exc)}),
            )
        raise TrainingJobLaunchError(f"Failed to start training job {job_id}: {exc}") from exc
    finally:
        try:
            stdout_handle.close()
        except Exception:
            pass
    if process.pid in (None, 0):
        with session_scope() as session:
            repo = ModelLifecycleRepository(session)
            repo.mark_training_job_failed(job_id, error_message="Training worker failed to report a PID.")
        raise TrainingJobLaunchError(f"Failed to start training job {job_id}: worker PID unavailable.")

    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        running = repo.mark_training_job_running(job_id, pid=process.pid)

    log_event(
        logger,
        logging.INFO,
        "training.job.started",
        job_id=job_id,
        model_type=normalized_type,
        pid=process.pid,
        log_path=str(log_path),
    )
    return {
        "accepted": True,
        "deduplicated": False,
        "job": None if running is None else running.model_dump(),
        "log_path": str(log_path),
    }


def reconcile_stale_training_jobs() -> int:
    """Open a session and reconcile any crashed or timed-out training jobs.

    Intended to be called by the scheduler on a fixed interval so that stale
    training jobs are cleaned up even when no client polls status endpoints.
    Returns the number of jobs that were transitioned to *failed*.
    """
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        return _reconcile_active_training_jobs(repo)


def list_training_jobs(limit: int = 20) -> dict:
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        _reconcile_active_training_jobs(repo)
        items = [row.model_dump() for row in repo.list_training_jobs(limit=limit)]
    return {"items": items, "count": len(items)}


def get_training_job(job_id: str) -> dict:
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        _reconcile_active_training_jobs(repo)
        row = repo.get_training_job(job_id)
    if row is None:
        raise LookupError(f"Training job not found: {job_id}")
    payload = row.model_dump()
    payload["log_path"] = str(_training_job_log_path(job_id))
    return payload


def get_training_dashboard(limit: int = 25) -> dict:
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        _reconcile_active_training_jobs(repo)
        jobs = []
        for row in repo.list_training_jobs(limit=limit):
            payload = row.model_dump()
            payload["log_path"] = str(_training_job_log_path(payload["job_id"]))
            jobs.append(payload)
        ml_runs = [row.model_dump() for row in repo.list_runs(model_type="ml", limit=10)]
        dl_runs = [row.model_dump() for row in repo.list_runs(model_type="dl", limit=10)]

    status_counts = {
        "queued": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
    }
    for item in jobs:
        normalized = str(item.get("status") or "").strip().lower()
        if normalized == "error":
            normalized = "failed"
        if normalized not in status_counts:
            status_counts[normalized] = 0
        status_counts[normalized] += 1

    latest_job = jobs[0] if jobs else None
    latest_runs = {
        "ml": ml_runs[0] if ml_runs else None,
        "dl": dl_runs[0] if dl_runs else None,
    }

    return {
        "status_counts": status_counts,
        "latest_job": latest_job,
        "latest_runs": latest_runs,
        "jobs": jobs,
        "runs": {
            "ml_runs": ml_runs,
            "dl_runs": dl_runs,
        },
    }
