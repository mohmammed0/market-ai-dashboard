from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ModelRunSummary(BaseModel):
    run_id: str
    model_type: str
    model_name: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    artifact_path: str | None = None
    is_active: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)


class PromotionReview(BaseModel):
    run_id: str
    model_type: str | None = None
    approved: bool = False
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class TrainingJobSummary(BaseModel):
    job_id: str
    model_type: str
    status: str
    requested_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    requested_by: str | None = None
    pid: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    artifact_path: str | None = None
    error_message: str | None = None
    worker_id: str | None = None
    worker_hostname: str | None = None
    heartbeat_at: str | None = None
