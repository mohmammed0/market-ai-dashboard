from __future__ import annotations

from collections import defaultdict

from backend.app.adapters.broker.alpaca import reconcile as reconcile_alpaca
from backend.app.application.execution.service import get_internal_portfolio, sync_internal_positions_from_broker


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _signed_quantity(quantity: float, side: str | None) -> float:
    normalized_side = str(side or "").strip().upper()
    if normalized_side == "SHORT":
        return -abs(quantity)
    return abs(quantity)


def _summarize_positions(rows: list[dict] | None) -> dict[str, dict]:
    summary: dict[str, dict] = defaultdict(
        lambda: {
            "symbol": None,
            "quantity": 0.0,
            "market_value": 0.0,
            "legs": [],
        }
    )
    for row in rows or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        quantity = abs(_safe_float(row.get("qty", row.get("quantity"))))
        side = str(row.get("side") or "").strip().upper() or "LONG"
        aggregate = summary[symbol]
        aggregate["symbol"] = symbol
        aggregate["quantity"] += _signed_quantity(quantity, side)
        aggregate["market_value"] += _safe_float(row.get("market_value"))
        aggregate["legs"].append(row)

    for symbol, item in summary.items():
        net_quantity = _safe_float(item.get("quantity"))
        item["side"] = "SHORT" if net_quantity < 0 else "LONG" if net_quantity > 0 else "FLAT"
        item["net_quantity"] = round(net_quantity, 6)
        item["abs_quantity"] = round(abs(net_quantity), 6)
        item["market_value"] = round(_safe_float(item.get("market_value")), 4)
        item["symbol"] = symbol
    return dict(summary)


def reconcile_execution_state(*, broker: str = "alpaca") -> dict:
    if str(broker or "").strip().lower() == "alpaca":
        return reconcile_alpaca()
    return {"broker": broker, "detail": "No reconciliation adapter configured.", "orders": [], "positions": []}


def get_execution_reconciliation(
    *,
    broker: str = "alpaca",
    strategy_mode: str = "classic",
    apply_sync: bool = False,
) -> dict:
    normalized_broker = str(broker or "alpaca").strip().lower() or "alpaca"
    normalized_strategy_mode = str(strategy_mode or "classic").strip().lower() or "classic"

    sync_result = None
    if apply_sync:
        sync_result = sync_internal_positions_from_broker(strategy_mode=normalized_strategy_mode)

    broker_state = reconcile_execution_state(broker=normalized_broker)
    internal_state = get_internal_portfolio(limit=500)

    broker_items = list((broker_state.get("positions") or {}).get("items") or [])
    internal_items = [
        row
        for row in list(internal_state.get("positions") or [])
        if str(row.get("strategy_mode") or normalized_strategy_mode).strip().lower() == normalized_strategy_mode
    ]

    broker_by_symbol = _summarize_positions(broker_items)
    internal_by_symbol = _summarize_positions(internal_items)

    matched = 0
    mismatched = 0
    broker_only = 0
    internal_only = 0
    side_mismatches = 0
    quantity_mismatches = 0
    rows: list[dict] = []

    for symbol in sorted(set(broker_by_symbol) | set(internal_by_symbol)):
        broker_row = broker_by_symbol.get(symbol)
        internal_row = internal_by_symbol.get(symbol)
        broker_qty = _safe_float((broker_row or {}).get("net_quantity"))
        internal_qty = _safe_float((internal_row or {}).get("net_quantity"))
        qty_delta = round(broker_qty - internal_qty, 6)
        abs_delta = abs(qty_delta)
        broker_side = (broker_row or {}).get("side", "FLAT")
        internal_side = (internal_row or {}).get("side", "FLAT")

        if broker_row and internal_row:
            if broker_side != internal_side and abs_delta > 1e-6:
                status = "side_mismatch"
                mismatched += 1
                side_mismatches += 1
            elif abs_delta > 1e-6:
                status = "quantity_mismatch"
                mismatched += 1
                quantity_mismatches += 1
            else:
                status = "matched"
                matched += 1
        elif broker_row:
            status = "broker_only"
            mismatched += 1
            broker_only += 1
        else:
            status = "internal_only"
            mismatched += 1
            internal_only += 1

        rows.append(
            {
                "symbol": symbol,
                "status": status,
                "broker_side": broker_side,
                "internal_side": internal_side,
                "broker_quantity": round(broker_qty, 6),
                "internal_quantity": round(internal_qty, 6),
                "quantity_delta": qty_delta,
                "broker_market_value": round(_safe_float((broker_row or {}).get("market_value")), 4),
                "internal_market_value": round(_safe_float((internal_row or {}).get("market_value")), 4),
                "broker_legs": len((broker_row or {}).get("legs") or []),
                "internal_legs": len((internal_row or {}).get("legs") or []),
            }
        )

    return {
        "broker": normalized_broker,
        "strategy_mode": normalized_strategy_mode,
        "applied_sync": bool(apply_sync),
        "sync_result": sync_result,
        "summary": {
            "broker_positions": len(broker_by_symbol),
            "internal_positions": len(internal_by_symbol),
            "matched": matched,
            "mismatched": mismatched,
            "broker_only": broker_only,
            "internal_only": internal_only,
            "side_mismatches": side_mismatches,
            "quantity_mismatches": quantity_mismatches,
        },
        "broker_status": {
            "connected": broker_state.get("connected"),
            "detail": broker_state.get("detail"),
            "mode": broker_state.get("mode"),
            "order_submission_enabled": broker_state.get("order_submission_enabled"),
            "live_execution_enabled": broker_state.get("live_execution_enabled"),
        },
        "account": broker_state.get("account"),
        "positions": rows,
        "orders": list((broker_state.get("orders") or {}).get("items") or []),
        "internal_portfolio": internal_state.get("summary", {}),
    }


__all__ = ["get_execution_reconciliation", "reconcile_execution_state"]
