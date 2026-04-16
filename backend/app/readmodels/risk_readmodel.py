from __future__ import annotations

from backend.app.application.portfolio.service import get_portfolio_exposure
from backend.app.domain.risk.services.broker_health_guard import broker_health_guard
from backend.app.risk.service import get_risk_dashboard


def build_risk_readmodel() -> dict:
    return {
        "dashboard": get_risk_dashboard(),
        "exposure": get_portfolio_exposure(),
        "broker_health": broker_health_guard(),
    }


__all__ = ["build_risk_readmodel"]

