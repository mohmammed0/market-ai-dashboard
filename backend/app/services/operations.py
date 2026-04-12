from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.config import (
    FORWARDED_ALLOW_IPS,
    OPS_BACKUPS_DIR,
    OPS_LOGS_DIR,
    PROXY_HEADERS_ENABLED,
    PUBLIC_API_ORIGIN,
    PUBLIC_WEB_ORIGIN,
    SERVER_NAME,
    TRUSTED_HOSTS,
)
from backend.app.core.logging_utils import get_log_paths, read_recent_app_log, read_recent_events
from backend.app.services.runtime_control import get_runtime_control_plane
from core.runtime_paths import (
    CONTINUOUS_LEARNING_LOGS_DIR,
    DATA_DIR,
    LOGS_DIR,
    MODEL_ARTIFACTS_DIR,
    DEFAULT_RUNTIME_CACHE_DIR,
    SETTINGS_KEY_PATH,
    SOURCE_CACHE_DIR,
    TRAINING_LOGS_DIR,
)


def _iso_or_none(value: float | None) -> str | None:
    if value in (None, 0):
        return None
    try:
        return datetime.utcfromtimestamp(float(value)).isoformat()
    except Exception:
        return None


def _file_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "size_bytes": 0,
            "modified_at": None,
        }
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": int(stat.st_size),
        "modified_at": _iso_or_none(stat.st_mtime),
    }


def list_backup_bundles(limit: int = 20) -> list[dict[str, Any]]:
    manifests = sorted(OPS_BACKUPS_DIR.glob("*.manifest.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    items: list[dict[str, Any]] = []
    for manifest_path in manifests[: max(int(limit or 0), 1)]:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        archive_path = OPS_BACKUPS_DIR / str(payload.get("archive_name") or "").strip()
        item = {
            "label": payload.get("backup_id") or manifest_path.stem.removesuffix(".manifest"),
            "created_at": payload.get("created_at") or _file_meta(manifest_path).get("modified_at"),
            "archive": _file_meta(archive_path) if archive_path.name else _file_meta(manifest_path.with_suffix("")),
            "manifest": _file_meta(manifest_path),
            "includes": payload.get("includes", []),
            "notes": payload.get("notes", []),
            "warnings": payload.get("warnings", []),
        }
        items.append(item)

    if items:
        return items

    archives = sorted(OPS_BACKUPS_DIR.glob("*.tar.gz"), key=lambda item: item.stat().st_mtime, reverse=True)
    return [
        {
            "label": archive.name,
            "created_at": _file_meta(archive).get("modified_at"),
            "archive": _file_meta(archive),
            "manifest": None,
            "includes": [],
            "notes": [],
            "warnings": [],
        }
        for archive in archives[: max(int(limit or 0), 1)]
    ]


def get_operations_overview() -> dict[str, Any]:
    log_paths = get_log_paths()
    app_log = Path(log_paths["app_log"])
    events_log = Path(log_paths["events_log"])
    backups = list_backup_bundles(limit=5)
    control_plane = get_runtime_control_plane()
    reverse_proxy_ready = bool(SERVER_NAME or PUBLIC_WEB_ORIGIN or PUBLIC_API_ORIGIN)
    return {
        "deployment": {
            "server_name": SERVER_NAME or None,
            "public_web_origin": PUBLIC_WEB_ORIGIN or None,
            "public_api_origin": PUBLIC_API_ORIGIN or None,
            "proxy_headers_enabled": PROXY_HEADERS_ENABLED,
            "forwarded_allow_ips": FORWARDED_ALLOW_IPS,
            "trusted_hosts": TRUSTED_HOSTS,
            "reverse_proxy_ready": reverse_proxy_ready,
            "reverse_proxy_verification": "not_verified_by_application",
            "https_termination_mode": "external_reverse_proxy",
            "notes": [
                "وجّه الدومين إلى خدمة الويب أو البروكسي العكسي أمامها.",
                "أنهِ SSL/HTTPS عند Nginx أو Caddy أو Traefik الخارجي، ثم مرر / و /api و /health و /ready إلى المنصة.",
                "الواجهة تعمل في الإنتاج بأسلوب same-origin، لذلك لا تعتمد على localhost عند ضبط الدومين.",
            ],
        },
        "paths": {
            "data_dir": str(DATA_DIR),
            "runtime_cache_dir": str(DEFAULT_RUNTIME_CACHE_DIR),
            "source_cache_dir": str(SOURCE_CACHE_DIR),
            "model_artifacts_dir": str(MODEL_ARTIFACTS_DIR),
            "logs_dir": str(LOGS_DIR),
            "training_logs_dir": str(TRAINING_LOGS_DIR),
            "continuous_learning_logs_dir": str(CONTINUOUS_LEARNING_LOGS_DIR),
            "backups_dir": str(OPS_BACKUPS_DIR),
            "settings_key_path": str(SETTINGS_KEY_PATH),
            "database_path": ((control_plane.get("storage") or {}).get("database") or {}).get("path"),
        },
        "logs": {
            "app": _file_meta(app_log),
            "events": _file_meta(events_log),
        },
        "backups": {
            "count": len(backups),
            "latest": backups[0] if backups else None,
            "items": backups,
        },
        "control_plane": control_plane,
    }


def get_operations_logs(limit: int = 100) -> dict[str, Any]:
    return {
        "events": read_recent_events(limit=limit),
        "app_tail": read_recent_app_log(limit=limit),
        "limit": int(limit),
    }
