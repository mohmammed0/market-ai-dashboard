from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import pandas as pd

from backend.app.application.broker.service import get_broker_summary
from backend.app.application.execution.service import get_internal_portfolio
from backend.app.domain.portfolio.contracts import PortfolioPosition, PortfolioSnapshot, PortfolioSourceSummary
from backend.app.services.market_data import load_history
from backend.app.services.market_profiles import load_symbol_profiles


def _correlation_warnings(symbols: list[str], weights: dict[str, float]) -> list[str]:
    if len(symbols) < 2:
        return []
    history_parts = {}
    for symbol in symbols:
        history = load_history(symbol, interval="1d", persist=True)
        items = history.get("items", [])
        if not items:
            continue
        frame = pd.DataFrame(items)
        if frame.empty or "close" not in frame.columns:
            continue
        history_parts[symbol] = pd.to_numeric(frame["close"], errors="coerce").tail(60).reset_index(drop=True)
    if len(history_parts) < 2:
        return []
    history_frame = pd.DataFrame(history_parts).dropna(how="any")
    if history_frame.empty or len(history_frame) < 10:
        return []
    returns = history_frame.pct_change().dropna(how="any")
    if returns.empty:
        return []
    corr = returns.corr()
    warnings = []
    seen = set()
    for left in corr.columns:
        for right in corr.columns:
            if left == right:
                continue
            pair = tuple(sorted((left, right)))
            if pair in seen:
                continue
            seen.add(pair)
            value = float(corr.loc[left, right])
            if abs(value) >= 0.8 and weights.get(left, 0.0) >= 0.15 and weights.get(right, 0.0) >= 0.15:
                warnings.append(f"{left} and {right} are highly correlated ({value:.2f}) while both carry meaningful exposure.")
    return warnings


def build_canonical_portfolio_snapshot() -> PortfolioSnapshot:
    internal = get_internal_portfolio(limit=500)
    broker = get_broker_summary()
    raw_positions: list[PortfolioPosition] = []

    for item in internal.get("items", []):
        raw_positions.append(PortfolioPosition(
            portfolio_source="internal_paper",
            symbol=item["symbol"],
            side=item["side"],
            quantity=float(item.get("quantity") or 0.0),
            current_price=item.get("current_price"),
            market_value=float(item.get("market_value") or 0.0),
            unrealized_pnl=float(item.get("unrealized_pnl") or 0.0),
            realized_pnl=float(item.get("realized_pnl") or 0.0),
            strategy_mode=item.get("strategy_mode"),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        ))

    broker_source = "broker_paper" if broker.get("paper", True) else "broker_live"
    for item in broker.get("positions", []):
        raw_positions.append(PortfolioPosition(
            portfolio_source=broker_source,
            symbol=item.get("symbol") or "",
            side=item.get("side") or "",
            quantity=float(item.get("qty") or 0.0),
            current_price=float(item.get("current_price") or 0.0),
            market_value=float(item.get("market_value") or 0.0),
            unrealized_pnl=float(item.get("unrealized_pnl") or 0.0),
            realized_pnl=0.0,
            strategy_mode="broker",
        ))

    total_market_value = sum(abs(item.market_value) for item in raw_positions)
    profiles = load_symbol_profiles([item.symbol for item in raw_positions if item.symbol])
    by_source = defaultdict(lambda: {"positions": 0, "market_value": 0.0, "unrealized_pnl": 0.0})

    for item in raw_positions:
        profile = profiles.get(item.symbol, {})
        item.sector = profile.get("sector", "Unknown")
        item.industry = profile.get("industry", "Unknown")
        item.market_cap_bucket = profile.get("market_cap_bucket", "Unknown")
        item.weight_pct = round((abs(item.market_value) / total_market_value) * 100.0, 2) if total_market_value else 0.0
        by_source[item.portfolio_source]["positions"] += 1
        by_source[item.portfolio_source]["market_value"] += abs(item.market_value)
        by_source[item.portfolio_source]["unrealized_pnl"] += item.unrealized_pnl

    return PortfolioSnapshot(
        generated_at=datetime.utcnow(),
        positions=raw_positions,
        sources=[PortfolioSourceSummary(source=source, positions=values["positions"], market_value=round(values["market_value"], 2), unrealized_pnl=round(values["unrealized_pnl"], 2)) for source, values in by_source.items()],
        total_market_value=round(total_market_value, 2),
        total_unrealized_pnl=round(sum(item.unrealized_pnl for item in raw_positions), 2),
    )


def get_portfolio_exposure() -> dict:
    snapshot = build_canonical_portfolio_snapshot()
    items = [item.model_dump(mode="json") for item in snapshot.positions]
    total_market_value = snapshot.total_market_value
    by_symbol = []
    by_sector = defaultdict(lambda: {"market_value": 0.0, "symbols": 0})
    by_bucket = defaultdict(lambda: {"market_value": 0.0, "symbols": 0})
    weights = {}

    for item in items:
        market_value = abs(float(item.get("market_value") or 0.0))
        weight = (market_value / total_market_value) if total_market_value else 0.0
        by_symbol.append({"symbol": item["symbol"], "portfolio_source": item["portfolio_source"], "sector": item.get("sector", "Unknown"), "market_cap_bucket": item.get("market_cap_bucket", "Unknown"), "market_value": round(market_value, 2), "weight_pct": round(weight * 100.0, 2), "side": item["side"], "strategy_mode": item.get("strategy_mode")})
        by_sector[item.get("sector", "Unknown")]["market_value"] += market_value
        by_sector[item.get("sector", "Unknown")]["symbols"] += 1
        by_bucket[item.get("market_cap_bucket", "Unknown")]["market_value"] += market_value
        by_bucket[item.get("market_cap_bucket", "Unknown")]["symbols"] += 1
        weights[item["symbol"]] = weight

    warnings = []
    for row in by_symbol:
        if row["weight_pct"] >= 25:
            warnings.append(f"{row['symbol']} represents {row['weight_pct']}% of the portfolio and exceeds the concentration threshold.")
    warnings.extend(_correlation_warnings([item["symbol"] for item in items], weights))
    if any(item["portfolio_source"] == "broker_live" for item in items):
        warnings.append("Live broker holdings are present in the canonical portfolio. Live execution remains disabled, but reconciliation should be reviewed before enabling any order workflow.")

    return {
        "summary": {"open_positions": len(items), "total_market_value": round(total_market_value, 2), "largest_position_pct": round(max([row["weight_pct"] for row in by_symbol], default=0.0), 2), "sources": [source.model_dump(mode="json") for source in snapshot.sources]},
        "positions": items,
        "by_symbol": sorted(by_symbol, key=lambda item: item["weight_pct"], reverse=True),
        "by_sector": [{"sector": sector, "market_value": round(values["market_value"], 2), "symbols": values["symbols"], "weight_pct": round((values["market_value"] / total_market_value) * 100.0, 2) if total_market_value else 0.0} for sector, values in sorted(by_sector.items(), key=lambda item: item[1]["market_value"], reverse=True)],
        "by_market_cap_bucket": [{"bucket": bucket, "market_value": round(values["market_value"], 2), "symbols": values["symbols"], "weight_pct": round((values["market_value"] / total_market_value) * 100.0, 2) if total_market_value else 0.0} for bucket, values in sorted(by_bucket.items(), key=lambda item: item[1]["market_value"], reverse=True)],
        "warnings": warnings,
        "canonical_snapshot": snapshot.model_dump(mode="json"),
    }
