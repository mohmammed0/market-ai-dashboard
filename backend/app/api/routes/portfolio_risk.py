from __future__ import annotations

from fastapi import APIRouter

from backend.app.services.portfolio_intelligence import (
    compute_correlation_matrix,
    compute_portfolio_beta,
    portfolio_risk_summary,
)

router = APIRouter(prefix="/portfolio-risk", tags=["risk"])


def _parse_symbols(symbols_str: str) -> list[str]:
    return [s.strip().upper() for s in symbols_str.split(",") if s.strip()]


def _parse_weights(weights_str: str | None, symbols: list[str]) -> dict[str, float] | None:
    if not weights_str:
        return None
    try:
        parts = [float(w.strip()) for w in weights_str.split(",") if w.strip()]
        if len(parts) == len(symbols):
            return dict(zip(symbols, parts))
    except Exception:
        pass
    return None


@router.get("/beta")
def get_portfolio_beta(
    symbols: str = "AAPL,MSFT,NVDA,SPY",
    weights: str = None,
):
    """Portfolio beta vs SPY. symbols is comma-separated.
    weights is optional comma-separated floats in same order as symbols.
    """
    sym_list = _parse_symbols(symbols)
    weight_dict = _parse_weights(weights, sym_list)
    return compute_portfolio_beta(sym_list, weight_dict)


@router.get("/correlation")
def get_correlation_matrix(
    symbols: str = "AAPL,MSFT,NVDA,SPY",
    lookback_days: int = 60,
):
    """Pairwise correlation matrix."""
    sym_list = _parse_symbols(symbols)
    return compute_correlation_matrix(sym_list, lookback_days)


@router.get("/summary")
def get_portfolio_risk_summary(
    symbols: str = "AAPL,MSFT,NVDA,SPY",
    weights: str = None,
):
    """Full portfolio risk summary including beta, correlation, volatility, max_drawdown."""
    sym_list = _parse_symbols(symbols)
    weight_dict = _parse_weights(weights, sym_list)
    return portfolio_risk_summary(sym_list, weight_dict)
