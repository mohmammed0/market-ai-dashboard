from fastapi import APIRouter

from backend.app.application.portfolio.service import build_canonical_portfolio_snapshot, get_portfolio_exposure


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/exposure")
def portfolio_exposure():
    return get_portfolio_exposure()


@router.get("/snapshot")
def portfolio_snapshot():
    return build_canonical_portfolio_snapshot().model_dump(mode="json")
