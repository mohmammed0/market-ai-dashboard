from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class OrderIntent(Base):
    __tablename__ = "order_intents"
    __table_args__ = (
        Index("ix_order_intents_symbol_status_created_at", "symbol", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_intent_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    signal_id: Mapped[str | None] = mapped_column(String(80), index=True)
    broker: Mapped[str] = mapped_column(String(40), default="simulated", index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    qty: Mapped[float] = mapped_column(Float, default=0.0)
    order_type: Mapped[str] = mapped_column(String(20), default="market", index=True)
    time_in_force: Mapped[str] = mapped_column(String(20), default="day")
    client_order_id: Mapped[str | None] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RiskDecision(Base):
    __tablename__ = "risk_decisions"
    __table_args__ = (
        Index("ix_risk_decisions_symbol_created_at", "symbol", "created_at"),
        Index("ix_risk_decisions_decision_created_at", "decision", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    signal_id: Mapped[str | None] = mapped_column(String(80), index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    intent: Mapped[str] = mapped_column(String(40), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    approved_qty: Mapped[float | None] = mapped_column(Float)
    reason_codes_json: Mapped[str | None] = mapped_column(Text)
    risk_snapshot_json: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (
        Index("ix_order_events_event_type_created_at", "event_type", "created_at"),
        Index("ix_order_events_client_order_id_created_at", "client_order_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    order_intent_id: Mapped[str | None] = mapped_column(String(80), index=True)
    client_order_id: Mapped[str | None] = mapped_column(String(80), index=True)
    symbol: Mapped[str | None] = mapped_column(String(20), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    event_version: Mapped[str] = mapped_column(String(10), default="1")
    producer: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PortfolioSnapshotRecord(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = (
        Index("ix_portfolio_snapshots_snapshot_type_created_at", "snapshot_type", "created_at"),
        Index("ix_portfolio_snapshots_active_source_created_at", "active_source", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(40), default="canonical", index=True)
    active_source: Mapped[str | None] = mapped_column(String(40), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    summary_json: Mapped[str | None] = mapped_column(Text)
    positions_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_workflow_name_started_at", "workflow_name", "started_at"),
        Index("ix_workflow_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workflow_name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="started")
    correlation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ProviderHealth(Base):
    __tablename__ = "provider_health"
    __table_args__ = (
        Index("ix_provider_health_provider_checked_at", "provider_name", "checked_at"),
        Index("ix_provider_health_provider_type_checked_at", "provider_type", "checked_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    provider_name: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    healthy: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    detail: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SchedulerLease(Base):
    __tablename__ = "scheduler_leases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lease_name: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    holder_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class EventReplayJob(Base):
    __tablename__ = "event_replay_jobs"
    __table_args__ = (
        Index("ix_event_replay_jobs_status_created_at", "status", "created_at"),
        Index("ix_event_replay_jobs_event_type_created_at", "event_type_filter", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, default="queued")
    event_type_filter: Mapped[str | None] = mapped_column(String(80), index=True)
    replay_since: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    result_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class DeadLetterEvent(Base):
    __tablename__ = "dead_letter_events"
    __table_args__ = (
        Index("ix_dead_letter_events_event_type_created_at", "event_type", "created_at"),
        Index("ix_dead_letter_events_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    producer: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
