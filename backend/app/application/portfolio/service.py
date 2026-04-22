from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import pandas as pd

from backend.app.application.broker.service import get_broker_summary
from backend.app.application.execution.service import (
    get_internal_portfolio,
    get_trade_history,
    list_paper_orders,
)
from backend.app.domain.portfolio.contracts import (
    PortfolioPosition,
    PortfolioSnapshot,
    PortfolioSnapshotV1,
    PortfolioSourceSummary,
    PortfolioViewOrder,
    PortfolioViewPosition,
    PortfolioViewSummary,
    PortfolioViewTrade,
)
from backend.app.services.market_data import load_history
from backend.app.services.market_profiles import load_symbol_profiles

_BROKER_TERMINAL_ORDER_STATUSES = {
    "filled",
    "canceled",
    "cancelled",
    "expired",
    "rejected",
    "replaced",
    "suspended",
}

_PORTFOLIO_SOURCE_LABELS = {
    "broker_live": ("broker", "Broker Live"),
}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default if default is None else float(default)
        return float(value)
    except Exception:
        return default if default is None else float(default)


def _normalize_text(value, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _normalize_enum_text(value, default: str = "") -> str:
    text = _normalize_text(value, default)
    if not text:
        return default
    parts = text.split(".")
    return parts[-1] or default


def _parse_datetime(value) -> datetime | None:
    text = _normalize_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _normalize_internal_position(item: dict) -> PortfolioViewPosition:
    return PortfolioViewPosition(
        portfolio_source="broker_live",
        symbol=_normalize_text(item.get("symbol"), "-"),
        side=_normalize_text(item.get("side")).upper(),
        quantity=_safe_float(item.get("quantity")),
        qty=_safe_float(item.get("quantity")),
        avg_entry_price=_safe_float(item.get("avg_entry_price"), None),
        current_price=_safe_float(item.get("current_price"), None),
        market_value=_safe_float(item.get("market_value")),
        cost_basis=round(_safe_float(item.get("avg_entry_price")) * _safe_float(item.get("quantity")), 4),
        unrealized_pnl=_safe_float(item.get("unrealized_pnl")),
        realized_pnl=_safe_float(item.get("realized_pnl")),
        stop_loss_price=_safe_float(item.get("stop_loss_price"), None),
        trailing_stop_pct=_safe_float(item.get("trailing_stop_pct"), None),
        trailing_stop_price=_safe_float(item.get("trailing_stop_price"), None),
        high_water_mark=_safe_float(item.get("high_water_mark"), None),
        strategy_mode=_normalize_text(item.get("strategy_mode")) or None,
        updated_at=_parse_datetime(item.get("updated_at")),
    )


def _normalize_broker_position(item: dict, broker_source: str) -> PortfolioViewPosition:
    return PortfolioViewPosition(
        portfolio_source=broker_source,
        symbol=_normalize_text(item.get("symbol"), "-"),
        side=_normalize_enum_text(item.get("side")).upper(),
        quantity=_safe_float(item.get("qty")),
        qty=_safe_float(item.get("qty")),
        avg_entry_price=_safe_float(item.get("avg_entry_price"), None),
        current_price=_safe_float(item.get("current_price"), None),
        market_value=_safe_float(item.get("market_value")),
        cost_basis=_safe_float(item.get("cost_basis")),
        unrealized_pnl=_safe_float(item.get("unrealized_pnl")),
        realized_pnl=0.0,
        unrealized_pnl_pct=_safe_float(item.get("unrealized_pnl_pct"), None),
        change_today_pct=_safe_float(item.get("change_today_pct"), None),
        strategy_mode="broker",
    )


def _normalize_internal_order(item: dict) -> PortfolioViewOrder:
    quantity = _safe_float(item.get("quantity"))
    order_type = _normalize_text(item.get("order_type"), "MARKET").upper()
    return PortfolioViewOrder(
        id=item.get("id"),
        client_order_id=_normalize_text(item.get("client_order_id")) or None,
        portfolio_source="broker_live",
        symbol=_normalize_text(item.get("symbol"), "-"),
        side=_normalize_text(item.get("side")).upper(),
        order_type=order_type,
        type=order_type,
        status=_normalize_text(item.get("status"), "UNKNOWN").upper(),
        quantity=quantity,
        qty=quantity,
        filled_qty=_safe_float(item.get("filled_quantity")),
        filled_avg_price=_safe_float(item.get("fill_price"), None),
        limit_price=_safe_float(item.get("limit_price"), None),
        submitted_at=_normalize_text(item.get("created_at")) or None,
        updated_at=_normalize_text(item.get("updated_at")) or None,
        notes=_normalize_text(item.get("notes")) or None,
    )


def _normalize_broker_order(item: dict, broker_source: str) -> PortfolioViewOrder:
    raw_status = _normalize_enum_text(item.get("status")).lower()
    order_type = _normalize_enum_text(item.get("type") or item.get("order_type"), "MARKET").upper()
    quantity = _safe_float(item.get("qty"))
    return PortfolioViewOrder(
        id=item.get("id"),
        client_order_id=_normalize_text(item.get("client_order_id")) or None,
        portfolio_source=broker_source,
        symbol=_normalize_text(item.get("symbol"), "-"),
        side=_normalize_enum_text(item.get("side")).upper(),
        order_type=order_type,
        type=order_type,
        status=raw_status.upper() if raw_status else "UNKNOWN",
        quantity=quantity,
        qty=quantity,
        filled_qty=_safe_float(item.get("filled_qty")),
        filled_avg_price=_safe_float(item.get("filled_avg_price"), None),
        submitted_at=_normalize_text(item.get("submitted_at")) or None,
        updated_at=_normalize_text(item.get("updated_at")) or None,
        raw_status=raw_status or None,
    )


def _is_open_broker_order(order: PortfolioViewOrder) -> bool:
    raw_status = _normalize_text(order.raw_status).lower()
    if not raw_status:
        return False
    return raw_status not in _BROKER_TERMINAL_ORDER_STATUSES


def _normalize_internal_trade(item: dict) -> PortfolioViewTrade:
    return PortfolioViewTrade(
        id=item.get("id"),
        portfolio_source="broker_live",
        symbol=_normalize_text(item.get("symbol"), "-"),
        side=_normalize_text(item.get("side")).upper(),
        quantity=_safe_float(item.get("quantity")),
        price=_safe_float(item.get("price")),
        realized_pnl=_safe_float(item.get("realized_pnl")),
        status=_normalize_text(item.get("status")) or None,
        created_at=_normalize_text(item.get("created_at")) or None,
        notes=_normalize_text(item.get("notes")) or None,
    )


def _normalize_broker_trade(order: PortfolioViewOrder) -> PortfolioViewTrade | None:
    if order.filled_qty <= 0 and order.raw_status not in {"filled", "partially_filled"}:
        return None
    return PortfolioViewTrade(
        id=order.id,
        portfolio_source=order.portfolio_source,
        symbol=order.symbol,
        side=order.side,
        quantity=order.filled_qty or order.quantity,
        price=_safe_float(order.filled_avg_price),
        realized_pnl=0.0,
        status=order.status,
        created_at=order.updated_at or order.submitted_at,
    )


def _with_profile_metadata(positions: list[PortfolioViewPosition]) -> list[PortfolioViewPosition]:
    if not positions:
        return positions
    profiles = load_symbol_profiles([item.symbol for item in positions if item.symbol and item.symbol != "-"])
    total_market_value = sum(abs(item.market_value) for item in positions)
    for item in positions:
        profile = profiles.get(item.symbol, {})
        item.sector = profile.get("sector", "Unknown")
        item.industry = profile.get("industry", "Unknown")
        item.market_cap_bucket = profile.get("market_cap_bucket", "Unknown")
        item.weight_pct = round((abs(item.market_value) / total_market_value) * 100.0, 2) if total_market_value else 0.0
    return positions


def _has_meaningful_snapshot_activity(
    summary: PortfolioViewSummary,
    positions: list[PortfolioViewPosition],
    open_orders: list[PortfolioViewOrder],
    trades: list[PortfolioViewTrade],
) -> bool:
    return any(
        (
            bool(positions),
            bool(open_orders),
            bool(trades),
            int(summary.open_positions or 0) > 0,
            int(summary.open_orders or 0) > 0,
            int(summary.total_trades or 0) > 0,
            abs(float(summary.total_market_value or 0.0)) > 0.0001,
            abs(float(summary.invested_cost or 0.0)) > 0.0001,
            abs(float(summary.total_unrealized_pnl or 0.0)) > 0.0001,
            abs(float(summary.total_realized_pnl or 0.0)) > 0.0001,
        )
    )


def _has_active_snapshot_book_state(
    summary: PortfolioViewSummary,
    positions: list[PortfolioViewPosition],
    open_orders: list[PortfolioViewOrder],
) -> bool:
    return any(
        (
            bool(positions),
            bool(open_orders),
            int(summary.open_positions or 0) > 0,
            int(summary.open_orders or 0) > 0,
            abs(float(summary.total_market_value or 0.0)) > 0.0001,
            abs(float(summary.invested_cost or 0.0)) > 0.0001,
            abs(float(summary.total_unrealized_pnl or 0.0)) > 0.0001,
        )
    )


def _build_internal_snapshot_view(internal: dict) -> tuple[
    list[PortfolioViewPosition],
    list[PortfolioViewOrder],
    list[PortfolioViewOrder],
    list[PortfolioViewTrade],
    PortfolioViewSummary,
]:
    positions = _with_profile_metadata(
        [_normalize_internal_position(item) for item in internal.get("items", [])]
    )
    all_orders_payload = list_paper_orders(limit=200, status=None)
    open_orders_payload = list_paper_orders(limit=200, status="OPEN")
    trades_payload = get_trade_history(limit=200)
    orders = [_normalize_internal_order(item) for item in all_orders_payload.get("items", [])]
    open_orders = [_normalize_internal_order(item) for item in open_orders_payload.get("items", [])]
    trades = [_normalize_internal_trade(item) for item in trades_payload.get("items", [])]
    internal_summary = internal.get("summary", {})
    win_rate_value = internal_summary.get("win_rate_pct")
    summary = PortfolioViewSummary(
        active_source="broker_live",
        provider="broker",
        connected=False,
        mode="live",
        open_positions=int(internal_summary.get("open_positions") or 0),
        open_orders=len(open_orders),
        total_market_value=round(_safe_float(internal_summary.get("total_market_value")), 4),
        invested_cost=round(_safe_float(internal_summary.get("invested_cost")), 4),
        cash_balance=round(_safe_float(internal_summary.get("cash_balance")), 4),
        total_equity=round(_safe_float(internal_summary.get("total_equity")), 4),
        portfolio_value=round(_safe_float(internal_summary.get("portfolio_value")), 4),
        total_unrealized_pnl=round(_safe_float(internal_summary.get("total_unrealized_pnl")), 4),
        total_realized_pnl=round(_safe_float(internal_summary.get("total_realized_pnl")), 4),
        total_trades=int(internal_summary.get("total_trades") or 0),
        starting_cash=round(_safe_float(internal_summary.get("starting_cash")), 4),
        win_rate_pct=None if win_rate_value in {None, "", "-"} else _safe_float(win_rate_value),
    )
    return positions, orders, open_orders, trades, summary


def _build_broker_snapshot_view(
    broker: dict,
    broker_source: str,
) -> tuple[
    list[PortfolioViewPosition],
    list[PortfolioViewOrder],
    list[PortfolioViewOrder],
    list[PortfolioViewTrade],
    PortfolioViewSummary,
]:
    positions = _with_profile_metadata(
        [_normalize_broker_position(item, broker_source) for item in broker.get("positions", [])]
    )
    orders = [_normalize_broker_order(item, broker_source) for item in broker.get("orders", [])]
    open_orders = [order for order in orders if _is_open_broker_order(order)]
    trades = [
        trade
        for trade in (_normalize_broker_trade(order) for order in orders)
        if trade is not None
    ]
    total_market_value = round(sum(item.market_value for item in positions), 4)
    invested_cost = round(sum(item.cost_basis for item in positions), 4)
    cash_balance = round(_safe_float((broker.get("account") or {}).get("cash")), 4)
    total_equity = round(
        _safe_float((broker.get("account") or {}).get("equity") or (broker.get("account") or {}).get("portfolio_value")),
        4,
    )
    portfolio_value = total_equity or round(_safe_float((broker.get("account") or {}).get("portfolio_value")), 4)
    summary = PortfolioViewSummary(
        active_source=broker_source,
        provider=_normalize_text(broker.get("provider"), "alpaca"),
        connected=True,
        mode=_normalize_text(broker.get("mode"), "live"),
        open_positions=len(positions),
        open_orders=len(open_orders),
        total_market_value=round(total_market_value, 4),
        invested_cost=round(invested_cost, 4),
        cash_balance=round(cash_balance, 4),
        total_equity=round(total_equity, 4),
        portfolio_value=round(portfolio_value or (cash_balance + total_market_value), 4),
        total_unrealized_pnl=round(sum(item.unrealized_pnl for item in positions), 4),
        total_realized_pnl=0.0,
        total_trades=len(trades),
        starting_cash=round(total_equity or cash_balance, 4),
        win_rate_pct=None,
    )
    return positions, orders, open_orders, trades, summary


def _build_canonical_positions(internal: dict, broker: dict) -> list[PortfolioPosition]:
    raw_positions: list[PortfolioPosition] = []
    broker_source = "broker_live"
    for item in broker.get("positions", []):
        raw_positions.append(
            PortfolioPosition(
                portfolio_source=broker_source,
                symbol=item.get("symbol") or "",
                side=item.get("side") or "",
                quantity=_safe_float(item.get("qty")),
                current_price=_safe_float(item.get("current_price")),
                market_value=_safe_float(item.get("market_value")),
                unrealized_pnl=_safe_float(item.get("unrealized_pnl")),
                realized_pnl=0.0,
                strategy_mode="broker",
            )
        )
    return raw_positions


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


def build_canonical_portfolio_snapshot(
    internal: dict | None = None,
    broker: dict | None = None,
) -> PortfolioSnapshot:
    internal = internal or {}
    broker = broker or get_broker_summary()
    raw_positions = _build_canonical_positions(internal, broker)

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
        sources=[
            PortfolioSourceSummary(
                source=source,
                positions=values["positions"],
                market_value=round(values["market_value"], 2),
                unrealized_pnl=round(values["unrealized_pnl"], 2),
            )
            for source, values in by_source.items()
        ],
        total_market_value=round(total_market_value, 2),
        total_unrealized_pnl=round(sum(item.unrealized_pnl for item in raw_positions), 2),
    )


def build_portfolio_snapshot_payload() -> PortfolioSnapshotV1:
    broker = get_broker_summary()
    canonical_snapshot = build_canonical_portfolio_snapshot(internal={}, broker=broker)
    broker_connected = bool(broker.get("connected"))
    broker_source = "broker_live"

    if broker_connected:
        positions, orders, open_orders, trades, summary = _build_broker_snapshot_view(broker, broker_source)
    else:
        positions = []
        orders = []
        open_orders = []
        trades = []
        summary = PortfolioViewSummary(
            active_source=broker_source,
            provider=_normalize_text(broker.get("provider"), "none"),
            connected=False,
            mode=_normalize_text(broker.get("mode"), "disabled"),
            open_positions=0,
            open_orders=0,
            total_market_value=0.0,
            invested_cost=0.0,
            cash_balance=0.0,
            total_equity=0.0,
            portfolio_value=0.0,
            total_unrealized_pnl=0.0,
            total_realized_pnl=0.0,
            total_trades=0,
            starting_cash=0.0,
            win_rate_pct=None,
        )

    source_type, source_label = _PORTFOLIO_SOURCE_LABELS.get(summary.active_source, ("broker", "Broker Managed"))
    broker_environment = "external_live"

    return PortfolioSnapshotV1(
        generated_at=datetime.utcnow(),
        active_source=summary.active_source,
        source_type=source_type,
        source_label=source_label,
        broker_connected=broker_connected,
        summary=summary,
        positions=positions,
        items=positions,
        orders=orders,
        open_orders=open_orders,
        trades=trades,
        broker_status={
            "provider": broker.get("provider", "none"),
            "enabled": bool(broker.get("enabled", False)),
            "configured": bool(broker.get("configured", False)),
            "sdk_installed": bool(broker.get("sdk_installed", False)),
            "connected": broker_connected,
            "mode": broker.get("mode", "disabled"),
            "paper": False,
            "live_execution_enabled": bool(broker.get("live_execution_enabled", False)),
            "order_submission_enabled": bool(broker.get("order_submission_enabled", False)),
            "detail": broker.get("detail", ""),
            "broker_execution_mode": "broker_managed",
            "broker_environment": broker_environment,
            "internal_paper_enabled": False,
            "account_source": "broker",
            "position_source": "broker",
            "order_source": "broker",
            "execution_source": "broker",
        },
        broker_account=broker.get("account"),
        source_summaries=canonical_snapshot.sources,
        canonical_snapshot=canonical_snapshot,
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
        by_symbol.append(
            {
                "symbol": item["symbol"],
                "portfolio_source": item["portfolio_source"],
                "sector": item.get("sector", "Unknown"),
                "market_cap_bucket": item.get("market_cap_bucket", "Unknown"),
                "market_value": round(market_value, 2),
                "weight_pct": round(weight * 100.0, 2),
                "side": item["side"],
                "strategy_mode": item.get("strategy_mode"),
            }
        )
        by_sector[item.get("sector", "Unknown")]["market_value"] += market_value
        by_sector[item.get("sector", "Unknown")]["symbols"] += 1
        by_bucket[item.get("market_cap_bucket", "Unknown")]["market_value"] += market_value
        by_bucket[item.get("market_cap_bucket", "Unknown")]["symbols"] += 1
        weights[item["symbol"]] = weight

    warnings = []
    for row in by_symbol:
        if row["weight_pct"] >= 25:
            warnings.append(
                f"{row['symbol']} represents {row['weight_pct']}% of the portfolio and exceeds the concentration threshold."
            )
    warnings.extend(_correlation_warnings([item["symbol"] for item in items], weights))
    if any(item["portfolio_source"] == "broker_live" for item in items):
        warnings.append(
            "Live broker holdings are present in the canonical portfolio. Live execution remains disabled, but reconciliation should be reviewed before enabling any order workflow."
        )

    return {
        "summary": {
            "open_positions": len(items),
            "total_market_value": round(total_market_value, 2),
            "largest_position_pct": round(max([row["weight_pct"] for row in by_symbol], default=0.0), 2),
            "sources": [source.model_dump(mode="json") for source in snapshot.sources],
        },
        "positions": items,
        "by_symbol": sorted(by_symbol, key=lambda item: item["weight_pct"], reverse=True),
        "by_sector": [
            {
                "sector": sector,
                "market_value": round(values["market_value"], 2),
                "symbols": values["symbols"],
                "weight_pct": round((values["market_value"] / total_market_value) * 100.0, 2)
                if total_market_value
                else 0.0,
            }
            for sector, values in sorted(by_sector.items(), key=lambda item: item[1]["market_value"], reverse=True)
        ],
        "by_market_cap_bucket": [
            {
                "bucket": bucket,
                "market_value": round(values["market_value"], 2),
                "symbols": values["symbols"],
                "weight_pct": round((values["market_value"] / total_market_value) * 100.0, 2)
                if total_market_value
                else 0.0,
            }
            for bucket, values in sorted(by_bucket.items(), key=lambda item: item[1]["market_value"], reverse=True)
        ],
        "warnings": warnings,
        "canonical_snapshot": snapshot.model_dump(mode="json"),
    }
