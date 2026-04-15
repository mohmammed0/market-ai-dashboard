"""Trailing Stop Monitor — periodic job that checks positions and closes if stops hit.

Runs every 5 minutes via the scheduler during market hours.
"""
from __future__ import annotations

import logging
from datetime import datetime

from backend.app.core.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def run_trailing_stop_check() -> dict:
    """Check all open positions for trailing stop triggers.

    Steps:
    1. Load all OPEN positions from paper_positions
    2. Fetch current quotes
    3. Evaluate trailing stops
    4. Close triggered positions
    5. Update high water marks for non-triggered positions
    6. Send Telegram notifications
    """
    from backend.app.repositories.execution import ExecutionRepository
    from backend.app.services.storage import session_scope
    from backend.app.services.market_data import fetch_quote_snapshots
    from backend.app.services.risk_engine import compute_trailing_stop, DEFAULT_TRAILING_STOP_PCT

    results = {
        "checked": 0,
        "triggered": 0,
        "updated": 0,
        "errors": 0,
        "closed_positions": [],
    }

    with session_scope() as session:
        repo = ExecutionRepository(session)
        positions = repo.list_open_positions()

        if not positions:
            return {**results, "status": "no_positions"}

        # Get symbols for quote lookup
        symbols = list(set(pos.symbol for pos in positions))
        snapshot = fetch_quote_snapshots(symbols, include_profile=False)
        quotes = {}
        for item in snapshot.get("items", []):
            sym = str(item.get("symbol", "")).upper()
            price = item.get("price")
            if sym and price:
                quotes[sym] = float(price)

        for pos in positions:
            results["checked"] += 1
            symbol = pos.symbol
            current_price = quotes.get(symbol)

            if not current_price or current_price <= 0:
                continue

            trailing_pct = getattr(pos, "trailing_stop_pct", None) or DEFAULT_TRAILING_STOP_PCT
            hwm = getattr(pos, "high_water_mark", None)
            existing_stop = getattr(pos, "trailing_stop_price", None)

            stop_result = compute_trailing_stop(
                side=pos.side,
                current_price=current_price,
                high_water_mark=hwm,
                trailing_stop_pct=trailing_pct,
                existing_trailing_stop=existing_stop,
            )

            if stop_result["triggered"]:
                # Close this position
                results["triggered"] += 1
                try:
                    _close_triggered_position(repo, pos, current_price, stop_result)
                    results["closed_positions"].append({
                        "symbol": symbol,
                        "side": pos.side,
                        "price": current_price,
                        "stop": stop_result["trailing_stop_price"],
                    })
                except Exception as exc:
                    results["errors"] += 1
                    logger.warning("trailing_stop close failed for %s: %s", symbol, exc)
            else:
                # Update high water mark and trailing stop price
                try:
                    pos.high_water_mark = stop_result["high_water_mark"]
                    pos.trailing_stop_price = stop_result["trailing_stop_price"]
                    pos.trailing_stop_pct = trailing_pct
                    pos.current_price = current_price
                    pos.market_value = round(current_price * float(pos.quantity or 0), 4)
                    sign = 1 if pos.side == "LONG" else -1
                    pos.unrealized_pnl = round(
                        (current_price - float(pos.avg_entry_price or 0)) * float(pos.quantity or 0) * sign, 4
                    )
                    pos.updated_at = datetime.utcnow()
                    results["updated"] += 1
                except Exception as exc:
                    results["errors"] += 1

    results["status"] = "completed"
    log_event(logger, logging.INFO, "trailing_stop.check.done",
              checked=results["checked"], triggered=results["triggered"], updated=results["updated"])
    return results


def _close_triggered_position(repo, pos, current_price: float, stop_result: dict):
    """Close a position that hit its trailing stop."""
    from backend.app.domain.execution.contracts import TradeRecord, ExecutionEventRecord
    from backend.app.services.paper_fill_engine import compute_fill

    fill_side = "SELL" if pos.side == "LONG" else "BUY"
    fill = compute_fill(side=fill_side, quantity=float(pos.quantity or 0), reference_price=current_price, order_type="market")

    sign = 1 if pos.side == "LONG" else -1
    gross_pnl = round((fill.fill_price - float(pos.avg_entry_price or 0)) * fill.filled_quantity * sign, 4)
    realized = round(gross_pnl - fill.fee_amount, 4)

    repo.close_position(pos, current_price=fill.fill_price, realized_pnl=realized)
    repo.append_trade(TradeRecord(
        symbol=pos.symbol, strategy_mode=pos.strategy_mode,
        action="CLOSE", side=pos.side, quantity=fill.filled_quantity,
        price=fill.fill_price, realized_pnl=realized,
        notes=f"Trailing stop triggered | {fill.to_notes_str()}",
    ))
    repo.append_audit_event(ExecutionEventRecord(
        event_type="trailing_stop_triggered",
        symbol=pos.symbol, strategy_mode=pos.strategy_mode,
        payload={
            "trigger_price": current_price,
            "stop_price": stop_result["trailing_stop_price"],
            "high_water_mark": stop_result["high_water_mark"],
            "trailing_pct": stop_result["trailing_stop_pct"],
            "realized_pnl": realized,
            "fill": fill.to_audit_dict(),
        },
    ))

    # Submit to broker
    try:
        from backend.app.application.execution.service import _submit_to_broker
        _submit_to_broker(pos.symbol, fill.filled_quantity, fill_side)
    except Exception:
        pass

    # Send Telegram notification
    try:
        from backend.app.services.trade_notifier import notify_trailing_stop
        notify_trailing_stop(
            symbol=pos.symbol, side=pos.side,
            trigger_price=current_price,
            entry_price=float(pos.avg_entry_price or 0),
            pnl=realized,
        )
    except Exception:
        pass
