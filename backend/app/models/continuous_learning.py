from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ContinuousLearningState(Base):
    __tablename__ = "continuous_learning_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    engine_key: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    desired_state: Mapped[str] = mapped_column(String(20), index=True, default="running")
    runtime_status: Mapped[str] = mapped_column(String(20), index=True, default="idle")
    active_stage: Mapped[str | None] = mapped_column(String(60), index=True)
    worker_id: Mapped[str | None] = mapped_column(String(120), index=True)
    active_pid: Mapped[int | None] = mapped_column(Integer, index=True)
    current_run_id: Mapped[str | None] = mapped_column(String(80), index=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_cycle_started_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_cycle_completed_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    next_cycle_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    current_model_version: Mapped[str | None] = mapped_column(String(160))
    best_strategy_name: Mapped[str | None] = mapped_column(String(160))
    best_strategy_run_id: Mapped[str | None] = mapped_column(String(80), index=True)
    latest_metrics_json: Mapped[str | None] = mapped_column(Text)
    latest_artifact_path: Mapped[str | None] = mapped_column(Text)
    last_failure_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class ContinuousLearningRun(Base):
    __tablename__ = "continuous_learning_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, default="running")
    stage: Mapped[str | None] = mapped_column(String(60), index=True)
    cycle_type: Mapped[str] = mapped_column(String(30), index=True, default="full")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    summary_json: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)


class ContinuousLearningArtifact(Base):
    __tablename__ = "continuous_learning_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    artifact_key: Mapped[str | None] = mapped_column(String(120), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
