from fastapi import APIRouter

from backend.app.services.dashboard_hub import get_dashboard_summary
from backend.app.services.kpi_dashboard import get_kpi_dashboard


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary():
    return get_dashboard_summary()


@router.get("/kpis")
def dashboard_kpis():
    return get_kpi_dashboard()
