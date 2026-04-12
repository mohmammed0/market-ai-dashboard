"""Smart Automation API routes."""

from fastapi import APIRouter

from backend.app.services.smart_automation import (
    clear_smart_alerts,
    get_smart_alerts,
    get_smart_automation_status,
    run_smart_cycle,
)

router = APIRouter(prefix="/smart", tags=["smart-automation"])


@router.get("/status")
async def smart_status():
    """Get smart automation status and recent alerts."""
    return get_smart_automation_status()


@router.get("/alerts")
async def smart_alerts(limit: int = 20):
    """Get recent smart alerts."""
    return {"alerts": get_smart_alerts(limit)}


@router.post("/cycle")
async def trigger_smart_cycle(symbol_limit: int = 10):
    """Manually trigger a smart automation cycle."""
    result = await run_smart_cycle(symbol_limit=symbol_limit)
    return result


@router.delete("/alerts")
async def clear_alerts():
    """Clear all smart alerts."""
    count = clear_smart_alerts()
    return {"cleared": count}
