from fastapi import APIRouter

from backend.app.readmodels import build_dashboard_readmodel
from backend.app.schemas import DashboardLiteResponse, DashboardWidgetResponse
from backend.app.services.dashboard_hub import (
    get_dashboard_lite,
    get_dashboard_market_widget,
    get_dashboard_ops_widget,
    get_dashboard_portfolio_widget,
    get_dashboard_summary,
)
from backend.app.services.kpi_dashboard import get_kpi_dashboard


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary():
    return build_dashboard_readmodel(compact=False)


@router.get("/lite", response_model=DashboardLiteResponse)
def dashboard_lite():
    return build_dashboard_readmodel(compact=True)


@router.get("/widgets/market", response_model=DashboardWidgetResponse)
def dashboard_market_widget():
    return get_dashboard_market_widget()


@router.get("/widgets/portfolio", response_model=DashboardWidgetResponse)
def dashboard_portfolio_widget():
    return get_dashboard_portfolio_widget()


@router.get("/widgets/ops", response_model=DashboardWidgetResponse)
def dashboard_ops_widget():
    return get_dashboard_ops_widget()


@router.get("/kpis")
def dashboard_kpis():
    return get_kpi_dashboard()
