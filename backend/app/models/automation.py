from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class SchedulerRun(Base):
    __tablename__ = "scheduler_runs"
    __table_args__ = (
        Index("ix_scheduler_runs_job_name_ran_at", "job_name", "ran_at"),
        Index("ix_scheduler_runs_status_ran_at", "status", "ran_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, default="idle")
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    detail: Mapped[str | None] = mapped_column(Text)


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (
        Index("ix_automation_runs_job_name_started_at", "job_name", "started_at"),
        Index("ix_automation_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    job_name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    detail: Mapped[str | None] = mapped_column(Text)
    artifacts_count: Mapped[int] = mapped_column(Integer, default=0)


class AutomationArtifact(Base):
    __tablename__ = "automation_artifacts"
    __table_args__ = (
        Index("ix_automation_artifacts_run_id_created_at", "run_id", "created_at"),
        Index("ix_automation_artifacts_job_name_created_at", "job_name", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    job_name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    artifact_key: Mapped[str | None] = mapped_column(String(120), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
