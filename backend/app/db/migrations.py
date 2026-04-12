from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from backend.app.config import BACKEND_DIR, DATABASE_AUTO_MIGRATE, DATABASE_LEGACY_BOOTSTRAP, DATABASE_URL
from backend.app.db.base import Base
from backend.app.db.session import engine


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


def migrate_database() -> None:
    from backend.app import models  # noqa: F401

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    user_tables = existing_tables - {"alembic_version"}

    if not DATABASE_AUTO_MIGRATE:
        if DATABASE_LEGACY_BOOTSTRAP:
            Base.metadata.create_all(bind=engine)
        return

    config = _alembic_config()
    if "alembic_version" not in existing_tables:
        if not user_tables:
            command.upgrade(config, "head")
            return
        if DATABASE_LEGACY_BOOTSTRAP:
            Base.metadata.create_all(bind=engine)
        command.stamp(config, "head")
        return

    command.upgrade(config, "head")
