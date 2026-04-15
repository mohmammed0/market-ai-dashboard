"""Remote GPU worker endpoints.

Protocol:
  1. Worker polls POST /training/worker/next-job with its worker_id → claims
     the oldest queued job atomically (FOR UPDATE SKIP LOCKED) and receives
     the payload needed to start training.
  2. While training, worker sends POST /training/worker/jobs/{id}/heartbeat
     every 30s. If heartbeat lapses > MARKET_AI_REMOTE_WORKER_STALE_SECONDS
     the server reconciler marks the job failed.
  3. On success, worker uploads multipart
     POST /training/worker/jobs/{id}/complete with the model artifact file,
     result_json, and metrics. Server persists the artifact + ModelRun row.
  4. On failure, worker calls POST /training/worker/jobs/{id}/fail.

Auth: Authorization: Bearer <MARKET_AI_WORKER_TOKEN>. The token is a shared
secret set in the backend env (.env). Workers keep the same token in their
config. If the env var is empty, the endpoints are disabled for safety.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.app.config import ROOT_DIR
from backend.app.models import ModelRun
from backend.app.repositories.model_lifecycle import ModelLifecycleRepository
from backend.app.services.storage import dumps_json, session_scope


router = APIRouter(prefix="/training/worker", tags=["training-worker"])


# ── Auth helper ────────────────────────────────────────────────────────────

def _require_worker_token(authorization: str | None = Header(default=None)) -> str:
    expected = os.environ.get("MARKET_AI_WORKER_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Remote worker protocol disabled (MARKET_AI_WORKER_TOKEN not set).")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing worker bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid worker token.")
    return token


# ── Schemas ────────────────────────────────────────────────────────────────

class ClaimJobRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=120)
    worker_hostname: str | None = Field(default=None, max_length=255)
    model_type: str | None = Field(default=None, description="Filter: 'ml' or 'dl'. None = any.")


class HeartbeatRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=120)


class FailJobRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=120)
    error_message: str = Field(..., max_length=4000)


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/next-job")
def claim_next_job(req: ClaimJobRequest, _: str = Depends(_require_worker_token)):
    """Atomically claim the oldest queued job. Returns 204 if queue is empty."""
    model_type = None
    if req.model_type:
        mt = req.model_type.strip().lower()
        if mt not in {"ml", "dl"}:
            raise HTTPException(status_code=400, detail=f"Unsupported model_type: {req.model_type}")
        model_type = mt

    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        claimed = repo.claim_next_queued_job(
            worker_id=req.worker_id,
            worker_hostname=req.worker_hostname,
            model_type=model_type,
        )
    if claimed is None:
        return {"claimed": False, "job": None}
    return {"claimed": True, "job": claimed.model_dump()}


@router.post("/jobs/{job_id}/heartbeat")
def heartbeat(job_id: str, req: HeartbeatRequest, _: str = Depends(_require_worker_token)):
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        updated = repo.heartbeat_training_job(job_id, worker_id=req.worker_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found or claimed by a different worker.")
    return {"ok": True, "heartbeat_at": updated.heartbeat_at}


@router.post("/jobs/{job_id}/fail")
def fail_job(job_id: str, req: FailJobRequest, _: str = Depends(_require_worker_token)):
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        row = repo.get_training_job_row(job_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
        if row.worker_id and row.worker_id != req.worker_id:
            raise HTTPException(status_code=403, detail="Job is claimed by a different worker.")
        updated = repo.mark_training_job_failed(
            job_id,
            error_message=req.error_message,
            result_json=dumps_json({"error": req.error_message, "worker_id": req.worker_id}),
        )
    return {"ok": True, "job": None if updated is None else updated.model_dump()}


@router.post("/jobs/{job_id}/complete")
def complete_job(
    job_id: str,
    worker_id: str = Form(...),
    run_id: str = Form(...),
    model_name: str = Form(...),
    metrics_json: str = Form(...),
    rows_json: str = Form(default="{}"),
    config_json: str = Form(default="{}"),
    set_active: bool = Form(default=True),
    artifact_file: UploadFile = File(...),
    _: str = Depends(_require_worker_token),
):
    """Worker uploads the trained artifact + metrics.

    Server writes the artifact to model_artifacts/<model_type>_runs/<run_id>/
    and creates the ModelRun row, then marks the TrainingJob completed.
    """
    # Validate inputs + claim integrity
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        row = repo.get_training_job_row(job_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
        if row.worker_id and row.worker_id != worker_id:
            raise HTTPException(status_code=403, detail="Job is claimed by a different worker.")
        model_type = str(row.model_type or "").strip().lower()
        if model_type not in {"ml", "dl"}:
            raise HTTPException(status_code=400, detail=f"Unknown model_type on job: {row.model_type}")

    try:
        metrics = json.loads(metrics_json) if metrics_json else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"metrics_json invalid: {exc}") from exc
    try:
        rows_meta = json.loads(rows_json) if rows_json else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"rows_json invalid: {exc}") from exc
    try:
        config_meta = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"config_json invalid: {exc}") from exc

    # Save uploaded artifact
    artifact_root = ROOT_DIR / "model_artifacts" / f"{model_type}_runs" / run_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    orig_name = Path(artifact_file.filename or "").name or (
        "best_model.pt" if model_type == "dl" else "model.joblib"
    )
    artifact_path = artifact_root / orig_name
    try:
        content = artifact_file.file.read()
        with artifact_path.open("wb") as out:
            out.write(content)
    finally:
        try:
            artifact_file.file.close()
        except Exception:
            pass

    now = datetime.utcnow()
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        if set_active:
            session.query(ModelRun).filter(ModelRun.model_type == model_type).update({"is_active": False})
        session.add(ModelRun(
            run_id=run_id,
            model_type=model_type,
            model_name=model_name,
            status="completed",
            started_at=now,
            completed_at=now,
            artifact_path=str(artifact_path),
            metrics_json=dumps_json(metrics),
            config_json=dumps_json(config_meta),
            notes=f"Trained by remote worker {worker_id}.",
            is_active=bool(set_active),
        ))
        result = {
            "run_id": run_id,
            "model_type": model_type,
            "model_name": model_name,
            "artifact_path": str(artifact_path),
            "metrics": metrics,
            "rows": rows_meta,
            "status": "completed",
            "worker_id": worker_id,
        }
        repo.mark_training_job_completed(job_id, result_json=dumps_json(result))

    return {"ok": True, "run_id": run_id, "artifact_path": str(artifact_path)}


# ──────────────────────────────────────────────────────────────────────────
# Alias router: /api/training/jobs/... endpoints (matches user spec)
# ──────────────────────────────────────────────────────────────────────────
#
# These reuse the same auth + repository code as the /training/worker router
# above; they are provided to match the public contract expected by the
# lightweight `trainer_daemon.py` (laptop GPU worker) protocol:
#
#   GET  /api/training/jobs/next-queued          → peek next queued job
#   POST /api/training/jobs/{id}/claim           → claim a specific job atomically
#   POST /api/training/jobs/{id}/artifact        → upload trained artifact (alias of /complete)
#
# IMPORTANT: This alias router must be registered BEFORE the main training
# router in main.py so that `/training/jobs/next-queued` is matched here
# instead of being captured by `/training/jobs/{job_id}` on the training
# router. See main.py for the include order.

jobs_router = APIRouter(prefix="/training/jobs", tags=["training-worker"])
# Alias so main.py can import this without clobbering the unrelated
# `jobs_router` from routes/jobs.py.
training_jobs_worker_router = jobs_router


@jobs_router.get("/next-queued")
def peek_next_queued_job(
    model_type: str | None = None,
    _: str = Depends(_require_worker_token),
):
    """Return the oldest queued training job summary WITHOUT claiming it.

    Remote workers poll this cheaply (every 5s by default) and, when a job is
    present, issue POST /{id}/claim to take ownership. Returns ``{"job": null}``
    when the queue is empty so callers never have to branch on status codes.
    """
    if model_type:
        mt = model_type.strip().lower()
        if mt not in {"ml", "dl"}:
            raise HTTPException(status_code=400, detail=f"Unsupported model_type: {model_type}")
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        summary = repo.peek_next_queued_job(model_type=model_type)
    return {"job": None if summary is None else summary.model_dump()}


@jobs_router.post("/{job_id}/claim")
def claim_job_by_id(
    job_id: str,
    req: ClaimJobRequest,
    _: str = Depends(_require_worker_token),
):
    """Atomically claim a specific queued job by its job_id.

    Response codes:
      * 200 — claimed successfully; payload includes job summary.
      * 404 — job does not exist.
      * 409 — job exists but is not in 'queued' state (already claimed or finished).
    """
    with session_scope() as session:
        repo = ModelLifecycleRepository(session)
        summary, reason = repo.claim_queued_job_by_id(
            job_id,
            worker_id=req.worker_id,
            worker_hostname=req.worker_hostname,
        )
    if reason == "not_found":
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    if reason == "not_queued":
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is not claimable (status={summary.status if summary else 'unknown'}).",
        )
    if reason == "race":
        raise HTTPException(status_code=409, detail=f"Job {job_id} is being claimed by another worker.")
    return {"claimed": True, "job": None if summary is None else summary.model_dump()}


@jobs_router.post("/{job_id}/artifact")
def upload_job_artifact(
    job_id: str,
    worker_id: str = Form(...),
    run_id: str = Form(...),
    model_name: str = Form(...),
    metrics_json: str = Form(...),
    rows_json: str = Form(default="{}"),
    config_json: str = Form(default="{}"),
    set_active: bool = Form(default=True),
    artifact_file: UploadFile = File(...),
    _: str = Depends(_require_worker_token),
):
    """Alias for /training/worker/jobs/{id}/complete using the /jobs/{id}/artifact path.

    Delegates to the exact same body as ``complete_job`` so there is one place
    that writes the artifact file and creates the ModelRun row.
    """
    return complete_job(
        job_id=job_id,
        worker_id=worker_id,
        run_id=run_id,
        model_name=model_name,
        metrics_json=metrics_json,
        rows_json=rows_json,
        config_json=config_json,
        set_active=set_active,
        artifact_file=artifact_file,
        _="",  # auth already validated by the Depends on this endpoint
    )
