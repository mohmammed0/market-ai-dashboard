from fastapi import APIRouter

from backend.app.readmodels import build_risk_readmodel
from backend.app.schemas.requests import RiskPlanRequest
from backend.app.risk.service import build_trade_risk_plan, get_risk_dashboard


router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/dashboard")
def risk_dashboard():
    return get_risk_dashboard()


@router.get("/readmodel")
def risk_readmodel():
    return build_risk_readmodel()


@router.post("/plan")
def risk_plan(payload: RiskPlanRequest):
    return build_trade_risk_plan(
        entry_price=payload.entry_price,
        stop_loss_price=payload.stop_loss_price,
        take_profit_price=payload.take_profit_price,
        portfolio_value=payload.portfolio_value,
        risk_per_trade_pct=payload.risk_per_trade_pct,
        max_daily_loss_pct=payload.max_daily_loss_pct,
        atr_pct=payload.atr_pct,
    )
