from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from backend.app.config import (
    BACKGROUND_JOB_MAX_ACTIVE_PER_TYPE,
    BACKGROUND_JOB_MAX_ACTIVE_TOTAL,
    BACKGROUND_JOB_STALE_PENDING_SECONDS,
    ROOT_DIR,
    TRAINING_RUNNER_PYTHON,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.repositories.jobs import BackgroundJobRepository
from backend.app.services.job_workflows import (
    run_automation_workflow,
    run_backtest_workflow,
    run_batch_inference_workflow,
    run_paper_signal_refresh_workflow,
    run_ranking_scan_workflow,
    run_scan_workflow,
    run_strategy_evaluation_workflow,
    run_vectorbt_backtest_workflow,
)
from backend.app.services.process_guardrails import is_process_running
from backend.app.services.storage import dumps_json, session_scope
from core.runtime_paths import BACKGROUND_JOB_LOGS_DIR


logger = get_logger(__name__)

BACKGROUND_JOB_DEDUP_SECONDS = 20

JOB_TYPE_AUTOMATION = "automation_run"
JOB_TYPE_SCAN = "scan_batch"
JOB_TYPE_RANKING_SCAN = "ranking_scan_batch"
JOB_TYPE_BACKTEST = "backtest_classic"
JOB_TYPE_BACKTEST_VECTORBT = "backtest_vectorbt"
JOB_TYPE_STRATEGY_EVALUATION = "strategy_evaluation"
JOB_TYPE_PAPER_REFRESH = "paper_signal_refresh"
JOB_TYPE_INFERENCE_BATCH = "intelligence_infer_batch"

JOB_EXECUTORS = {
    JOB_TYPE_AUTOMATION: run_automation_workflow,
    JOB_TYPE_SCAN: run_scan_workflow,
    JOB_TYPE_RANKING_SCAN: run_ranking_scan_workflow,
    JOB_TYPE_BACKTEST: run_backtest_workflow,
    JOB_TYPE_BACKTEST_VECTORBT: run_vectorbt_backtest_workflow,
    JOB_TYPE_STRATEGY_EVALUATION: run_strategy_evaluation_workflow,
    JOB_TYPE_PAPER_REFRESH: run_paper_signal_refresh_workflow,
    JOB_TYPE_INFERENCE_BATCH: run_batch_inference_workflow,
}


class BackgroundJobSubmissionError(RuntimeError):
    status_code = 400


class BackgroundJobCapacityError(BackgroundJobSubmissionError):
    status_code = 429


class BackgroundJobLaunchError(BackgroundJobSubmissionError):
    status_code = 503


def _job_log_path(job_id: str) -> Path:
    BACKGROUND_JOB_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return BACKGROUND_JOB_LOGS_DIR / f"{job_id}.log"


def _normalize_job_type(job_type: str) -> str:
    normalized = str(job_type or "").strip().lower()
    if normalized not in JOB_EXECUTORS:
        raise ValueError(f"Unsupported background job type: {job_type}")
    return normalized


def _payload_hash(job_type: str, payload: dict) -> str:
    normalized = json.dumps(
        {"type": _normalize_job_type(job_type), "payload": payload or {}},
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _summarize_result(job_type: str, result: dict) -> dict:
    if not isinstance(result, dict):
        return {"ok": False, "detail": "Job result is not a JSON object."}

    if job_type == JOB_TYPE_AUTOMATION:
        return {
            "status": result.get("status"),
            "job_name": result.get("job_name"),
            "artifacts_count": len(result.get("artifacts", []) or []),
            "detail": result.get("detail"),
        }
    if job_type in {JOB_TYPE_SCAN, JOB_TYPE_RANKING_SCAN, JOB_TYPE_INFERENCE_BATCH}:
        items = result.get("items", []) or []
        summary = result.get("summary", {}) or {}
        return {
            "items": len(items),
            "top_pick": summary.get("top_pick"),
            "long_candidates": len(summary.get("top_longs", []) or []),
            "short_candidates": len(summary.get("top_shorts", []) or []),
        }
    if job_type in {JOB_TYPE_BACKTEST, JOB_TYPE_BACKTEST_VECTORBT}:
        returns_stats = result.get("returns_stats", {}) or {}
        drawdown_stats = result.get("drawdown_stats", {}) or {}
        return {
            "instrument": result.get("instrument"),
            "engine": result.get("engine", "classic"),
            "trades": result.get("trades"),
            "overall_win_rate_pct": result.get("overall_win_rate_pct"),
            "total_return_pct": returns_stats.get("total_return_pct"),
            "max_drawdown_pct": drawdown_stats.get("max_drawdown_pct"),
            "error": result.get("error"),
        }
    if job_type == JOB_TYPE_STRATEGY_EVALUATION:
        leaderboard = result.get("leaderboard", []) or []
        return {
            "instrument": result.get("instrument"),
            "run_id": result.get("run_id"),
            "modes": len(leaderboard),
            "best_mode": None if not leaderboard else leaderboard[0].get("mode"),
            "error": result.get("error"),
        }
    if job_type == JOB_TYPE_PAPER_REFRESH:
        portfolio = result.get("portfolio", {}) or {}
        return {
            "symbols": len(result.get("items", []) or []),
            "open_positions": (portfolio.get("summary") or {}).get("open_positions"),
            "recent_alerts": len((result.get("alerts") or {}).get("items", []) or []),
        }
    return {"status": "completed"}


def _spawn_background_job_process(job_id: str) -> int:
    command = [TRAINING_RUNNER_PYTHON, "-m", "backend.app.workers.job_runner", job_id]
    log_path = _job_log_path(job_id)
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(f"[launcher] job_id={job_id}\n")
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
    finally:
        try:
            stdout_handle.close()
        except Exception:
            pass
    return int(process.pid or 0)


def _reconcile_active_jobs(repo: BackgroundJobRepository) -> int:
    stale_before = datetime.utcnow() - timedelta(seconds=max(int(BACKGROUND_JOB_STALE_PENDING_SECONDS), 30))
    changed = 0
    for row in repo.list_active_job_rows():
        normalized_status = str(row.status or "").strip().lower()
        if normalized_status == "running" and row.pid and not is_process_running(row.pid):
            repo.mark_job_failed(
                row.job_id,
                error_message="Background worker process is no longer running.",
                result_json=dumps_json({"error": "Background worker process is no longer running."}),
                result_summary_json=dumps_json({"error": "Worker process terminated unexpectedly."}),
            )
            changed += 1
        elif normalized_status == "pending" and row.created_at and row.created_at <= stale_before:
            repo.mark_job_failed(
                row.job_id,
                error_message="Background job launch timed out before the worker started.",
                result_json=dumps_json({"error": "Background job launch timed out before the worker started."}),
                result_summary_json=dumps_json({"error": "Launch timed out."}),
            )
            changed += 1
    return changed


def submit_background_job(
    *,
    job_type: str,
    payload: dict,
    requested_by: str | None = "api",
    dedupe_seconds: int = BACKGROUND_JOB_DEDUP_SECONDS,
) -> dict:
    normalized_type = _normalize_job_type(job_type)
    safe_payload = dict(payload or {})
    payload_json = dumps_json(safe_payload)
    payload_hash = _payload_hash(normalized_type, safe_payload)

    with session_scope() as session:
        repo = BackgroundJobRepository(session)
        _reconcile_active_jobs(repo)
        existing = repo.find_active_duplicate(
            job_type=normalized_type,
            payload_hash=payload_hash,
        )
        if existing is not None:
            existing["accepted"] = True
            existing["deduplicated"] = True
            existing["log_path"] = str(_job_log_path(existing["job_id"]))
            existing["poll_url"] = f"/api/jobs/{existing['job_id']}"
            log_event(
                logger,
                logging.INFO,
                "background_job.deduplicated",
                job_id=existing["job_id"],
                job_type=normalized_type,
            )
            return existing

        active_total = repo.count_active_jobs()
        if active_total >= BACKGROUND_JOB_MAX_ACTIVE_TOTAL:
            raise BackgroundJobCapacityError(
                f"Background job capacity reached ({active_total}/{BACKGROUND_JOB_MAX_ACTIVE_TOTAL})."
            )

        active_same_type = repo.count_active_jobs(job_type=normalized_type)
        if active_same_type >= BACKGROUND_JOB_MAX_ACTIVE_PER_TYPE:
            raise BackgroundJobCapacityError(
                f"Background job capacity reached for {normalized_type} ({active_same_type}/{BACKGROUND_JOB_MAX_ACTIVE_PER_TYPE})."
            )

        job_id = f"job-{normalized_type}-{uuid4().hex[:12]}"
        created = repo.create_job(
            job_id=job_id,
            job_type=normalized_type,
            payload_json=payload_json,
            payload_hash=payload_hash,
            requested_by=requested_by,
        )

    try:
        pid = _spawn_background_job_process(created["job_id"])
    except Exception as exc:
        with session_scope() as session:
            repo = BackgroundJobRepository(session)
            created = repo.mark_job_failed(
                created["job_id"],
                error_message=str(exc),
                result_json=dumps_json({"error": str(exc)}),
                result_summary_json=dumps_json({"error": str(exc)}),
            ) or created
        log_event(
            logger,
            logging.ERROR,
            "background_job.spawn_failed",
            job_id=created["job_id"],
            job_type=normalized_type,
            error=str(exc),
        )
        raise BackgroundJobLaunchError(f"Failed to start background job {created['job_id']}: {exc}") from exc

    with session_scope() as session:
        repo = BackgroundJobRepository(session)
        created = repo.mark_job_running(created["job_id"], pid=pid) or created

    log_event(
        logger,
        logging.INFO,
        "background_job.submitted",
        job_id=created["job_id"],
        job_type=normalized_type,
        pid=pid,
        requested_by=requested_by,
    )
    created["accepted"] = True
    created["deduplicated"] = False
    created["log_path"] = str(_job_log_path(created["job_id"]))
    created["poll_url"] = f"/api/jobs/{created['job_id']}"
    return created


def get_background_job(job_id: str) -> dict | None:
    with session_scope() as session:
        repo = BackgroundJobRepository(session)
        _reconcile_active_jobs(repo)
        payload = repo.get_job(job_id)
    if payload is None:
        return None
    payload["log_path"] = str(_job_log_path(job_id))
    return payload


def list_background_jobs(limit: int = 20, job_type: str | None = None, status: str | None = None) -> dict:
    with session_scope() as session:
        repo = BackgroundJobRepository(session)
        _reconcile_active_jobs(repo)
        items = repo.list_jobs(limit=limit, job_type=job_type, status=status)
    for item in items:
        item["log_path"] = str(_job_log_path(item["job_id"]))
    return {"items": items, "count": len(items)}


def reconcile_stale_jobs() -> int:
    """Open a session and reconcile any crashed or timed-out background jobs.

    Intended to be called by the scheduler on a fixed interval so that stale
    jobs are cleaned up even when no client polls status endpoints.
    Returns the number of jobs that were transitioned to *failed*.
    """
    with session_scope() as session:
        repo = BackgroundJobRepository(session)
        return _reconcile_active_jobs(repo)


def update_background_job_progress(job_id: str, progress: int, *, status: str | None = None) -> dict | None:
    with session_scope() as session:
        repo = BackgroundJobRepository(session)
        payload = repo.update_job_progress(job_id, progress=progress, status=status)
    return payload


def run_background_job(job_id: str) -> int:
    payload = get_background_job(job_id)
    if payload is None:
        log_event(logger, logging.ERROR, "background_job.missing", job_id=job_id)
        return 1

    if payload.get("status") == "completed":
        log_event(logger, logging.INFO, "background_job.already_completed", job_id=job_id)
        return 0
    if payload.get("status") == "failed":
        log_event(logger, logging.INFO, "background_job.already_failed", job_id=job_id)
        return 1

    job_type = _normalize_job_type(payload.get("type"))
    executor = JOB_EXECUTORS[job_type]
    update_background_job_progress(job_id, 10, status="running")
    try:
        result = executor(dict(payload.get("payload") or {}))
        update_background_job_progress(job_id, 90, status="running")
        summary = _summarize_result(job_type, result)
        with session_scope() as session:
            repo = BackgroundJobRepository(session)
            repo.mark_job_completed(
                job_id,
                result_json=dumps_json(result),
                result_summary_json=dumps_json(summary),
            )
        log_event(logger, logging.INFO, "background_job.completed", job_id=job_id, job_type=job_type)
        return 0
    except Exception as exc:
        error_payload = {"error": str(exc)}
        with session_scope() as session:
            repo = BackgroundJobRepository(session)
            repo.mark_job_failed(
                job_id,
                error_message=str(exc),
                result_json=dumps_json(error_payload),
                result_summary_json=dumps_json({"error": str(exc)}),
            )
        log_event(logger, logging.ERROR, "background_job.failed", job_id=job_id, job_type=job_type, error=str(exc))
        return 1
