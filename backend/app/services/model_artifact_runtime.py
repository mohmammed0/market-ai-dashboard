from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import desc

from backend.app.config import ROOT_DIR
from backend.app.models import ModelRun
from backend.app.services.storage import loads_json, session_scope


ARTIFACT_ROOT = ROOT_DIR / "model_artifacts"
RUN_ARTIFACT_DIRS = {
    "ml": ARTIFACT_ROOT / "ml_runs",
    "dl": ARTIFACT_ROOT / "dl_runs",
}
RUN_ARTIFACT_FILES = {
    "ml": "model.joblib",
    "dl": "best_model.pt",
}
VALID_RUN_STATUSES = {"completed", "running"}
CONTINUOUS_LEARNING_ARTIFACT_ROOT = ARTIFACT_ROOT / "continuous_learning"


def _normalize_artifact_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(value)
    return path if path.is_absolute() else (ROOT_DIR / path).resolve()


def _canonical_artifact_path(model_type: str, run_id: str) -> Path | None:
    run_root = RUN_ARTIFACT_DIRS.get(model_type)
    file_name = RUN_ARTIFACT_FILES.get(model_type)
    if run_root is None or not file_name or not run_id:
        return None
    return run_root / run_id / file_name


def _candidate_artifact_paths(row: ModelRun) -> list[Path]:
    candidates = [
        _normalize_artifact_path(row.artifact_path),
        _canonical_artifact_path(row.model_type, row.run_id),
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _resolve_existing_artifact(row: ModelRun) -> Path | None:
    for candidate in _candidate_artifact_paths(row):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _serialize_resolution(row: ModelRun, artifact_path: Path, resolution: str) -> dict:
    return {
        "run_id": row.run_id,
        "model_type": row.model_type,
        "model_name": row.model_name,
        "status": row.status,
        "is_active": bool(row.is_active),
        "artifact_path": str(artifact_path),
        "metrics": loads_json(row.metrics_json, default={}),
        "config": loads_json(row.config_json, default={}),
        "resolution": resolution,
    }


def _serialize_inferred_resolution(
    *,
    run_id: str,
    model_type: str,
    artifact_path: Path,
    resolution: str,
    model_name: str | None = None,
    status: str = "completed",
    is_active: bool = False,
    metrics: dict | None = None,
    config: dict | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "model_type": model_type,
        "model_name": model_name or f"{model_type}_inferred",
        "status": status,
        "is_active": bool(is_active),
        "artifact_path": str(artifact_path),
        "metrics": metrics or {},
        "config": config or {},
        "resolution": resolution,
    }


def _load_json_file(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _resolve_from_continuous_learning_artifacts() -> dict | None:
    if not CONTINUOUS_LEARNING_ARTIFACT_ROOT.exists():
        return None

    directories = sorted(
        [item for item in CONTINUOUS_LEARNING_ARTIFACT_ROOT.iterdir() if item.is_dir()],
        key=lambda item: item.name,
        reverse=True,
    )
    for directory in directories:
        promotion_payload = _load_json_file(directory / "promotion_dl.json")
        training_payload = _load_json_file(directory / "training_dl.json")

        promoted_run_id = str(promotion_payload.get("promoted_run_id") or "").strip()
        review_payload = promotion_payload.get("review") if isinstance(promotion_payload.get("review"), dict) else {}
        review_metrics = review_payload.get("metrics") if isinstance(review_payload.get("metrics"), dict) else {}
        training_run_id = str(training_payload.get("run_id") or "").strip()
        training_metrics = training_payload.get("metrics") if isinstance(training_payload.get("metrics"), dict) else {}

        candidates = []
        if promoted_run_id:
            promoted_artifact = _normalize_artifact_path(review_metrics.get("best_checkpoint_path")) or _canonical_artifact_path("dl", promoted_run_id)
            candidates.append({
                "run_id": promoted_run_id,
                "artifact_path": promoted_artifact,
                "resolution": "promoted_artifact",
                "metrics": review_metrics,
                "status": "completed",
                "is_active": True,
            })

        if training_run_id:
            training_artifact = _normalize_artifact_path(training_payload.get("artifact_path")) or _normalize_artifact_path(training_metrics.get("best_checkpoint_path")) or _canonical_artifact_path("dl", training_run_id)
            candidates.append({
                "run_id": training_run_id,
                "artifact_path": training_artifact,
                "resolution": "training_artifact",
                "metrics": training_metrics,
                "status": str(training_payload.get("status") or "completed"),
                "is_active": False,
            })

        for candidate in candidates:
            artifact_path = candidate.get("artifact_path")
            if artifact_path is None or not artifact_path.exists() or not artifact_path.is_file():
                continue
            return _serialize_inferred_resolution(
                run_id=candidate["run_id"],
                model_type="dl",
                model_name="gru_sequence",
                artifact_path=artifact_path,
                resolution=candidate["resolution"],
                status=candidate["status"],
                is_active=candidate["is_active"],
                metrics=candidate["metrics"],
            )
    return None


def _resolve_from_latest_run_directory(model_type: str) -> dict | None:
    run_root = RUN_ARTIFACT_DIRS.get(model_type)
    file_name = RUN_ARTIFACT_FILES.get(model_type)
    if run_root is None or not run_root.exists() or not file_name:
        return None

    artifacts = sorted(
        [item for item in run_root.glob(f"*/{file_name}") if item.is_file()],
        key=lambda item: item.parent.name,
        reverse=True,
    )
    if not artifacts:
        return None

    artifact_path = artifacts[0]
    return _serialize_inferred_resolution(
        run_id=artifact_path.parent.name,
        model_type=model_type,
        artifact_path=artifact_path,
        resolution="filesystem_latest",
    )


def resolve_model_artifact(model_type: str, run_id: str | None = None) -> dict:
    normalized_type = str(model_type or "").strip().lower()
    if normalized_type not in RUN_ARTIFACT_FILES:
        return {"error": f"Unsupported model type: {model_type}"}

    with session_scope() as session:
        query = session.query(ModelRun).filter(ModelRun.model_type == normalized_type)

        if run_id:
            row = query.filter(ModelRun.run_id == run_id).first()
            if row is None:
                return {"error": f"Model run not found: {run_id}"}
            artifact_path = _resolve_existing_artifact(row)
            if artifact_path is None:
                return {"error": f"Model artifact is missing for run: {run_id}"}
            return _serialize_resolution(row, artifact_path, "explicit")

        candidates = query.order_by(
            desc(ModelRun.is_active),
            desc(ModelRun.completed_at),
            desc(ModelRun.started_at),
        ).limit(100).all()

    latest_valid: dict | None = None
    for row in candidates:
        if str(row.status or "").strip().lower() not in VALID_RUN_STATUSES:
            continue
        artifact_path = _resolve_existing_artifact(row)
        if artifact_path is None:
            continue
        resolution = "active" if row.is_active else "latest_valid"
        resolved = _serialize_resolution(row, artifact_path, resolution)
        if row.is_active:
            return resolved
        if latest_valid is None:
            latest_valid = resolved

    if latest_valid is not None:
        return latest_valid

    if normalized_type == "dl":
        inferred = _resolve_from_continuous_learning_artifacts()
        if inferred is not None:
            return inferred

    inferred = _resolve_from_latest_run_directory(normalized_type)
    if inferred is not None:
        return inferred

    return {"error": f"No valid {normalized_type.upper()} model artifact run is available."}
