from __future__ import annotations

from backend.app.application.execution.service import get_internal_portfolio
from backend.app.application.portfolio.service import build_portfolio_snapshot_payload, get_portfolio_exposure


def build_portfolio_readmodel(limit: int = 100) -> dict:
    return {
        "snapshot": build_portfolio_snapshot_payload().model_dump(mode="json"),
        "internal": get_internal_portfolio(limit=limit),
        "exposure": get_portfolio_exposure(),
    }


__all__ = ["build_portfolio_readmodel"]

