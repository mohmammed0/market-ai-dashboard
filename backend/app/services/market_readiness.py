from __future__ import annotations

from typing import Any

from backend.app.models import AutomationArtifact, AutomationRun
from backend.app.services.storage import loads_json, session_scope

_JOB_NAME = "auto_trading_cycle"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _row_payload(run: AutomationRun, artifact_map: dict[str, dict]) -> dict:
    readiness = artifact_map.get("market_open_readiness") if isinstance(artifact_map.get("market_open_readiness"), dict) else {}
    session = artifact_map.get("market_session_status") if isinstance(artifact_map.get("market_session_status"), dict) else {}
    kronos = artifact_map.get("kronos_intelligence") if isinstance(artifact_map.get("kronos_intelligence"), dict) else {}

    return {
        "cycle_id": run.run_id,
        "status": run.status,
        "cycle_started_at": run.started_at.isoformat() if run.started_at else None,
        "cycle_completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_seconds": run.duration_seconds,
        "market_session": session,
        "market_readiness": readiness,
        "kronos": kronos,
    }


def list_market_readiness_cycles(limit: int = 20) -> dict:
    resolved_limit = max(1, min(_safe_int(limit, 20), 100))

    with session_scope() as session:
        runs = (
            session.query(AutomationRun)
            .filter(AutomationRun.job_name == _JOB_NAME)
            .order_by(AutomationRun.started_at.desc())
            .limit(resolved_limit)
            .all()
        )

        run_ids = [row.run_id for row in runs if row.run_id]
        artifact_map_by_run: dict[str, dict[str, dict]] = {run_id: {} for run_id in run_ids}
        if run_ids:
            artifacts = (
                session.query(AutomationArtifact)
                .filter(
                    AutomationArtifact.job_name == _JOB_NAME,
                    AutomationArtifact.run_id.in_(run_ids),
                    AutomationArtifact.artifact_type.in_([
                        "market_open_readiness",
                        "market_session_status",
                        "kronos_intelligence",
                    ]),
                )
                .order_by(AutomationArtifact.created_at.desc())
                .all()
            )
            for artifact in artifacts:
                bucket = artifact_map_by_run.setdefault(artifact.run_id, {})
                if artifact.artifact_type in bucket:
                    continue
                bucket[artifact.artifact_type] = loads_json(artifact.payload_json)

    items = [_row_payload(run, artifact_map_by_run.get(run.run_id, {})) for run in runs]
    return {
        "count": len(items),
        "limit": resolved_limit,
        "items": items,
    }


def get_latest_market_readiness() -> dict | None:
    payload = list_market_readiness_cycles(limit=10)
    items = payload.get("items") if isinstance(payload, dict) else []
    if not items:
        return None

    for item in items:
        readiness = item.get("market_readiness") if isinstance(item.get("market_readiness"), dict) else {}
        if readiness:
            return item
    return items[0]


def get_market_readiness_cycle(cycle_id: str) -> dict | None:
    normalized = str(cycle_id or "").strip()
    if not normalized:
        return None

    with session_scope() as session:
        run = (
            session.query(AutomationRun)
            .filter(
                AutomationRun.job_name == _JOB_NAME,
                AutomationRun.run_id == normalized,
            )
            .first()
        )
        if run is None:
            return None

        artifacts = (
            session.query(AutomationArtifact)
            .filter(
                AutomationArtifact.job_name == _JOB_NAME,
                AutomationArtifact.run_id == normalized,
                AutomationArtifact.artifact_type.in_([
                    "market_open_readiness",
                    "market_session_status",
                    "kronos_intelligence",
                ]),
            )
            .order_by(AutomationArtifact.created_at.desc())
            .all()
        )

    artifact_map: dict[str, dict] = {}
    for artifact in artifacts:
        if artifact.artifact_type in artifact_map:
            continue
        artifact_map[artifact.artifact_type] = loads_json(artifact.payload_json)
    return _row_payload(run, artifact_map)
