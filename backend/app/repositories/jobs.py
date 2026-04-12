from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models.jobs import BackgroundJob
from backend.app.services.storage import loads_json


def _job_duration_seconds(row: BackgroundJob) -> float | None:
    if row.started_at and row.completed_at:
        return round((row.completed_at - row.started_at).total_seconds(), 4)
    return None


def _serialize_job_summary(row: BackgroundJob) -> dict:
    result_summary = loads_json(row.result_summary_json)
    return {
        "job_id": row.job_id,
        "type": row.job_type,
        "status": row.status,
        "progress": int(row.progress or 0),
        "requested_by": row.requested_by,
        "result_summary": result_summary,
        "error_message": row.error_message,
        "pid": row.pid,
        "created_at": None if row.created_at is None else row.created_at.isoformat(),
        "started_at": None if row.started_at is None else row.started_at.isoformat(),
        "completed_at": None if row.completed_at is None else row.completed_at.isoformat(),
        "updated_at": None if row.updated_at is None else row.updated_at.isoformat(),
        "duration_seconds": _job_duration_seconds(row),
        "has_payload": bool(row.payload_json),
        "has_result": bool(row.result_json),
    }


def _serialize_job_detail(row: BackgroundJob) -> dict:
    payload = _serialize_job_summary(row)
    payload["payload"] = loads_json(row.payload_json)
    payload["result"] = loads_json(row.result_json)
    return payload


class BackgroundJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_job(
        self,
        *,
        job_id: str,
        job_type: str,
        payload_json: str,
        payload_hash: str,
        requested_by: str | None = None,
    ) -> dict:
        row = BackgroundJob(
            job_id=job_id,
            job_type=job_type,
            status="pending",
            progress=0,
            requested_by=requested_by,
            payload_hash=payload_hash,
            payload_json=payload_json,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.flush()
        return _serialize_job_detail(row)

    def get_job_row(self, job_id: str) -> BackgroundJob | None:
        return self.session.query(BackgroundJob).filter(BackgroundJob.job_id == job_id).first()

    def get_job(self, job_id: str) -> dict | None:
        row = self.get_job_row(job_id)
        return None if row is None else _serialize_job_detail(row)

    def list_jobs(self, *, limit: int = 20, job_type: str | None = None, status: str | None = None) -> list[dict]:
        query = self.session.query(BackgroundJob)
        if job_type:
            query = query.filter(BackgroundJob.job_type == str(job_type).strip().lower())
        if status:
            query = query.filter(BackgroundJob.status == str(status).strip().lower())
        rows = query.order_by(BackgroundJob.created_at.desc(), BackgroundJob.id.desc()).limit(limit).all()
        return [_serialize_job_summary(row) for row in rows]

    def list_active_job_rows(
        self,
        *,
        job_type: str | None = None,
        statuses: tuple[str, ...] = ("pending", "running"),
    ) -> list[BackgroundJob]:
        query = self.session.query(BackgroundJob).filter(BackgroundJob.status.in_(statuses))
        if job_type:
            query = query.filter(BackgroundJob.job_type == str(job_type).strip().lower())
        return query.order_by(BackgroundJob.created_at.asc(), BackgroundJob.id.asc()).all()

    def count_active_jobs(
        self,
        *,
        job_type: str | None = None,
        statuses: tuple[str, ...] = ("pending", "running"),
    ) -> int:
        query = self.session.query(BackgroundJob).filter(BackgroundJob.status.in_(statuses))
        if job_type:
            query = query.filter(BackgroundJob.job_type == str(job_type).strip().lower())
        return int(query.count())

    def find_active_duplicate(
        self,
        *,
        job_type: str,
        payload_hash: str,
        statuses: tuple[str, ...] = ("pending", "running"),
    ) -> dict | None:
        row = (
            self.session.query(BackgroundJob)
            .filter(BackgroundJob.job_type == job_type)
            .filter(BackgroundJob.payload_hash == payload_hash)
            .filter(BackgroundJob.status.in_(statuses))
            .order_by(BackgroundJob.created_at.desc(), BackgroundJob.id.desc())
            .first()
        )
        return None if row is None else _serialize_job_detail(row)

    def find_recent_duplicate(
        self,
        *,
        job_type: str,
        payload_hash: str,
        dedupe_seconds: int,
        statuses: tuple[str, ...] = ("pending", "running"),
    ) -> dict | None:
        window_start = datetime.utcnow() - timedelta(seconds=max(int(dedupe_seconds), 1))
        row = (
            self.session.query(BackgroundJob)
            .filter(BackgroundJob.job_type == job_type)
            .filter(BackgroundJob.payload_hash == payload_hash)
            .filter(BackgroundJob.status.in_(statuses))
            .filter(BackgroundJob.created_at >= window_start)
            .order_by(BackgroundJob.created_at.desc(), BackgroundJob.id.desc())
            .first()
        )
        return None if row is None else _serialize_job_detail(row)

    def mark_job_running(self, job_id: str, *, pid: int | None = None) -> dict | None:
        row = self.get_job_row(job_id)
        if row is None:
            return None
        now = datetime.utcnow()
        row.status = "running"
        row.progress = max(int(row.progress or 0), 5)
        row.started_at = row.started_at or now
        row.updated_at = now
        if pid is not None:
            row.pid = int(pid)
        self.session.flush()
        return _serialize_job_detail(row)

    def update_job_progress(self, job_id: str, *, progress: int, status: str | None = None) -> dict | None:
        row = self.get_job_row(job_id)
        if row is None:
            return None
        row.progress = max(0, min(int(progress), 100))
        if status:
            row.status = str(status).strip().lower()
        row.updated_at = datetime.utcnow()
        self.session.flush()
        return _serialize_job_detail(row)

    def mark_job_completed(self, job_id: str, *, result_json: str, result_summary_json: str) -> dict | None:
        row = self.get_job_row(job_id)
        if row is None:
            return None
        now = datetime.utcnow()
        row.status = "completed"
        row.progress = 100
        row.completed_at = now
        row.updated_at = now
        row.result_json = result_json
        row.result_summary_json = result_summary_json
        row.error_message = None
        self.session.flush()
        return _serialize_job_detail(row)

    def mark_job_failed(
        self,
        job_id: str,
        *,
        error_message: str,
        result_json: str | None = None,
        result_summary_json: str | None = None,
    ) -> dict | None:
        row = self.get_job_row(job_id)
        if row is None:
            return None
        now = datetime.utcnow()
        row.status = "failed"
        row.completed_at = now
        row.updated_at = now
        row.error_message = error_message
        if result_json is not None:
            row.result_json = result_json
        if result_summary_json is not None:
            row.result_summary_json = result_summary_json
        self.session.flush()
        return _serialize_job_detail(row)
