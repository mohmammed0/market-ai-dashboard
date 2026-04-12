from __future__ import annotations

import json
from sqlalchemy.orm import Session

from datetime import datetime

from backend.app.domain.model_lifecycle.contracts import ModelRunSummary, TrainingJobSummary
from backend.app.models.model_lifecycle import ModelRun, TrainingJob
from backend.app.services.storage import loads_json


def _serialize_run(row: ModelRun) -> ModelRunSummary:
    duration_seconds = None
    if row.started_at and row.completed_at:
        duration_seconds = round((row.completed_at - row.started_at).total_seconds(), 4)
    return ModelRunSummary(
        run_id=row.run_id,
        model_type=row.model_type,
        model_name=row.model_name,
        status=row.status,
        started_at=row.started_at.isoformat() if row.started_at else None,
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        duration_seconds=duration_seconds,
        artifact_path=row.artifact_path,
        is_active=bool(row.is_active),
        metrics=loads_json(row.metrics_json),
    )


def _serialize_training_job(row: TrainingJob) -> TrainingJobSummary:
    result = loads_json(row.result_json)
    run_id = None
    artifact_path = None
    result_summary = {}
    if isinstance(result, dict):
        run_id = result.get("run_id")
        artifact_path = result.get("artifact_path")
        metrics = result.get("metrics") or {}
        rows = result.get("rows") or {}
        result_summary = {
            "status": result.get("status"),
            "validation_macro_f1": metrics.get("validation_macro_f1"),
            "test_accuracy": metrics.get("test_accuracy"),
            "best_model_name": metrics.get("best_model_name"),
            "train_rows": rows.get("train"),
            "validation_rows": rows.get("validation"),
            "test_rows": rows.get("test"),
        }
    duration_seconds = None
    if row.started_at and row.completed_at:
        duration_seconds = round((row.completed_at - row.started_at).total_seconds(), 4)
    return TrainingJobSummary(
        job_id=row.job_id,
        model_type=row.model_type,
        status=row.status,
        requested_at=row.requested_at.isoformat() if row.requested_at else None,
        started_at=row.started_at.isoformat() if row.started_at else None,
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        duration_seconds=duration_seconds,
        requested_by=row.requested_by,
        pid=row.pid,
        payload=loads_json(row.payload_json),
        result=result,
        result_summary=result_summary,
        run_id=run_id,
        artifact_path=artifact_path,
        error_message=row.error_message,
    )


class ModelLifecycleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_runs(self, model_type: str | None = None, limit: int = 50) -> list[ModelRunSummary]:
        query = self.session.query(ModelRun)
        if model_type:
            query = query.filter(ModelRun.model_type == model_type)
        rows = query.order_by(ModelRun.started_at.desc()).limit(limit).all()
        return [_serialize_run(row) for row in rows]

    def get_run_row(self, run_id: str) -> ModelRun | None:
        return self.session.query(ModelRun).filter(ModelRun.run_id == run_id).first()

    def get_run(self, run_id: str) -> ModelRunSummary | None:
        row = self.get_run_row(run_id)
        return None if row is None else _serialize_run(row)

    def set_active(self, run_id: str, active: bool = True) -> ModelRunSummary | None:
        row = self.get_run_row(run_id)
        if row is None:
            return None
        if active:
            self.session.query(ModelRun).filter(ModelRun.model_type == row.model_type).update({"is_active": False})
        row.is_active = bool(active)
        self.session.flush()
        return _serialize_run(row)

    def create_training_job(self, *, job_id: str, model_type: str, payload_json: str, requested_by: str | None = None) -> TrainingJobSummary:
        row = TrainingJob(
            job_id=job_id,
            model_type=model_type,
            status="queued",
            payload_json=payload_json,
            requested_by=requested_by,
        )
        self.session.add(row)
        self.session.flush()
        return _serialize_training_job(row)

    def get_training_job_row(self, job_id: str) -> TrainingJob | None:
        return self.session.query(TrainingJob).filter(TrainingJob.job_id == job_id).first()

    def get_training_job(self, job_id: str) -> TrainingJobSummary | None:
        row = self.get_training_job_row(job_id)
        return None if row is None else _serialize_training_job(row)

    def list_training_jobs(self, limit: int = 20) -> list[TrainingJobSummary]:
        rows = self.session.query(TrainingJob).order_by(TrainingJob.requested_at.desc()).limit(limit).all()
        return [_serialize_training_job(row) for row in rows]

    def list_active_training_job_rows(
        self,
        *,
        model_type: str | None = None,
        statuses: tuple[str, ...] = ("queued", "running"),
    ) -> list[TrainingJob]:
        query = self.session.query(TrainingJob).filter(TrainingJob.status.in_(statuses))
        if model_type:
            query = query.filter(TrainingJob.model_type == str(model_type).strip().lower())
        return query.order_by(TrainingJob.requested_at.asc(), TrainingJob.id.asc()).all()

    def count_active_training_jobs(
        self,
        *,
        model_type: str | None = None,
        statuses: tuple[str, ...] = ("queued", "running"),
    ) -> int:
        query = self.session.query(TrainingJob).filter(TrainingJob.status.in_(statuses))
        if model_type:
            query = query.filter(TrainingJob.model_type == str(model_type).strip().lower())
        return int(query.count())

    def find_active_training_job(
        self,
        *,
        model_type: str,
        payload_json: str,
        statuses: tuple[str, ...] = ("queued", "running"),
    ) -> TrainingJobSummary | None:
        row = (
            self.session.query(TrainingJob)
            .filter(TrainingJob.model_type == str(model_type).strip().lower())
            .filter(TrainingJob.payload_json == payload_json)
            .filter(TrainingJob.status.in_(statuses))
            .order_by(TrainingJob.requested_at.desc(), TrainingJob.id.desc())
            .first()
        )
        return None if row is None else _serialize_training_job(row)

    def mark_training_job_running(self, job_id: str, pid: int | None = None) -> TrainingJobSummary | None:
        row = self.get_training_job_row(job_id)
        if row is None:
            return None
        row.status = "running"
        row.started_at = datetime.utcnow()
        row.pid = pid
        self.session.flush()
        return _serialize_training_job(row)

    def mark_training_job_completed(self, job_id: str, *, result_json: str) -> TrainingJobSummary | None:
        row = self.get_training_job_row(job_id)
        if row is None:
            return None
        row.status = "completed"
        row.completed_at = datetime.utcnow()
        row.result_json = result_json
        row.error_message = None
        self.session.flush()
        return _serialize_training_job(row)

    def mark_training_job_failed(self, job_id: str, *, error_message: str, result_json: str | None = None) -> TrainingJobSummary | None:
        row = self.get_training_job_row(job_id)
        if row is None:
            return None
        row.status = "failed"
        row.completed_at = datetime.utcnow()
        row.error_message = error_message
        if result_json is not None:
            row.result_json = result_json
        self.session.flush()
        return _serialize_training_job(row)
