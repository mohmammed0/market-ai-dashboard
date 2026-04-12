from __future__ import annotations

import argparse
import json
import sys
import tarfile
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.runtime_paths import BACKUPS_DIR, DATA_DIR, LOGS_DIR, MODEL_ARTIFACTS_DIR, SETTINGS_KEY_PATH, SOURCE_CACHE_DIR, is_postgresql_url, sqlite_file_path
from backend.app.config import DATABASE_URL


def _repo_root() -> Path:
    return ROOT_DIR


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_repo_root()))
    except Exception:
        return path.name


def build_backup(args: argparse.Namespace) -> dict:
    backup_id = datetime.utcnow().strftime("market_ai_backup_%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir or BACKUPS_DIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{backup_id}.tar.gz"
    manifest_path = output_dir / f"{backup_id}.manifest.json"

    database_path = sqlite_file_path(DATABASE_URL)
    includes: list[dict] = []
    warnings: list[str] = []
    notes: list[str] = [
        "قاعدة البيانات تتضمن إعدادات التشغيل المخزنة بشكل مشفر.",
        "مفتاح فك تشفير الإعدادات لا يُضمّن افتراضياً داخل النسخة الاحتياطية.",
    ]

    candidates: list[tuple[Path, str]] = []
    if database_path and database_path.exists():
        candidates.append((database_path, _relative(database_path)))
        includes.append({"label": "sqlite_database", "path": _relative(database_path)})
    else:
        if is_postgresql_url(DATABASE_URL):
            warnings.append("PostgreSQL runtime data is not included by this backup script. Use pg_dump or platform-native PostgreSQL backups separately.")
            notes.append("إذا كانت بيئة الإنتاج تعمل على PostgreSQL فانسخ قاعدة البيانات باستخدام pg_dump أو آلية النسخ الاحتياطي الخاصة بالمنصة.")
        else:
            warnings.append("SQLite database file was not found and was not included.")

    if MODEL_ARTIFACTS_DIR.exists():
        candidates.append((MODEL_ARTIFACTS_DIR, _relative(MODEL_ARTIFACTS_DIR)))
        includes.append({"label": "model_artifacts", "path": _relative(MODEL_ARTIFACTS_DIR)})

    if SOURCE_CACHE_DIR.exists():
        candidates.append((SOURCE_CACHE_DIR, _relative(SOURCE_CACHE_DIR)))
        includes.append({"label": "source_cache", "path": _relative(SOURCE_CACHE_DIR)})

    if args.include_runtime_cache:
        runtime_cache_dir = DATA_DIR / "runtime_cache"
        if runtime_cache_dir.exists():
            candidates.append((runtime_cache_dir, _relative(runtime_cache_dir)))
            includes.append({"label": "runtime_cache", "path": _relative(runtime_cache_dir)})

    if args.include_logs and LOGS_DIR.exists():
        candidates.append((LOGS_DIR, _relative(LOGS_DIR)))
        includes.append({"label": "logs", "path": _relative(LOGS_DIR)})

    if args.include_settings_key:
        if SETTINGS_KEY_PATH.exists():
            candidates.append((SETTINGS_KEY_PATH, _relative(SETTINGS_KEY_PATH)))
            includes.append({"label": "settings_key", "path": _relative(SETTINGS_KEY_PATH)})
            warnings.append("The settings encryption key was included. Store this backup in a restricted location.")
        else:
            warnings.append("Requested settings key inclusion, but the key file was not found.")
    else:
        notes.append("إذا أردت استعادة مفاتيح OpenAI/Alpaca من النسخة نفسها، خزّن مفتاح data/.settings.key بشكل منفصل وآمن.")

    with tarfile.open(archive_path, "w:gz") as archive:
        for source_path, archive_name in candidates:
            if source_path.exists():
                archive.add(source_path, arcname=archive_name, recursive=True)

    manifest = {
        "backup_id": backup_id,
        "created_at": datetime.utcnow().isoformat(),
        "archive_name": archive_path.name,
        "archive_path": str(archive_path),
        "includes": includes,
        "warnings": warnings,
        "notes": notes,
        "restore_notes": [
            "استعد قاعدة البيانات والـ artifacts أولاً.",
            "أعد إدخال الأسرار من الواجهة إذا لم تسترجع مفتاح التشفير بشكل منفصل وآمن.",
            "بعد الاستعادة شغّل فحص /health و /ready ثم راجع واجهة العمليات.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a production-safe Market AI runtime backup.")
    parser.add_argument("--output-dir", default=str(BACKUPS_DIR), help="Directory to write backup archives into.")
    parser.add_argument("--include-runtime-cache", action="store_true", help="Include data/runtime_cache in the archive.")
    parser.add_argument("--include-logs", action="store_true", help="Include data/logs in the archive.")
    parser.add_argument("--include-settings-key", action="store_true", help="Include data/.settings.key. Use only in a secure secret-handling flow.")
    args = parser.parse_args()

    manifest = build_backup(args)
    print(json.dumps(manifest, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
