"""Automation diagnostics and status payloads."""

from __future__ import annotations

from backend.app.config import (
    AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT,
    AUTONOMOUS_INCLUDE_DL,
    AUTONOMOUS_TRAIN_SYMBOL_LIMIT,
    ENABLE_AUTO_RETRAIN,
    ENABLE_AUTONOMOUS_CYCLE,
)
from backend.app.models import AutomationArtifact, AutomationRun
from backend.app.services.automation.orchestration import JOB_NAMES
from backend.app.services.storage import loads_json, session_scope


def get_automation_status(limit: int = 20) -> dict:
    limit = max(1, min(int(limit or 20), 100))
    with session_scope() as session:
        rows = (
            session.query(AutomationRun)
            .order_by(AutomationRun.started_at.desc())
            .limit(limit)
            .all()
        )
        items = [
            {
                "run_id": row.run_id,
                "job_name": row.job_name,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "duration_seconds": row.duration_seconds,
                "dry_run": bool(row.dry_run),
                "detail": row.detail,
                "artifacts_count": row.artifacts_count,
            }
            for row in rows
        ]
        artifacts = (
            session.query(AutomationArtifact)
            .order_by(AutomationArtifact.created_at.desc())
            .limit(limit)
            .all()
        )
        latest_artifacts = [
            {
                "run_id": row.run_id,
                "job_name": row.job_name,
                "artifact_type": row.artifact_type,
                "artifact_key": row.artifact_key,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "payload": loads_json(row.payload_json),
            }
            for row in artifacts
        ]

    return {
        "jobs": [{"job_name": key, "label": value} for key, value in JOB_NAMES.items()],
        "recent_runs": items,
        "latest_artifacts": latest_artifacts,
        "auto_retrain_enabled": ENABLE_AUTO_RETRAIN,
        "autonomous_cycle_enabled": ENABLE_AUTONOMOUS_CYCLE,
        "autonomous_analysis_symbol_limit": AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT,
        "autonomous_train_symbol_limit": AUTONOMOUS_TRAIN_SYMBOL_LIMIT,
        "autonomous_include_dl": AUTONOMOUS_INCLUDE_DL,
    }
