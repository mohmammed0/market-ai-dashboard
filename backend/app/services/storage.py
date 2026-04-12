import json
from contextlib import contextmanager

from backend.app.db.session import SessionLocal


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dumps_json(payload):
    try:
        return json.dumps(payload, default=str)
    except Exception:
        return json.dumps({"error": "json_encode_failed"})


def loads_json(payload, default=None):
    if not payload:
        return {} if default is None else default
    try:
        return json.loads(payload)
    except Exception:
        return {} if default is None else default
