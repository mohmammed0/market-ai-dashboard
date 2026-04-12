from fastapi import APIRouter, Query

from backend.app.services.continuous_learning import (
    get_continuous_learning_status,
    list_continuous_learning_artifacts,
    pause_continuous_learning,
    resume_continuous_learning,
    start_continuous_learning,
)


router = APIRouter(prefix="/continuous-learning", tags=["continuous-learning"])


@router.get("/status")
def continuous_learning_status(limit: int = Query(default=10, ge=1, le=50)):
    return get_continuous_learning_status(limit=limit)


@router.get("/artifacts")
def continuous_learning_artifacts(limit: int = Query(default=20, ge=1, le=100)):
    return list_continuous_learning_artifacts(limit=limit)


@router.post("/start")
def continuous_learning_start():
    return start_continuous_learning(requested_by="api")


@router.post("/pause")
def continuous_learning_pause():
    return pause_continuous_learning(requested_by="api")


@router.post("/resume")
def continuous_learning_resume():
    return resume_continuous_learning(requested_by="api")
