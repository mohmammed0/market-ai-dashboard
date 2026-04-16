from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        Index("ix_background_jobs_status_created_at", "status", "created_at"),
        Index("ix_background_jobs_job_type_status_created_at", "job_type", "status", "created_at"),
        Index("ix_background_jobs_job_type_payload_hash_status", "job_type", "payload_hash", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    job_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(80))
    payload_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    result_summary_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    pid: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
