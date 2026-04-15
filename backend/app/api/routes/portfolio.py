from fastapi import APIRouter

from backend.app.application.portfolio.service import (
    build_portfolio_snapshot_payload,
    get_portfolio_exposure,
)
from backend.app.domain.portfolio.contracts import PortfolioSnapshotV1


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/exposure")
def portfolio_exposure():
    return get_portfolio_exposure()


@router.get("/snapshot", response_model=PortfolioSnapshotV1)
def portfolio_snapshot():
    return build_portfolio_snapshot_payload()
