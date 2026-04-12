from fastapi import APIRouter, HTTPException

from backend.app.services import get_scheduler_status, start_scheduler


router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/status")
def scheduler_status():
    return get_scheduler_status()


@router.post("/start")
def scheduler_start():
    result = start_scheduler()
    if result.get("blocked"):
        raise HTTPException(status_code=409, detail=result.get("reason") or result.get("error") or "Scheduler cannot start in this process.")
    return result
