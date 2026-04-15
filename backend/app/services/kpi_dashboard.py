from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import logging
from math import sqrt
from statistics import mean, pstdev
from typing import Any

from backend.app.application.execution.service import get_trade_history
from backend.app.application.portfolio.service import get_portfolio_exposure
from backend.app.config import DEFAULT_SAMPLE_SYMBOLS, RISK_DEFAULT_PORTFOLIO_VALUE
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.services import get_cache
from backend.app.services.breadth_engine import compute_sector_rotation
from backend.app.services.events_calendar import fetch_market_events
from backend.app.services.market_data import fetch_quote_snapshots, load_history
from backend.app.services.llm_gateway import get_llm_status
from backend.app.services.risk_engine import get_risk_dashboard
from backend.app.services.strategy_lab import list_strategy_evaluations


logger = get_logger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _trade_rows(limit: int = 500) -> list[dict[str, Any]]:
    items = get_trade_history(limit=limit).get("items", [])
    normalized = []
    for item in items:
        created_at = _parse_datetime(item.get("created_at"))
        normalized.append({
            **item,
            "created_dt": created_at,
            "realized_pnl": _safe_float(item.get("realized_pnl")),
            "quantity": _safe_float(item.get("quantity")),
            "price": _safe_float(item.get("price")),
        })
    normalized.sort(key=lambda row: row.get("created_dt") or datetime.min)
    return normalized


def _equity_curve(trades: list[dict[str, Any]], base_equity: float) -> list[dict[str, Any]]:
    equity = float(base_equity)
    curve = [{"date": datetime.utcnow().date().isoformat(), "equity": round(equity, 2), "pnl": 0.0}] if not trades else []
    for trade in trades:
        equity += _safe_float(trade.get("realized_pnl"))
        created_dt = trade.get("created_dt")
        if created_dt is None:
            continue
        curve.append({
            "date": created_dt.date().isoformat(),
            "equity": round(equity, 2),
            "pnl": round(_safe_float(trade.get("realized_pnl")), 2),
        })
    return curve


def _daily_pnl(trades: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, float] = defaultdict(float)
    for trade in trades:
        created_dt = trade.get("created_dt")
        if created_dt is None:
            continue
        grouped[created_dt.date().isoformat()] += _safe_float(trade.get("realized_pnl"))
    return dict(sorted(grouped.items()))


def _monthly_return_stats(daily_pnl: dict[str, float], base_equity: float) -> dict[str, Any]:
    grouped: dict[str, float] = defaultdict(float)
    for day, pnl in daily_pnl.items():
        grouped[str(day)[:7]] += _safe_float(pnl)
    monthly_returns = [round((value / base_equity) * 100.0, 3) for value in grouped.values()] if base_equity else []
    monthly_std = pstdev(monthly_returns) if len(monthly_returns) > 1 else 0.0
    stability_score = round(100.0 / (1.0 + monthly_std), 2) if monthly_returns else 0.0
    return {
        "months": [{"month": key, "return_pct": round((value / base_equity) * 100.0, 3) if base_equity else 0.0} for key, value in sorted(grouped.items())],
        "stability_score": stability_score,
        "volatility_pct": round(monthly_std, 3),
    }


def _max_drawdown_pct(curve: list[dict[str, Any]]) -> float:
    peak = 0.0
    drawdown = 0.0
    for point in curve:
        equity = _safe_float(point.get("equity"))
        peak = max(peak, equity)
        if peak > 0:
            drawdown = min(drawdown, ((equity - peak) / peak) * 100.0)
    return round(abs(drawdown), 3)


def _max_consecutive_losses(trades: list[dict[str, Any]]) -> int:
    current = 0
    maximum = 0
    for trade in trades:
        if _safe_float(trade.get("realized_pnl")) < 0:
            current += 1
            maximum = max(maximum, current)
        elif _safe_float(trade.get("realized_pnl")) > 0:
            current = 0
    return maximum


def _holding_time_hours(trades: list[dict[str, Any]]) -> float:
    opened: dict[tuple[str, str], datetime] = {}
    durations: list[float] = []
    for trade in trades:
        created_dt = trade.get("created_dt")
        if created_dt is None:
            continue
        key = (str(trade.get("symbol") or ""), str(trade.get("strategy_mode") or ""))
        action = str(trade.get("action") or "").upper()
        if action == "OPEN":
            opened[key] = created_dt
        elif action == "CLOSE" and key in opened:
            durations.append((created_dt - opened[key]).total_seconds() / 3600.0)
            del opened[key]
    return round(mean(durations), 2) if durations else 0.0


def _benchmark_series(symbol: str, days: int = 180) -> list[dict[str, Any]]:
    history = load_history(symbol, interval="1d", persist=True)
    items = history.get("items", [])[-days:]
    closes = [_safe_float(item.get("close")) for item in items if item.get("close") is not None]
    if not closes:
        return []
    base = closes[0] or 1.0
    series = []
    for item in items:
        close = _safe_float(item.get("close"))
        if close <= 0:
            continue
        series.append({
            "date": str(item.get("datetime") or "")[:10],
            "close": round(close, 4),
            "return_pct": round(((close / base) - 1.0) * 100.0, 3),
        })
    return series


def _safe_call(name: str, func, default):
    try:
        return func()
    except Exception as exc:
        log_event(logger, logging.WARNING, "dashboard.kpi.partial_failure", component=name, error=str(exc))
        return default


def _lightweight_market_intelligence() -> dict[str, Any]:
    sample_symbols = [symbol for symbol in DEFAULT_SAMPLE_SYMBOLS[:6] if str(symbol).strip()] or ["AAPL", "MSFT", "NVDA", "SPY"]
    snapshots_payload = _safe_call(
        "quote_snapshots",
        lambda: fetch_quote_snapshots(sample_symbols, include_profile=True),
        {"items": []},
    )
    snapshots = snapshots_payload.get("items", [])
    advancing = [item for item in snapshots if _safe_float(item.get("change_pct")) > 0]
    declining = [item for item in snapshots if _safe_float(item.get("change_pct")) < 0]
    sector_rotation = _safe_call(
        "sector_rotation",
        compute_sector_rotation,
        {"leaders": [], "laggards": []},
    )
    events = _safe_call(
        "market_events",
        lambda: fetch_market_events(symbols=sample_symbols, limit=6),
        {"items": [], "note": "Event data is not currently available."},
    )
    llm_status = _safe_call(
        "llm_status",
        get_llm_status,
        {"effective_status": "unavailable", "effective_provider": None},
    )
    watchlist_opportunities = sorted(
        snapshots,
        key=lambda item: _safe_float(item.get("change_pct")),
        reverse=True,
    )[:6]
    breadth_ratio = round(len(advancing) / max(len(declining), 1), 3) if snapshots else 0.0
    return {
        "breadth": {
            "advancing": len(advancing),
            "declining": len(declining),
            "breadth_ratio": breadth_ratio,
            "new_highs": 0,
            "new_lows": 0,
            "sample_size": len(snapshots),
        },
        "sector_strength": sector_rotation.get("leaders", []),
        "sector_weakness": sector_rotation.get("laggards", []),
        "news_sentiment_summary": {
            "llm_ready": llm_status.get("effective_status") == "ready",
            "provider": llm_status.get("effective_provider"),
            "detail": llm_status.get("ollama", {}).get("detail") or llm_status.get("effective_status"),
        },
        "watchlist_opportunities": watchlist_opportunities,
        "events": events.get("items", [])[:6],
    }


def get_kpi_dashboard() -> dict[str, Any]:
    cache = get_cache()

    def build_payload() -> dict[str, Any]:
        base_equity = float(RISK_DEFAULT_PORTFOLIO_VALUE)
        trades = _trade_rows(limit=500)
        curve = _equity_curve(trades, base_equity)
        daily_pnl = _daily_pnl(trades)
        monthly = _monthly_return_stats(daily_pnl, base_equity)
        realized_values = [_safe_float(item.get("realized_pnl")) for item in trades if _safe_float(item.get("realized_pnl")) != 0]
        wins = [value for value in realized_values if value > 0]
        losses = [value for value in realized_values if value < 0]
        net_pnl = round(sum(realized_values), 2)
        total_return_pct = round((net_pnl / base_equity) * 100.0, 3) if base_equity else 0.0
        start_dt = trades[0].get("created_dt") if trades else None
        end_dt = trades[-1].get("created_dt") if trades else None
        period_days = max(((end_dt - start_dt).days if start_dt and end_dt else 0), 1)
        years = period_days / 365.25
        ending_equity = base_equity + net_pnl
        cagr = round((((ending_equity / base_equity) ** (1 / years)) - 1.0) * 100.0, 3) if base_equity > 0 and years > 0 else 0.0
        daily_returns = [round((value / base_equity) * 100.0, 4) for value in daily_pnl.values()] if base_equity else []
        volatility_pct = round(pstdev(daily_returns), 3) if len(daily_returns) > 1 else 0.0
        sharpe_like = round((mean(daily_returns) / pstdev(daily_returns)) * sqrt(len(daily_returns)), 3) if len(daily_returns) > 1 and pstdev(daily_returns) else 0.0
        risk = _safe_call(
            "risk_dashboard",
            lambda: get_risk_dashboard(base_equity),
            {"portfolio_warnings": [], "gross_exposure_pct": 0.0, "max_daily_loss_pct": 0.0},
        )
        exposure = _safe_call(
            "portfolio_exposure",
            get_portfolio_exposure,
            {"summary": {"largest_position_pct": 0.0}},
        )
        market_intelligence = _lightweight_market_intelligence()
        strategy_history = _safe_call(
            "strategy_evaluations",
            lambda: list_strategy_evaluations(limit=5),
            {"items": [], "count": 0},
        )
        latest_eval = strategy_history.get("items", [None])[0] if strategy_history.get("items") else None
        latest_leaderboard = latest_eval.get("leaderboard", []) if latest_eval else []
        spy_series = _safe_call("benchmark_spy", lambda: _benchmark_series("SPY"), [])
        qqq_series = _safe_call("benchmark_qqq", lambda: _benchmark_series("QQQ"), [])
        benchmark_summary = {
            "spy_total_return_pct": spy_series[-1]["return_pct"] if spy_series else 0.0,
            "qqq_total_return_pct": qqq_series[-1]["return_pct"] if qqq_series else 0.0,
            "strategy_total_return_pct": total_return_pct,
            "vs_spy_pct": round(total_return_pct - (spy_series[-1]["return_pct"] if spy_series else 0.0), 3),
            "vs_qqq_pct": round(total_return_pct - (qqq_series[-1]["return_pct"] if qqq_series else 0.0), 3),
        }

        best_day = max(daily_pnl.items(), key=lambda item: item[1]) if daily_pnl else None
        worst_day = min(daily_pnl.items(), key=lambda item: item[1]) if daily_pnl else None
        profit_factor = round(sum(wins) / abs(sum(losses)), 3) if losses else round(sum(wins), 3)
        expectancy = round((sum(realized_values) / len(realized_values)), 3) if realized_values else 0.0
        win_rate = round((len(wins) / len(realized_values)) * 100.0, 2) if realized_values else 0.0

        return {
            "generated_at": datetime.utcnow().isoformat(),
            "base_portfolio_value": base_equity,
            "performance": {
                "net_pnl": net_pnl,
                "total_return_pct": total_return_pct,
                "cagr_pct": cagr,
                "monthly_return_stability": monthly["stability_score"],
                "monthly_return_volatility_pct": monthly["volatility_pct"],
                "equity_curve": curve,
                "best_day": None if best_day is None else {"date": best_day[0], "pnl": round(best_day[1], 2)},
                "worst_day": None if worst_day is None else {"date": worst_day[0], "pnl": round(worst_day[1], 2)},
                "average_win": round(mean(wins), 2) if wins else 0.0,
                "average_loss": round(mean(losses), 2) if losses else 0.0,
            },
            "risk": {
                "max_drawdown_pct": _max_drawdown_pct(curve),
                "daily_loss_limit_tracking_pct": round((abs(worst_day[1]) / max(_safe_float(risk.get("max_daily_loss_pct")) * base_equity / 100.0, 1.0)) * 100.0, 2) if worst_day else 0.0,
                "volatility_pct": volatility_pct,
                "consecutive_losses": _max_consecutive_losses(trades),
                "risk_adjusted_return": sharpe_like,
                "exposure_concentration_pct": _safe_float(exposure.get("summary", {}).get("largest_position_pct")),
                "current_portfolio_risk_state": "warning" if risk.get("portfolio_warnings") else "stable",
                "warnings": risk.get("portfolio_warnings", []),
                "gross_exposure_pct": _safe_float(risk.get("gross_exposure_pct")),
            },
            "strategy_quality": {
                "win_rate_pct": win_rate,
                "profit_factor": profit_factor,
                "expectancy": expectancy,
                "average_holding_time_hours": _holding_time_hours(trades),
                "regime_performance": [
                    {"label": "أفضل عائد", "value": latest_leaderboard[0].get("candidate_name", latest_leaderboard[0].get("strategy", "-")) if latest_leaderboard else "-"},
                    {"label": "أفضل متانة", "value": latest_eval.get("best_strategy") if latest_eval else "-"},
                    {"label": "تقييمات محفوظة", "value": strategy_history.get("count", 0)},
                ],
                "signal_quality_summary": {
                    "recent_closed_trades": len([item for item in trades if str(item.get("action")).upper() == "CLOSE"]),
                    "positive_outcomes": len(wins),
                    "negative_outcomes": len(losses),
                },
                "leaderboard": latest_leaderboard,
            },
            "market_intelligence": {
                **market_intelligence,
            },
            "benchmark": {
                **benchmark_summary,
                "series": {
                    "spy": spy_series[-90:],
                    "qqq": qqq_series[-90:],
                    "strategy": curve[-90:],
                },
                "current_positioning_vs_benchmark": {
                    "gross_exposure_pct": _safe_float(risk.get("gross_exposure_pct")),
                    "largest_position_pct": _safe_float(exposure.get("summary", {}).get("largest_position_pct")),
                },
            },
        }

    return cache.get_or_set("dashboard:kpi", build_payload, ttl_seconds=60)
