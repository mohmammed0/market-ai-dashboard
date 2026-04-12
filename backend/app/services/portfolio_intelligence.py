"""
Portfolio beta & correlation intelligence using OhlcvBar data from the DB.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _fetch_price_series(symbols: list[str], lookback_days: int = 252) -> dict:
    """Fetch close prices from OhlcvBar for given symbols, last N calendar days."""
    try:
        import numpy as np
        from backend.app.models import OhlcvBar
        from backend.app.services.storage import session_scope

        cutoff = datetime.utcnow() - timedelta(days=lookback_days + 30)  # buffer for weekends
        prices: dict[str, dict] = {s: {} for s in symbols}

        with session_scope() as session:
            rows = (
                session.query(OhlcvBar.symbol, OhlcvBar.bar_time, OhlcvBar.close)
                .filter(OhlcvBar.symbol.in_(symbols))
                .filter(OhlcvBar.timeframe == "1d")
                .filter(OhlcvBar.bar_time >= cutoff)
                .filter(OhlcvBar.close.isnot(None))
                .order_by(OhlcvBar.bar_time)
                .all()
            )

        for sym, bar_time, close in rows:
            date_key = bar_time.date().isoformat()
            prices[sym][date_key] = float(close)

        return prices
    except Exception as exc:
        logger.warning("_fetch_price_series failed: %s", exc)
        return {s: {} for s in symbols}


def _prices_to_returns(price_dict: dict) -> "tuple[list[str], object]":
    """Convert {date: price} dicts to aligned return arrays using pandas."""
    try:
        import pandas as pd

        series = {sym: pd.Series(data, dtype=float) for sym, data in price_dict.items() if data}
        if not series:
            return [], None
        df = pd.DataFrame(series).sort_index()
        df.index = pd.to_datetime(df.index)
        returns = df.pct_change().dropna(how="all")
        return list(returns.columns), returns
    except Exception as exc:
        logger.warning("_prices_to_returns failed: %s", exc)
        return [], None


def compute_portfolio_beta(
    symbols: list[str],
    weights: Optional[dict[str, float]] = None,
) -> dict:
    """Compute weighted portfolio beta vs SPY.

    Uses OhlcvBar data from DB (last 252 trading days).
    Returns: {portfolio_beta, symbol_betas: {sym: beta}, benchmark: "SPY"}
    """
    try:
        import numpy as np

        BENCHMARK = "SPY"
        all_symbols = list({BENCHMARK} | set(symbols))
        price_data = _fetch_price_series(all_symbols, lookback_days=400)
        cols, returns_df = _prices_to_returns(price_data)

        if returns_df is None or BENCHMARK not in returns_df.columns:
            return {
                "portfolio_beta": None,
                "symbol_betas": {},
                "benchmark": BENCHMARK,
                "warning": "Insufficient data — SPY not available in DB",
            }

        benchmark_returns = returns_df[BENCHMARK].dropna()
        symbol_betas: dict[str, float] = {}

        for sym in symbols:
            if sym == BENCHMARK or sym not in returns_df.columns:
                continue
            sym_ret = returns_df[sym].dropna()
            aligned = sym_ret.align(benchmark_returns, join="inner")
            sym_a, bench_a = aligned[0].values, aligned[1].values
            if len(sym_a) < 10:
                continue
            try:
                cov_matrix = np.cov(sym_a, bench_a)
                beta = cov_matrix[0, 1] / cov_matrix[1, 1] if cov_matrix[1, 1] != 0 else None
                symbol_betas[sym] = round(float(beta), 4) if beta is not None else None
            except Exception:
                symbol_betas[sym] = None

        # Portfolio beta = weighted average
        if weights:
            total_w = sum(weights.get(s, 0) for s in symbol_betas)
            if total_w > 0:
                portfolio_beta = sum(
                    (weights.get(s, 0) / total_w) * (b or 0)
                    for s, b in symbol_betas.items()
                )
            else:
                valid = [b for b in symbol_betas.values() if b is not None]
                portfolio_beta = sum(valid) / len(valid) if valid else None
        else:
            valid = [b for b in symbol_betas.values() if b is not None]
            portfolio_beta = sum(valid) / len(valid) if valid else None

        return {
            "portfolio_beta": round(float(portfolio_beta), 4) if portfolio_beta is not None else None,
            "symbol_betas": symbol_betas,
            "benchmark": BENCHMARK,
            "symbols_used": list(symbol_betas.keys()),
            "data_points": len(benchmark_returns),
        }
    except Exception as exc:
        logger.exception("compute_portfolio_beta failed")
        return {"portfolio_beta": None, "symbol_betas": {}, "benchmark": "SPY", "error": str(exc)}


def compute_correlation_matrix(
    symbols: list[str],
    lookback_days: int = 60,
) -> dict:
    """Compute pairwise return correlations from OHLCV DB data.

    Returns: {symbols, matrix (NxN list of lists), dates_used}
    """
    try:
        import numpy as np

        price_data = _fetch_price_series(symbols, lookback_days=lookback_days + 30)
        cols, returns_df = _prices_to_returns(price_data)

        if returns_df is None or returns_df.empty:
            return {
                "symbols": symbols,
                "matrix": [],
                "dates_used": 0,
                "warning": "Insufficient data in DB",
            }

        # Only include symbols with enough data
        min_points = max(10, lookback_days // 4)
        valid_cols = [c for c in returns_df.columns if returns_df[c].count() >= min_points]
        if not valid_cols:
            return {"symbols": symbols, "matrix": [], "dates_used": 0, "warning": "Not enough data points"}

        sub = returns_df[valid_cols].dropna(how="all")
        corr = sub.corr(method="pearson")

        matrix = [[round(corr.loc[r, c], 4) if (r in corr.index and c in corr.columns) else None
                   for c in valid_cols]
                  for r in valid_cols]

        return {
            "symbols": valid_cols,
            "matrix": matrix,
            "dates_used": len(sub),
            "lookback_days": lookback_days,
        }
    except Exception as exc:
        logger.exception("compute_correlation_matrix failed")
        return {"symbols": symbols, "matrix": [], "dates_used": 0, "error": str(exc)}


def _compute_max_drawdown(returns_series) -> float:
    """Compute maximum drawdown from a returns series."""
    try:
        import numpy as np
        cum = (1 + returns_series.fillna(0)).cumprod()
        roll_max = cum.cummax()
        drawdown = (cum - roll_max) / roll_max
        return round(float(drawdown.min()), 4)
    except Exception:
        return 0.0


def portfolio_risk_summary(
    symbols: list[str],
    weights: Optional[dict[str, float]] = None,
) -> dict:
    """Full portfolio risk: beta, correlation, volatility, max_drawdown.

    Returns combined dict for dashboard display.
    """
    try:
        import numpy as np

        beta_result = compute_portfolio_beta(symbols, weights)
        corr_result = compute_correlation_matrix(symbols, lookback_days=60)

        # Compute individual volatilities
        price_data = _fetch_price_series(symbols, lookback_days=252)
        cols, returns_df = _prices_to_returns(price_data)

        volatilities: dict[str, float] = {}
        if returns_df is not None:
            for sym in symbols:
                if sym in returns_df.columns:
                    std = returns_df[sym].std()
                    ann_vol = float(std) * (252 ** 0.5) * 100  # annualized %
                    volatilities[sym] = round(ann_vol, 2)

        # Weighted portfolio volatility (simplified — ignores correlations for quick summary)
        if weights and volatilities:
            total_w = sum(weights.get(s, 0) for s in volatilities)
            if total_w > 0:
                port_vol = sum((weights.get(s, 0) / total_w) * v for s, v in volatilities.items())
            else:
                vals = list(volatilities.values())
                port_vol = sum(vals) / len(vals) if vals else None
        else:
            vals = list(volatilities.values())
            port_vol = round(sum(vals) / len(vals), 2) if vals else None

        # Max drawdowns
        drawdowns: dict[str, float] = {}
        if returns_df is not None:
            for sym in symbols:
                if sym in returns_df.columns:
                    drawdowns[sym] = _compute_max_drawdown(returns_df[sym].dropna())

        return {
            "portfolio_beta": beta_result.get("portfolio_beta"),
            "symbol_betas": beta_result.get("symbol_betas", {}),
            "benchmark": beta_result.get("benchmark", "SPY"),
            "correlation": {
                "symbols": corr_result.get("symbols", []),
                "matrix": corr_result.get("matrix", []),
                "dates_used": corr_result.get("dates_used", 0),
            },
            "volatilities_annualized_pct": volatilities,
            "portfolio_volatility_pct": port_vol,
            "max_drawdowns": drawdowns,
            "symbols": symbols,
            "weights": weights,
        }
    except Exception as exc:
        logger.exception("portfolio_risk_summary failed")
        return {
            "portfolio_beta": None,
            "symbol_betas": {},
            "correlation": {},
            "volatilities_annualized_pct": {},
            "portfolio_volatility_pct": None,
            "max_drawdowns": {},
            "error": str(exc),
        }
