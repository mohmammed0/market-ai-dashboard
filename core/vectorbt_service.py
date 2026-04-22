from __future__ import annotations

from typing import Any

import pandas as pd

from core.legacy_adapters.backtest import _load_source_data, backtest_symbol_enhanced

try:
    import vectorbt as vbt
except Exception:  # pragma: no cover - optional dependency
    vbt = None


def _safe_float(value: Any, digits: int = 4):
    try:
        if value is None or pd.isna(value):
            return None
        return round(float(value), digits)
    except Exception:
        return None


def _safe_int(value: Any):
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except Exception:
        return None


def _build_boolean_series(index: pd.Index, event_dates: list[str]) -> pd.Series:
    date_index = pd.Index(pd.to_datetime(event_dates, errors="coerce")).dropna().unique()
    return pd.Series(index.normalize().isin(date_index), index=index)


def run_vectorbt_backtest(
    instrument="AAPL",
    start_date="2024-01-01",
    end_date="2026-04-02",
    hold_days=10,
    min_technical_score=2,
    buy_score_threshold=3,
    sell_score_threshold=4,
):
    classic_result = backtest_symbol_enhanced(
        instrument=instrument,
        start_date=start_date,
        end_date=end_date,
        hold_days=hold_days,
        min_technical_score=min_technical_score,
        buy_score_threshold=buy_score_threshold,
        sell_score_threshold=sell_score_threshold,
    )

    base_response = {
        "engine": "vectorbt",
        "instrument": instrument,
        "start_date": start_date,
        "end_date": end_date,
        "hold_days": int(hold_days),
        "min_technical_score": int(min_technical_score),
        "buy_score_threshold": int(buy_score_threshold),
        "sell_score_threshold": int(sell_score_threshold),
        "classic_summary": classic_result if isinstance(classic_result, dict) else None,
    }

    if classic_result.get("error"):
        return {
            **base_response,
            "error": classic_result.get("error"),
            "message": classic_result.get("message"),
            "equity_curve": [],
            "drawdown_curve": [],
            "returns_stats": {},
            "drawdown_stats": {},
        }

    if vbt is None:
        return {
            **base_response,
            "error": "vectorbt is not installed. Install backend requirements to enable vectorbt mode.",
            "message": "Classic backtest remains available.",
            "equity_curve": [],
            "drawdown_curve": [],
            "returns_stats": {},
            "drawdown_stats": {},
        }

    price_df, load_error = _load_source_data(instrument, start_date, end_date)
    if load_error:
        return {
            **base_response,
            "error": load_error,
            "message": "Unable to load source data for vectorbt.",
            "equity_curve": [],
            "drawdown_curve": [],
            "returns_stats": {},
            "drawdown_stats": {},
        }

    if price_df is None or price_df.empty:
        return {
            **base_response,
            "error": "No source data available for vectorbt backtest.",
            "message": "Classic backtest remains available.",
            "equity_curve": [],
            "drawdown_curve": [],
            "returns_stats": {},
            "drawdown_stats": {},
        }

    events_df = pd.DataFrame(classic_result.get("events", []))
    if events_df.empty:
        return {
            **base_response,
            "error": None,
            "message": classic_result.get("message") or "No qualified enhanced trades for vectorbt signals.",
            "trades": 0,
            "equity_curve": [],
            "drawdown_curve": [],
            "returns_stats": {},
            "drawdown_stats": {},
        }

    price_df = price_df.sort_values("datetime").copy()
    price_df["datetime"] = pd.to_datetime(price_df["datetime"], errors="coerce")
    price_df = price_df.dropna(subset=["datetime"])
    price_df["session_date"] = price_df["datetime"].dt.normalize()
    close = price_df.set_index("session_date")["close"].astype(float)

    buy_events = events_df[events_df["enhanced_signal"] == "BUY"]["datetime"].tolist()
    sell_events = events_df[events_df["enhanced_signal"] == "SELL"]["datetime"].tolist()

    long_entries = _build_boolean_series(close.index, buy_events)
    short_entries = _build_boolean_series(close.index, sell_events)
    long_exits = long_entries.shift(int(hold_days), fill_value=False)
    short_exits = short_entries.shift(int(hold_days), fill_value=False)

    portfolio = vbt.Portfolio.from_signals(
        close,
        entries=long_entries,
        exits=long_exits,
        short_entries=short_entries,
        short_exits=short_exits,
        init_cash=10000.0,
        fees=0.0,
        freq="1D",
    )

    value_series = portfolio.value()
    drawdown_series = portfolio.drawdown() * 100.0
    trades = portfolio.trades

    equity_curve = [
        {"date": str(idx)[:10], "equity": _safe_float(value)}
        for idx, value in value_series.items()
        if pd.notna(value)
    ]
    drawdown_curve = [
        {"date": str(idx)[:10], "drawdown_pct": _safe_float(value)}
        for idx, value in drawdown_series.items()
        if pd.notna(value)
    ]

    returns_stats = {
        "total_return_pct": _safe_float(portfolio.total_return() * 100.0),
        "annualized_return_pct": _safe_float(portfolio.annualized_return() * 100.0),
        "sharpe_ratio": _safe_float(portfolio.sharpe_ratio()),
        "sortino_ratio": _safe_float(portfolio.sortino_ratio()),
        "calmar_ratio": _safe_float(portfolio.calmar_ratio()),
    }
    drawdown_stats = {
        "max_drawdown_pct": _safe_float(portfolio.max_drawdown() * 100.0),
        "max_gross_exposure_pct": _safe_float(portfolio.gross_exposure().max() * 100.0),
    }

    stats = {
        **base_response,
        "error": None,
        "message": None,
        "trades": _safe_int(trades.count()),
        "winning_trades": _safe_int(trades.winning.count()),
        "losing_trades": _safe_int(trades.losing.count()),
        "win_rate_pct": _safe_float(trades.win_rate() * 100.0),
        "profit_factor": _safe_float(trades.profit_factor()),
        "expectancy": _safe_float(trades.expectancy()),
        "final_equity": _safe_float(value_series.iloc[-1]) if not value_series.empty else None,
        "returns_stats": returns_stats,
        "drawdown_stats": drawdown_stats,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "events": classic_result.get("events", []),
    }
    return stats
