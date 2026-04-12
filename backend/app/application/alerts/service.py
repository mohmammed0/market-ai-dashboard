from __future__ import annotations

from backend.app.domain.alerts.contracts import AlertRecord
from backend.app.repositories.execution import ExecutionRepository
from backend.app.services.market_universe import resolve_universe_preset
from backend.app.services.storage import session_scope


def list_alert_history(limit: int = 100, severity: str | None = None) -> dict:
    with session_scope() as session:
        repo = ExecutionRepository(session)
        rows = repo.list_alerts(limit=limit, severity=severity)
        return {"items": [row.model_dump(mode="json") for row in rows], "count": len(rows)}


def append_alert(record: AlertRecord) -> dict:
    with session_scope() as session:
        repo = ExecutionRepository(session)
        return repo.append_alert(record).model_dump(mode="json")


def resolve_alert_symbols(preset: str = "ALL_US_EQUITIES", limit: int = 30) -> list[str]:
    universe = resolve_universe_preset(preset, limit=limit)
    return universe.get("symbols", [])
