from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker

from backend.app.config import (
    DATABASE_APPLICATION_NAME,
    DATABASE_CONNECT_TIMEOUT_SECONDS,
    DATABASE_IS_POSTGRESQL,
    DATABASE_IS_SQLITE,
    DATABASE_MAX_OVERFLOW,
    DATABASE_POOL_RECYCLE_SECONDS,
    DATABASE_POOL_SIZE,
    DATABASE_URL,
)
from core.runtime_paths import ensure_database_parent, ensure_runtime_directories


ensure_runtime_directories()
ensure_database_parent(DATABASE_URL)

_engine_kwargs = {
    "future": True,
    "echo": False,
}
if DATABASE_IS_SQLITE:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    _engine_kwargs["poolclass"] = NullPool
elif DATABASE_IS_POSTGRESQL:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"] = DATABASE_POOL_SIZE
    _engine_kwargs["max_overflow"] = DATABASE_MAX_OVERFLOW
    _engine_kwargs["pool_recycle"] = DATABASE_POOL_RECYCLE_SECONDS
    _engine_kwargs["connect_args"] = {
        "connect_timeout": DATABASE_CONNECT_TIMEOUT_SECONDS,
        "application_name": DATABASE_APPLICATION_NAME,
    }

engine = create_engine(DATABASE_URL, **_engine_kwargs)

# Enable WAL mode for SQLite — better concurrent read/write performance
if DATABASE_IS_SQLITE:
    from sqlalchemy import event, text as _text

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA cache_size=-20000")  # 20MB cache
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(*, run_migrations: bool = True):
    if not run_migrations:
        return
    from backend.app.db.migrations import migrate_database

    migrate_database()
