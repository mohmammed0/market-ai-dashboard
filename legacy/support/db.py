from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core.runtime_paths import default_database_url, ensure_database_parent, ensure_runtime_directories


DATABASE_URL = default_database_url()

ensure_runtime_directories()
ensure_database_parent(DATABASE_URL)

engine = create_engine(
    DATABASE_URL,
    future=True,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True
)

Base = declarative_base()


def init_db():
    from legacy.support import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
