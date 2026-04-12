from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.runtime_env import ENV_BOOTSTRAP_INFO, ROOT_DIR, load_local_env_file

load_local_env_file()
DATA_DIR = Path(os.getenv("MARKET_AI_DATA_DIR", str(ROOT_DIR / "data"))).resolve()
MODEL_ARTIFACTS_DIR = Path(os.getenv("MARKET_AI_MODEL_ARTIFACTS_DIR", str(ROOT_DIR / "model_artifacts"))).resolve()
SOURCE_CACHE_DIR = Path(os.getenv("MARKET_AI_SOURCE_CACHE_DIR", str(DATA_DIR / "source_cache"))).resolve()
LOGS_DIR = Path(os.getenv("MARKET_AI_LOGS_DIR", str(DATA_DIR / "logs"))).resolve()
BACKGROUND_JOB_LOGS_DIR = Path(os.getenv("MARKET_AI_BACKGROUND_JOB_LOGS_DIR", str(LOGS_DIR / "jobs"))).resolve()
TRAINING_LOGS_DIR = Path(os.getenv("MARKET_AI_TRAINING_LOGS_DIR", str(LOGS_DIR / "training"))).resolve()
CONTINUOUS_LEARNING_LOGS_DIR = Path(os.getenv("MARKET_AI_CONTINUOUS_LEARNING_LOGS_DIR", str(LOGS_DIR / "continuous_learning"))).resolve()
BACKUPS_DIR = Path(os.getenv("MARKET_AI_BACKUPS_DIR", str(ROOT_DIR / "backups"))).resolve()
CONTINUOUS_LEARNING_ARTIFACTS_DIR = Path(os.getenv("MARKET_AI_CONTINUOUS_LEARNING_ARTIFACTS_DIR", str(MODEL_ARTIFACTS_DIR / "continuous_learning"))).resolve()
SEED_SOURCE_DIR = ROOT_DIR / "seed_data" / "source_seed"
LEGACY_SOURCE_DIR = ROOT_DIR / "us_watchlist_source"
DEFAULT_DB_PATH = DATA_DIR / os.getenv("MARKET_AI_DB_FILENAME", "market_ai.db")
DEFAULT_RUNTIME_CACHE_DIR = DATA_DIR / "runtime_cache"
SETTINGS_KEY_PATH = Path(os.getenv("MARKET_AI_SETTINGS_KEY_PATH", str(DATA_DIR / ".settings.key"))).resolve()


def default_database_url() -> str:
    return f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"


def normalize_database_url(database_url: str | None) -> str:
    value = str(database_url or "").strip()
    if not value:
        return default_database_url()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://") and not value.startswith("postgresql+"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


def is_sqlite_url(database_url: str | None) -> bool:
    return normalize_database_url(database_url).startswith("sqlite")


def is_postgresql_url(database_url: str | None) -> bool:
    value = normalize_database_url(database_url)
    return value.startswith("postgresql://") or value.startswith("postgresql+")


def sqlite_file_path(database_url: str | None) -> Path | None:
    value = normalize_database_url(database_url)
    if not value.startswith("sqlite"):
        return None
    if value in {"sqlite://", "sqlite:///"}:
        return None

    if value.startswith("sqlite:////"):
        return Path(unquote(value.removeprefix("sqlite:////")))
    if value.startswith("sqlite:///"):
        raw_path = value.removeprefix("sqlite:///")
        path = Path(unquote(raw_path))
        return path if path.is_absolute() else (ROOT_DIR / path).resolve()

    parsed = urlparse(value)
    if parsed.scheme != "sqlite":
        return None
    if parsed.path:
        path = Path(unquote(parsed.path))
        return path if path.is_absolute() else (ROOT_DIR / path).resolve()
    return None


def ensure_runtime_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    CONTINUOUS_LEARNING_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_RUNTIME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    BACKGROUND_JOB_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    TRAINING_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    CONTINUOUS_LEARNING_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_database_parent(database_url: str | None) -> Path | None:
    sqlite_path = sqlite_file_path(database_url)
    if sqlite_path is None:
        return None
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite_path
