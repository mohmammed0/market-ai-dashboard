from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ModelRun(Base):
    __tablename__ = "model_runs"
    __table_args__ = (
        Index("ix_model_runs_model_type_started_at", "model_type", "started_at"),
        Index("ix_model_runs_model_type_is_active", "model_type", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    model_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    artifact_path: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[str | None] = mapped_column(Text)
    config_json: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class ModelPrediction(Base):
    __tablename__ = "model_predictions"
    __table_args__ = (
        Index("ix_model_predictions_symbol_model_type_predicted_at", "symbol", "model_type", "predicted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    predicted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    model_run_id: Mapped[str | None] = mapped_column(String(80), index=True)
    model_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    signal: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    prob_buy: Mapped[float | None] = mapped_column(Float)
    prob_hold: Mapped[float | None] = mapped_column(Float)
    prob_sell: Mapped[float | None] = mapped_column(Float)
    payload_json: Mapped[str | None] = mapped_column(Text)


class StrategyEvaluationRun(Base):
    __tablename__ = "strategy_evaluation_runs"
    __table_args__ = (
        Index("ix_strategy_evaluation_runs_instrument_started_at", "instrument", "started_at"),
        Index("ix_strategy_evaluation_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    instrument: Mapped[str | None] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True, default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    config_json: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[str | None] = mapped_column(Text)
    leaderboard_json: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class TrainingJob(Base):
    __tablename__ = "training_jobs"
    __table_args__ = (
        Index("ix_training_jobs_status_requested_at", "status", "requested_at"),
        Index("ix_training_jobs_model_type_status_requested_at", "model_type", "status", "requested_at"),
        Index("ix_training_jobs_worker_status_heartbeat_at", "worker_id", "status", "heartbeat_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    model_type: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, default="queued")
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    requested_by: Mapped[str | None] = mapped_column(String(80))
    pid: Mapped[int | None] = mapped_column(Integer)
    payload_json: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    # Remote GPU worker fields (nullable => local subprocess leaves them unset)
    worker_id: Mapped[str | None] = mapped_column(String(120), index=True)
    worker_hostname: Mapped[str | None] = mapped_column(String(255))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
