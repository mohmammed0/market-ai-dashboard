from fastapi import APIRouter, HTTPException, Query

from backend.app.services.background_jobs import get_background_job, list_background_jobs


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job_status(job_id: str):
    payload = get_background_job(job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Background job not found: {job_id}")
    return payload


@router.get("")
def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
):
    return list_background_jobs(limit=limit, job_type=type, status=status)
