from fastapi import APIRouter, Query

from backend.app.application.alerts.service import list_alert_history
from backend.app.services.advanced_alerts import generate_advanced_alerts
from backend.app.services.market_universe import resolve_universe_preset


router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/history")
def alert_history(limit: int = Query(default=100, ge=1, le=500), severity: str | None = None):
    return list_alert_history(limit=limit, severity=severity)


@router.post("/run")
def run_alert_cycle(preset: str = "ALL_US_EQUITIES", limit: int = 30, dry_run: bool = False):
    try:
        universe = resolve_universe_preset(preset, limit=limit)
        return generate_advanced_alerts(universe.get("symbols", []), persist=not dry_run)
    except Exception as exc:
        return {"items": [], "count": 0, "error": str(exc)}
