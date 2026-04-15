from __future__ import annotations

import threading
import time
from uuid import uuid4
import logging

from backend.app.application.broker.service import get_broker_summary
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.domain.alerts.contracts import AlertRecord
from backend.app.domain.execution.contracts import (
    ExecutionCommand,
    ExecutionEventRecord,
    PaperOrderRecord,
    PositionState,
    SignalRecord,
    SignalSnapshot,
    TradeIntent,
    TradeRecord,
)
from backend.app.domain.platform.contracts import ExecutionConfirmResult, ExecutionPreview
from backend.app.repositories.execution import ExecutionRepository
from backend.app.services.execution_halt import is_halted, get_halt_status
from backend.app.services.market_data import fetch_quote_snapshots
from backend.app.services.paper_fill_engine import compute_fill
from backend.app.services.risk_engine import check_execution_risk
from backend.app.services.signal_runtime import build_smart_analysis, extract_signal_view
from backend.app.services.storage import session_scope

# Broker integration for live order submission
def _submit_to_broker(symbol: str, qty: float, side: str, order_type: str = "market", estimated_price: float | None = None) -> dict | None:
    """Submit order to broker (Alpaca) if configured and enabled."""
    try:
        from backend.app.services.runtime_settings import get_auto_trading_config
        config = get_auto_trading_config()
        if not config.get("ready", False):
            return None

        from backend.app.services.broker.registry import get_broker_provider
        broker = get_broker_provider()
        result = broker.submit_order(
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            estimated_price=estimated_price,
        )

        if result.get("ok"):
            # Send Telegram notification
            _notify_trade(symbol, qty, side, result.get("order", {}))

        return result
    except Exception as exc:
        log_event(logger, logging.WARNING, "execution.broker_submit.failed",
                  symbol=symbol, side=side, qty=qty, error=str(exc))
        return {"ok": False, "error": str(exc)}


def _notify_trade(symbol: str, qty: float, side: str, order: dict):
    """Send Telegram notification for executed trade."""
    try:
        from core.telegram_notifier import send_telegram_message, is_telegram_configured
        if not is_telegram_configured():
            return
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        mode = order.get("mode", "paper")
        msg = (
            f"{emoji} <b>تنفيذ {side.upper()}</b>\n"
            f"📊 السهم: <b>{symbol}</b>\n"
            f"📦 الكمية: {qty}\n"
            f"💰 الوضع: {mode}\n"
            f"🆔 Order: {order.get('id', 'N/A')}"
        )
        send_telegram_message(msg)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# In-memory preview store (TTL = 5 minutes)
# ---------------------------------------------------------------------------
_PREVIEW_TTL_SECONDS: int = 300
_preview_store: dict[str, dict] = {}  # preview_id -> {preview, params, expires_at}
_preview_lock = threading.Lock()

logger = get_logger(__name__)


class ExecutionHaltedError(RuntimeError):
    """Raised when an execution attempt is blocked by the kill switch."""
    status_code = 503


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _build_quote_lookup(symbols) -> dict[str, dict]:
    normalized_symbols = [
        str(symbol or "").strip().upper()
        for symbol in (symbols or [])
        if str(symbol or "").strip()
    ]
    if not normalized_symbols:
        return {}
    snapshot = fetch_quote_snapshots(normalized_symbols)
    return {
        str(item.get("symbol") or "").strip().upper(): item
        for item in snapshot.get("items", [])
        if item.get("symbol")
    }


def _latest_price(symbol: str, fallback_price=None, quote_lookup: dict[str, dict] | None = None):
    normalized_symbol = str(symbol or "").strip().upper()
    if quote_lookup is not None:
        quote_payload = quote_lookup.get(normalized_symbol)
        if quote_payload is not None:
            return _safe_float(quote_payload.get("price"), fallback_price), quote_payload
        return _safe_float(fallback_price, 0.0), None
    snapshot = fetch_quote_snapshots([normalized_symbol])
    items = snapshot.get("items", [])
    if items:
        return _safe_float(items[0].get("price"), fallback_price), items[0]
    return _safe_float(fallback_price, 0.0), None


def _build_signal_snapshot(symbol: str, strategy_mode: str, result: dict, start_date: str, end_date: str, quote_lookup: dict[str, dict] | None = None) -> SignalSnapshot:
    signal_view = extract_signal_view({**result, "start_date": start_date, "end_date": end_date}, mode=strategy_mode)
    latest_price, quote_payload = _latest_price(symbol, signal_view.get("price"), quote_lookup=quote_lookup)
    return SignalSnapshot(
        symbol=symbol,
        strategy_mode=strategy_mode,
        signal=str(signal_view.get("signal", "HOLD")).upper(),
        confidence=_safe_float(signal_view.get("confidence"), 0.0),
        price=latest_price,
        reasoning=str(signal_view.get("reasoning") or ""),
        analysis_payload={"analysis": result, "quote": quote_payload, "signal_view": signal_view},
    )


def _build_trade_intents(current_position: PositionState | None, signal_snapshot: SignalSnapshot, quantity: float) -> list[TradeIntent]:
    quantity = max(_safe_float(quantity, 1.0), 1.0)
    signal = signal_snapshot.signal
    price = signal_snapshot.price
    symbol = signal_snapshot.symbol
    strategy_mode = signal_snapshot.strategy_mode
    intents: list[TradeIntent] = []

    if signal == "BUY":
        if current_position and current_position.side == "SHORT":
            intents.append(TradeIntent(intent="CLOSE_SHORT", symbol=symbol, strategy_mode=strategy_mode, side="SHORT", quantity=current_position.quantity, execution_price=price, reason="Signal BUY closed short"))
        if not current_position or current_position.side != "LONG":
            intents.append(TradeIntent(intent="OPEN_LONG", symbol=symbol, strategy_mode=strategy_mode, side="LONG", quantity=quantity, execution_price=price, reason="Signal BUY opened long"))
    elif signal == "SELL":
        if current_position and current_position.side == "LONG":
            intents.append(TradeIntent(intent="CLOSE_LONG", symbol=symbol, strategy_mode=strategy_mode, side="LONG", quantity=current_position.quantity, execution_price=price, reason="Signal SELL closed long"))
        else:
            intents.append(TradeIntent(intent="NONE", symbol=symbol, strategy_mode=strategy_mode, quantity=0.0, execution_price=price, reason="Signal SELL ignored because no long position is open"))
    else:
        intents.append(TradeIntent(intent="NONE", symbol=symbol, strategy_mode=strategy_mode, quantity=0.0, execution_price=price, reason="Signal HOLD generated no execution intent"))
    return intents


def _get_internal_cash_balance() -> float:
    portfolio = get_internal_portfolio(limit=500)
    summary = portfolio.get("summary", {}) if isinstance(portfolio, dict) else {}
    return max(_safe_float(summary.get("cash_balance"), 0.0), 0.0)


def _validate_cash_only_order(
    *,
    side: str,
    symbol: str,
    quantity: float,
    estimated_price: float,
    fee_amount: float = 0.0,
    current_position: PositionState | None = None,
) -> tuple[bool, str | None]:
    normalized_side = str(side or "").strip().upper()
    quantity_f = max(_safe_float(quantity, 0.0), 0.0)
    price_f = max(_safe_float(estimated_price, 0.0), 0.0)
    fee_f = max(_safe_float(fee_amount, 0.0), 0.0)

    if normalized_side == "BUY":
        required_cash = round((quantity_f * price_f) + fee_f, 4)
        available_cash = round(_get_internal_cash_balance(), 4)
        if required_cash > available_cash:
            return False, (
                f"{symbol} buy requires ${required_cash:.2f} cash, but only ${available_cash:.2f} is available. "
                "Cash-only execution blocks margin usage."
            )
        return True, None

    if normalized_side == "SELL":
        held_quantity = _safe_float(current_position.quantity if current_position else 0.0, 0.0)
        if current_position is None or str(current_position.side).upper() != "LONG" or held_quantity <= 0:
            return False, f"{symbol} cannot be sold because no long shares are currently held. Short selling is disabled."
        if quantity_f - held_quantity > 1e-9:
            return False, (
                f"{symbol} sell quantity {quantity_f:.4f} exceeds held long quantity {held_quantity:.4f}. "
                "Cash-only execution blocks short selling."
            )
        return True, None

    return False, f"Unsupported order side: {normalized_side}"


def _record_signal_alerts(repo: ExecutionRepository, strategy_mode: str, signal_snapshot: SignalSnapshot, previous_signal: SignalRecord | None) -> None:
    if signal_snapshot.signal == "BUY" and (previous_signal is None or previous_signal.signal != "BUY"):
        repo.append_alert(AlertRecord(symbol=signal_snapshot.symbol, strategy_mode=strategy_mode, alert_type="new_buy_signal", severity="info", message=f"{signal_snapshot.symbol} generated a new BUY signal in {strategy_mode}", payload=signal_snapshot.model_dump()))
    if signal_snapshot.signal == "SELL" and (previous_signal is None or previous_signal.signal != "SELL"):
        repo.append_alert(AlertRecord(symbol=signal_snapshot.symbol, strategy_mode=strategy_mode, alert_type="new_sell_signal", severity="info", message=f"{signal_snapshot.symbol} generated a new SELL signal in {strategy_mode}", payload=signal_snapshot.model_dump()))
    if previous_signal is not None and abs(_safe_float(previous_signal.confidence) - signal_snapshot.confidence) >= 15:
        repo.append_alert(AlertRecord(symbol=signal_snapshot.symbol, strategy_mode=strategy_mode, alert_type="confidence_change", severity="warning", message=f"{signal_snapshot.symbol} confidence changed materially in {strategy_mode}", payload={"previous_confidence": previous_signal.confidence, "current_confidence": signal_snapshot.confidence}))


def _apply_trade_intent(
    repo: ExecutionRepository,
    current_row,
    intent: TradeIntent,
    correlation_id: str | None = None,
) -> None:
    """Apply a single trade intent, pre-checked by the risk gate.

    The risk gate is evaluated here so that every call site — including future
    callers — automatically gets the protection without needing to remember to
    call it externally.  CLOSE / NONE intents bypass the gate (closing a
    position is always safe).
    """
    if intent.intent == "NONE":
        repo.append_audit_event(ExecutionEventRecord(
            event_type="execution_intent_skipped",
            symbol=intent.symbol,
            strategy_mode=intent.strategy_mode,
            correlation_id=correlation_id,
            payload={"intent": intent.intent, "reason": intent.reason},
        ))
        return

    # --- pre-trade risk gate -------------------------------------------------
    risk = check_execution_risk(
        intent=intent.intent,
        symbol=intent.symbol,
        quantity=intent.quantity,
        price=intent.execution_price,
    )
    if not risk["allowed"]:
        repo.append_audit_event(ExecutionEventRecord(
            event_type="risk_gate_blocked",
            symbol=intent.symbol,
            strategy_mode=intent.strategy_mode,
            correlation_id=correlation_id,
            payload={
                "intent": intent.intent,
                "blocked_reason": risk["blocked_reason"],
                "warnings": risk.get("warnings", []),
                "price": intent.execution_price,
                "quantity": intent.quantity,
            },
        ))
        log_event(
            logger, logging.WARNING, "execution.risk_gate.blocked",
            symbol=intent.symbol, intent=intent.intent,
            reason=risk["blocked_reason"], correlation_id=correlation_id,
        )
        return
    # -------------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Paper fill simulation — slippage, spread, fee, partial fill
    # OPEN_LONG / CLOSE_SHORT are buy-side; OPEN_SHORT / CLOSE_LONG are sell-side.
    # ------------------------------------------------------------------
    fill_side = "BUY" if intent.intent in {"OPEN_LONG", "CLOSE_SHORT"} else "SELL"
    fill = compute_fill(
        side=fill_side,
        quantity=intent.quantity,
        reference_price=intent.execution_price,
        order_type="market",
    )
    fill_price = fill.fill_price
    fill_qty = fill.filled_quantity
    fill_notes = f"{intent.reason} | {fill.to_notes_str()}"
    fill_audit = fill.to_audit_dict()
    # ------------------------------------------------------------------

    cash_side = "BUY" if intent.intent in {"OPEN_LONG", "CLOSE_SHORT"} else "SELL"
    current_position = None if current_row is None else PositionState(
        id=current_row.id,
        symbol=current_row.symbol,
        strategy_mode=current_row.strategy_mode,
        side=current_row.side,
        quantity=current_row.quantity,
        avg_entry_price=current_row.avg_entry_price,
        current_price=current_row.current_price,
        market_value=current_row.market_value or 0.0,
        unrealized_pnl=current_row.unrealized_pnl or 0.0,
        realized_pnl=current_row.realized_pnl or 0.0,
        status=current_row.status,
        opened_at=current_row.opened_at,
        updated_at=current_row.updated_at,
    )
    cash_allowed, cash_block_reason = _validate_cash_only_order(
        side=cash_side,
        symbol=intent.symbol,
        quantity=fill_qty if fill_qty > 0 else intent.quantity,
        estimated_price=fill_price,
        fee_amount=fill.fee_amount,
        current_position=current_position,
    )
    if not cash_allowed:
        repo.append_audit_event(ExecutionEventRecord(
            event_type="cash_only_blocked",
            symbol=intent.symbol,
            strategy_mode=intent.strategy_mode,
            correlation_id=correlation_id,
            payload={
                "intent": intent.intent,
                "side": cash_side,
                "price": fill_price,
                "quantity": fill_qty if fill_qty > 0 else intent.quantity,
                "reason": cash_block_reason,
            },
        ))
        log_event(
            logger,
            logging.WARNING,
            "execution.cash_only.blocked",
            symbol=intent.symbol,
            intent=intent.intent,
            side=cash_side,
            reason=cash_block_reason,
            correlation_id=correlation_id,
        )
        return

    if intent.intent in {"CLOSE_LONG", "CLOSE_SHORT"} and current_row is not None:
        close_qty = fill_qty if fill_qty > 0 else float(current_row.quantity or 0.0)
        sign = 1 if current_row.side == "LONG" else -1
        gross_pnl = round((fill_price - float(current_row.avg_entry_price or 0.0)) * close_qty * sign, 4)
        # Fees reduce realized P&L on close
        realized = round(gross_pnl - fill.fee_amount, 4)
        repo.close_position(current_row, current_price=fill_price, realized_pnl=realized)
        repo.append_trade(TradeRecord(
            symbol=intent.symbol, strategy_mode=intent.strategy_mode,
            action="CLOSE", side=current_row.side, quantity=close_qty,
            price=fill_price, realized_pnl=realized, notes=fill_notes,
        ))
        # Submit SELL to Alpaca broker
        broker_side = "SELL" if intent.intent == "CLOSE_LONG" else "BUY"
        broker_result = _submit_to_broker(intent.symbol, close_qty, broker_side, estimated_price=fill_price)
        broker_info = broker_result if broker_result else {"skipped": True}
        repo.append_audit_event(ExecutionEventRecord(
            event_type=intent.intent.lower(), symbol=intent.symbol,
            strategy_mode=intent.strategy_mode, correlation_id=correlation_id,
            payload={"price": fill_price, "quantity": close_qty, "realized_pnl": realized, "fill": fill_audit, "broker": broker_info},
        ))
    elif intent.intent == "OPEN_LONG":
        # Set trailing stop on new position
        from backend.app.services.risk_engine import DEFAULT_TRAILING_STOP_PCT
        trailing_pct = DEFAULT_TRAILING_STOP_PCT
        trailing_stop = round(fill_price * (1 - trailing_pct / 100.0), 4)
        repo.upsert_position(
            symbol=intent.symbol, strategy_mode=intent.strategy_mode,
            side="LONG", quantity=fill_qty, avg_entry_price=fill_price,
            current_price=fill_price, market_value=round(fill_price * fill_qty, 4),
            unrealized_pnl=0.0, realized_pnl=0.0, status="OPEN",
            trailing_stop_pct=trailing_pct, trailing_stop_price=trailing_stop,
            high_water_mark=fill_price, stop_loss_price=trailing_stop,
        )
        repo.append_trade(TradeRecord(
            symbol=intent.symbol, strategy_mode=intent.strategy_mode,
            action="OPEN", side="LONG", quantity=fill_qty,
            price=fill_price, realized_pnl=0.0, notes=fill_notes,
        ))
        # Submit to Alpaca broker
        broker_result = _submit_to_broker(intent.symbol, fill_qty, "BUY", estimated_price=fill_price)
        broker_info = broker_result if broker_result else {"skipped": True}
        repo.append_audit_event(ExecutionEventRecord(
            event_type="open_long", symbol=intent.symbol,
            strategy_mode=intent.strategy_mode, correlation_id=correlation_id,
            payload={"price": fill_price, "quantity": fill_qty, "fill": fill_audit, "broker": broker_info},
        ))
    elif intent.intent == "OPEN_SHORT":
        repo.append_audit_event(ExecutionEventRecord(
            event_type="short_open_blocked",
            symbol=intent.symbol,
            strategy_mode=intent.strategy_mode,
            correlation_id=correlation_id,
            payload={"reason": "Cash-only execution blocks opening short positions."},
        ))


def refresh_signals(
    symbols,
    mode="classic",
    start_date="2024-01-01",
    end_date="2026-04-02",
    auto_execute=True,
    quantity=1.0,
    idempotency_key: str | None = None,
):
    normalized_symbols = []
    for symbol in symbols or []:
        normalized_symbol = str(symbol or "").strip().upper()
        if normalized_symbol and normalized_symbol not in normalized_symbols:
            normalized_symbols.append(normalized_symbol)

    # Use the caller-supplied idempotency key as the correlation_id when given;
    # otherwise generate a fresh one.
    correlation_id = str(idempotency_key).strip() if idempotency_key else f"paper-refresh-{uuid4().hex[:12]}"

    # --- kill switch ---------------------------------------------------------
    if is_halted():
        with session_scope() as session:
            repo = ExecutionRepository(session)
            repo.append_audit_event(ExecutionEventRecord(
                event_type="halt_blocked_refresh",
                correlation_id=correlation_id,
                payload={"symbols": normalized_symbols, "mode": mode, "auto_execute": auto_execute},
            ))
        log_event(logger, logging.WARNING, "execution.refresh.halted", correlation_id=correlation_id, symbols=len(normalized_symbols))
        return {"halted": True, "correlation_id": correlation_id, "items": [], "portfolio": {}, "alerts": {}, "signals": {}}
    # -------------------------------------------------------------------------

    # --- idempotency check ---------------------------------------------------
    if idempotency_key:
        with session_scope() as session:
            repo = ExecutionRepository(session)
            if repo.has_audit_event("refresh_completed", correlation_id):
                log_event(logger, logging.INFO, "execution.refresh.deduplicated", correlation_id=correlation_id)
                return {
                    "deduplicated": True,
                    "idempotency_key": idempotency_key,
                    "correlation_id": correlation_id,
                    "items": [],
                    "portfolio": get_internal_portfolio(limit=500),
                    "alerts": get_alert_history(limit=20),
                    "signals": get_signal_history(limit=20),
                }
    # -------------------------------------------------------------------------

    items = []
    quote_lookup = _build_quote_lookup(normalized_symbols)
    with session_scope() as session:
        repo = ExecutionRepository(session)
        log_event(logger, logging.INFO, "execution.refresh.started", strategy_mode=mode, symbols=len(normalized_symbols), auto_execute=auto_execute, correlation_id=correlation_id)
        for normalized_symbol in normalized_symbols:
            try:
                result = build_smart_analysis(normalized_symbol, start_date, end_date, include_dl=True, include_ensemble=True)
                if "error" in result:
                    repo.append_alert(AlertRecord(symbol=normalized_symbol, strategy_mode=mode, alert_type="model_status", severity="warning", message=result.get("error", "signal refresh error"), payload=result))
                    repo.append_audit_event(ExecutionEventRecord(event_type="signal_refresh_error", symbol=normalized_symbol, strategy_mode=mode, correlation_id=correlation_id, payload=result))
                    items.append({"symbol": normalized_symbol, "strategy_mode": mode, "error": result.get("error")})
                    continue

                signal_snapshot = _build_signal_snapshot(normalized_symbol, mode, result, start_date, end_date, quote_lookup=quote_lookup)
                previous_signal = repo.latest_signal(normalized_symbol, mode)
                repo.append_signal(SignalRecord(symbol=normalized_symbol, strategy_mode=mode, signal=signal_snapshot.signal, confidence=signal_snapshot.confidence, price=signal_snapshot.price, reasoning=signal_snapshot.reasoning, payload=signal_snapshot.analysis_payload))
                _record_signal_alerts(repo, mode, signal_snapshot, previous_signal)
                repo.append_audit_event(ExecutionEventRecord(event_type="signal_recorded", symbol=normalized_symbol, strategy_mode=mode, correlation_id=correlation_id, payload=signal_snapshot.model_dump()))

                mode_output = result.get(f"{mode}_output") if mode in {"ml", "dl"} else result.get("ensemble_output") if mode == "ensemble" else None
                if isinstance(mode_output, dict) and mode_output.get("error"):
                    repo.append_alert(AlertRecord(symbol=normalized_symbol, strategy_mode=mode, alert_type="model_status", severity="warning", message=f"{normalized_symbol} {mode} output degraded", payload=mode_output))

                if auto_execute and signal_snapshot.signal in {"BUY", "SELL"}:
                    command = ExecutionCommand(symbol=normalized_symbol, strategy_mode=mode, quantity=quantity, auto_execute=auto_execute, correlation_id=correlation_id)
                    current_row = repo.get_open_position_row(normalized_symbol, mode)
                    current_position = None if current_row is None else PositionState(id=current_row.id, symbol=current_row.symbol, strategy_mode=current_row.strategy_mode, side=current_row.side, quantity=current_row.quantity, avg_entry_price=current_row.avg_entry_price, current_price=current_row.current_price, market_value=current_row.market_value or 0.0, unrealized_pnl=current_row.unrealized_pnl or 0.0, realized_pnl=current_row.realized_pnl or 0.0, status=current_row.status, opened_at=current_row.opened_at, updated_at=current_row.updated_at)
                    intents = _build_trade_intents(current_position, signal_snapshot, command.quantity)
                    for intent in intents:
                        _apply_trade_intent(repo, current_row, intent, correlation_id=correlation_id)
                        if intent.intent.startswith("CLOSE"):
                            current_row = None

                items.append({"symbol": normalized_symbol, "strategy_mode": mode, "signal": signal_snapshot.signal, "confidence": signal_snapshot.confidence, "price": signal_snapshot.price, "reasoning": signal_snapshot.reasoning})
            except Exception as exc:
                log_event(logger, logging.WARNING, "execution.refresh.symbol_failed", symbol=normalized_symbol, strategy_mode=mode, error=str(exc), correlation_id=correlation_id)
                repo.append_alert(AlertRecord(symbol=normalized_symbol, strategy_mode=mode, alert_type="model_status", severity="warning", message=f"{normalized_symbol} signal refresh failed", payload={"error": str(exc)}))
                repo.append_audit_event(ExecutionEventRecord(event_type="signal_refresh_exception", symbol=normalized_symbol, strategy_mode=mode, correlation_id=correlation_id, payload={"error": str(exc)}))
                items.append({"symbol": normalized_symbol, "strategy_mode": mode, "error": str(exc)})

        # Mark this correlation_id as completed so idempotency checks work.
        repo.append_audit_event(ExecutionEventRecord(
            event_type="refresh_completed",
            correlation_id=correlation_id,
            payload={"symbols": normalized_symbols, "mode": mode, "results": len(items)},
        ))
        portfolio = get_internal_portfolio(limit=500)
        alerts = get_alert_history(limit=20)
        signals = get_signal_history(limit=20)

    log_event(logger, logging.INFO, "execution.refresh.completed", strategy_mode=mode, results=len(items), correlation_id=correlation_id)
    return {"items": items, "portfolio": portfolio, "alerts": alerts, "signals": signals, "correlation_id": correlation_id}


def get_internal_portfolio(limit: int = 500) -> dict:
    import os
    with session_scope() as session:
        repo = ExecutionRepository(session)
        items = [position.model_dump(mode="json") for position in repo.list_open_positions()[:limit]]
        all_trades = [row.model_dump(mode="json") for row in repo.list_trades(limit=10000)]

    total_market_value = round(sum(_safe_float(item.get("market_value")) for item in items), 4)
    total_unrealized = round(sum(_safe_float(item.get("unrealized_pnl")) for item in items), 4)
    total_realized = round(sum(_safe_float(item.get("realized_pnl")) for item in items), 4)
    invested_cost = round(
        sum(_safe_float(item.get("avg_entry_price")) * _safe_float(item.get("quantity")) for item in items),
        4,
    )

    # Paper-trading wallet model (no broker required):
    #   starting_cash configurable via MARKET_AI_PAPER_STARTING_CASH (default $100,000)
    #   cash    = starting_cash + realized_pnl - invested_cost
    #   equity  = cash + total_market_value
    starting_cash = _safe_float(os.environ.get("MARKET_AI_PAPER_STARTING_CASH"), default=100_000.0)
    cash_balance = round(starting_cash + total_realized - invested_cost, 4)
    total_equity = round(cash_balance + total_market_value, 4)

    # Close/exit trades (CLOSE action) to compute win rate
    close_trades = [t for t in all_trades if (t.get("action") or "").upper() in {"CLOSE", "CLOSE_LONG", "CLOSE_SHORT", "EXIT"}]
    wins = sum(1 for t in close_trades if _safe_float(t.get("realized_pnl")) > 0)
    total_trades_count = len(all_trades)
    win_rate = round((wins / len(close_trades) * 100.0), 2) if close_trades else None

    summary = {
        "open_positions": len(items),
        "total_market_value": total_market_value,
        "portfolio_value": total_equity,  # frontend "Portfolio Value" should be EQUITY (cash + positions)
        "starting_cash": starting_cash,
        "cash_balance": cash_balance,
        "invested_cost": invested_cost,
        "total_equity": total_equity,
        "total_unrealized_pnl": total_unrealized,
        "total_realized_pnl": total_realized,
        "total_trades": total_trades_count,
        "win_rate_pct": win_rate if win_rate is not None else "-",
    }
    return {
        "items": items,
        "positions": items,  # alias expected by frontend
        "summary": summary,
    }


def _parse_fill_details_from_notes(notes: str | None) -> dict | None:
    """Extract structured fill details from the pipe-delimited notes string.

    Notes format (from paper_fill_engine):
      ``ref=150.00 | spread=+0.0750 | slip=+0.0750 | fill=150.1500 | qty=10/10 | fee=0.0500``
    """
    if not notes:
        return None
    import re  # noqa: PLC0415
    parts = [p.strip() for p in notes.split("|")]
    result: dict = {}
    for part in parts:
        m = re.match(r"ref=([\d.]+)", part)
        if m:
            result["reference_price"] = float(m.group(1))
            continue
        m = re.match(r"spread=([+\-]?[\d.]+)", part)
        if m:
            result["spread_adj"] = float(m.group(1))
            continue
        m = re.match(r"slip=([+\-]?[\d.]+)", part)
        if m:
            result["slippage_adj"] = float(m.group(1))
            continue
        m = re.match(r"fill=([\d.]+)", part)
        if m:
            result["fill_price"] = float(m.group(1))
            continue
        m = re.match(r"qty=(\d+)/(\d+)", part)
        if m:
            filled = int(m.group(1))
            requested = int(m.group(2))
            result["filled_quantity"] = filled
            result["requested_quantity"] = requested
            result["fill_ratio"] = round(filled / requested, 4) if requested > 0 else 1.0
            result["is_partial"] = filled < requested
            continue
        m = re.match(r"fee=([\d.]+)", part)
        if m:
            result["fee_amount"] = float(m.group(1))
            continue
    return result if result else None


def _enrich_with_fill_details(item: dict) -> dict:
    """Add ``fill_details`` key to an order or trade dict by parsing notes."""
    notes = item.get("notes") or ""
    fill_details = _parse_fill_details_from_notes(notes)
    if fill_details:
        item["fill_details"] = fill_details
    return item


def get_trade_history(limit=100):
    with session_scope() as session:
        repo = ExecutionRepository(session)
        return {"items": [_enrich_with_fill_details(row.model_dump(mode="json")) for row in repo.list_trades(limit=limit)]}


def _compact_signal(item: dict) -> dict:
    """Drop the heavy `payload` blob for list views; keep only a lightweight summary.

    The raw `payload` can exceed 250KB per signal (full indicator snapshots),
    which balloons list responses to 30MB+ and chokes the browser. Callers that
    need the full payload can fetch a specific signal by id.
    """
    payload = item.get("payload") or {}
    analysis = payload.get("analysis") if isinstance(payload, dict) else None
    compact_payload = None
    if isinstance(analysis, dict):
        keep = ("close", "rsi14", "macd", "macd_signal", "adx14", "atr14")
        compact_payload = {"analysis": {k: analysis.get(k) for k in keep if k in analysis}}
    item = dict(item)
    item["payload"] = compact_payload
    return item


def get_signal_history(limit=100, *, compact: bool = True):
    with session_scope() as session:
        repo = ExecutionRepository(session)
        rows = [row.model_dump(mode="json") for row in repo.list_signals(limit=limit)]
        if compact:
            rows = [_compact_signal(r) for r in rows]
        return {"items": rows, "count": len(rows)}


def get_alert_history(limit=100, severity: str | None = None):
    with session_scope() as session:
        repo = ExecutionRepository(session)
        rows = repo.list_alerts(limit=limit, severity=severity)
        return {"items": [row.model_dump(mode="json") for row in rows], "count": len(rows)}


def get_execution_audit(limit=100, symbol: str | None = None):
    with session_scope() as session:
        repo = ExecutionRepository(session)
        rows = repo.list_audit_events(limit=limit, symbol=symbol)
        return {"items": [row.model_dump(mode="json") for row in rows], "count": len(rows)}


def list_paper_orders(limit: int = 100, status: str | None = "OPEN") -> dict:
    with session_scope() as session:
        repo = ExecutionRepository(session)
        rows = repo.list_orders(limit=limit, status=status)
        items = [_enrich_with_fill_details(row.model_dump(mode="json")) for row in rows]
        return {"items": items, "count": len(items)}


def create_paper_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    limit_price: float | None = None,
    strategy_mode: str | None = "manual",
    notes: str | None = None,
    client_order_id: str | None = None,
    trace_id: str | None = None,
) -> dict:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_side = str(side or "").strip().upper()
    normalized_order_type = str(order_type or "market").strip().lower()
    if normalized_side not in {"BUY", "SELL"}:
        raise ValueError("Paper order side must be BUY or SELL.")
    if normalized_order_type not in {"market", "limit"}:
        raise ValueError("Paper order type must be market or limit.")
    if float(quantity or 0.0) <= 0:
        raise ValueError("Paper order quantity must be greater than zero.")
    if normalized_order_type == "limit" and limit_price in (None, 0):
        raise ValueError("Limit orders require a limit_price.")

    # --- kill switch ---------------------------------------------------------
    if is_halted():
        correlation_id = f"paper-order-{uuid4().hex[:12]}"
        with session_scope() as session:
            repo = ExecutionRepository(session)
            repo.append_audit_event(ExecutionEventRecord(
                event_type="halt_blocked_order",
                symbol=normalized_symbol,
                strategy_mode=strategy_mode,
                correlation_id=correlation_id,
                payload={"side": normalized_side, "quantity": quantity, "order_type": normalized_order_type},
            ))
        log_event(logger, logging.WARNING, "execution.order.halted", symbol=normalized_symbol, side=normalized_side)
        raise ExecutionHaltedError("Execution is currently halted. Clear the halt before submitting new orders.")
    # -------------------------------------------------------------------------

    # Resolve the client_order_id; use caller-supplied value when provided.
    resolved_client_order_id = str(client_order_id).strip() if client_order_id else f"paper-{uuid4().hex[:12]}"

    # --- idempotency: return existing order if client_order_id already used --
    if client_order_id:
        with session_scope() as session:
            repo = ExecutionRepository(session)
            existing_row = repo.get_order_by_client_id(resolved_client_order_id)
            if existing_row is not None:
                existing = repo.serialize_order(existing_row)
                log_event(logger, logging.INFO, "execution.order.deduplicated", client_order_id=resolved_client_order_id, symbol=normalized_symbol)
                result = existing.model_dump(mode="json")
                result["deduplicated"] = True
                return result
    # -------------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Fill simulation for the manual order path
    # ------------------------------------------------------------------
    ref_price_val = 0.0
    bid_val: float | None = None
    ask_val: float | None = None
    try:
        ref_price_val, quote_payload = _latest_price(normalized_symbol)
        if quote_payload:
            bid_val = _safe_float(quote_payload.get("bid"), None) or None
            ask_val = _safe_float(quote_payload.get("ask"), None) or None
    except Exception:
        pass

    # For limit orders use limit_price as the reference; market uses last trade.
    fill_ref = float(limit_price) if normalized_order_type == "limit" and limit_price else ref_price_val

    fill = compute_fill(
        side=normalized_side,
        quantity=float(quantity),
        reference_price=fill_ref,
        order_type=normalized_order_type,
        limit_price=float(limit_price) if limit_price else None,
        bid=bid_val,
        ask=ask_val,
    )

    with session_scope() as session:
        repo = ExecutionRepository(session)
        current_row = repo.get_any_open_position_row(normalized_symbol)
        current_position = None if current_row is None else PositionState(
            id=current_row.id,
            symbol=current_row.symbol,
            strategy_mode=current_row.strategy_mode,
            side=current_row.side,
            quantity=current_row.quantity,
            avg_entry_price=current_row.avg_entry_price,
            current_price=current_row.current_price,
            market_value=current_row.market_value or 0.0,
            unrealized_pnl=current_row.unrealized_pnl or 0.0,
            realized_pnl=current_row.realized_pnl or 0.0,
            status=current_row.status,
            opened_at=current_row.opened_at,
            updated_at=current_row.updated_at,
        )
        cash_allowed, cash_block_reason = _validate_cash_only_order(
            side=normalized_side,
            symbol=normalized_symbol,
            quantity=float(quantity),
            estimated_price=fill.fill_price if fill.fill_price > 0 else fill_ref,
            fee_amount=fill.fee_amount,
            current_position=current_position,
        )
        if not cash_allowed:
            repo.append_audit_event(ExecutionEventRecord(
                event_type="paper_order_cash_only_blocked",
                symbol=normalized_symbol,
                strategy_mode=strategy_mode,
                correlation_id=trace_id,
                payload={
                    "side": normalized_side,
                    "quantity": float(quantity),
                    "order_type": normalized_order_type,
                    "reason": cash_block_reason,
                },
            ))
            raise ValueError(cash_block_reason)

    # Determine whether the order fills immediately.
    if normalized_order_type == "market":
        order_status = "PARTIAL_FILL" if fill.is_partial else "FILLED"
    elif normalized_order_type == "limit" and ref_price_val > 0 and limit_price:
        # Limit fills immediately if the current price already satisfies the condition.
        lp = float(limit_price)
        cond_met = (normalized_side == "BUY" and ref_price_val <= lp) or (normalized_side == "SELL" and ref_price_val >= lp)
        order_status = ("PARTIAL_FILL" if fill.is_partial else "FILLED") if cond_met else "OPEN"
    else:
        order_status = "OPEN"

    order_notes_parts = [p for p in [notes, fill.to_notes_str() if order_status != "OPEN" else None] if p]
    order = PaperOrderRecord(
        client_order_id=resolved_client_order_id,
        symbol=normalized_symbol,
        strategy_mode=strategy_mode,
        side=normalized_side,
        order_type=normalized_order_type,
        quantity=float(quantity),
        limit_price=None if limit_price is None else float(limit_price),
        status=order_status,
        notes=" | ".join(order_notes_parts) if order_notes_parts else None,
    )
    with session_scope() as session:
        repo = ExecutionRepository(session)
        created = repo.append_order(order)
        repo.append_audit_event(ExecutionEventRecord(
            event_type="paper_order_created",
            symbol=normalized_symbol,
            strategy_mode=strategy_mode,
            correlation_id=trace_id,
            payload={
                **created.model_dump(mode="json"),
                "fill": fill.to_audit_dict() if order_status != "OPEN" else None,
                "trace_id": trace_id,
            },
        ))
    return created.model_dump(mode="json")


def preview_paper_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "market",
    limit_price: float | None = None,
    strategy_mode: str | None = "manual",
    notes: str | None = None,
) -> ExecutionPreview:
    """Phase 1 — compute an execution preview without placing any order.

    Returns an ``ExecutionPreview`` with a ``preview_id`` the caller must pass
    to ``confirm_paper_order()`` within ``_PREVIEW_TTL_SECONDS`` to actually
    execute.  No DB writes occur in this function.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    normalized_symbol = str(symbol or "").strip().upper()
    normalized_side = str(side or "").strip().upper()
    normalized_order_type = str(order_type or "market").strip().lower()

    blocking_reasons: list[str] = []
    warnings_list: list[str] = []

    # --- halt check ----------------------------------------------------------
    halt_info = get_halt_status()
    halted = bool(halt_info.get("halted"))
    if halted:
        blocking_reasons.append(halt_info.get("reason") or "Execution is halted.")

    # --- quote ---------------------------------------------------------------
    ref_price_val = 0.0
    bid_val: float | None = None
    ask_val: float | None = None
    try:
        ref_price_val, quote_payload = _latest_price(normalized_symbol)
        if quote_payload:
            bid_val = _safe_float(quote_payload.get("bid"), None) or None
            ask_val = _safe_float(quote_payload.get("ask"), None) or None
    except Exception:
        warnings_list.append("Could not fetch live quote; using 0.0 as reference price.")

    fill_ref = float(limit_price) if normalized_order_type == "limit" and limit_price else ref_price_val

    # --- fill simulation -----------------------------------------------------
    fill = compute_fill(
        side=normalized_side,
        quantity=float(quantity),
        reference_price=fill_ref,
        order_type=normalized_order_type,
        limit_price=float(limit_price) if limit_price else None,
        bid=bid_val,
        ask=ask_val,
    )

    # --- risk gate (read-only probe) -----------------------------------------
    risk: dict = {"allowed": True, "blocked_reason": None, "warnings": []}
    if not halted:
        try:
            with session_scope() as session:
                repo = ExecutionRepository(session)
                current_row = repo.get_any_open_position_row(normalized_symbol)
                current_position = None if current_row is None else PositionState(
                    id=current_row.id,
                    symbol=current_row.symbol,
                    strategy_mode=current_row.strategy_mode,
                    side=current_row.side,
                    quantity=current_row.quantity,
                    avg_entry_price=current_row.avg_entry_price,
                    current_price=current_row.current_price,
                    market_value=current_row.market_value or 0.0,
                    unrealized_pnl=current_row.unrealized_pnl or 0.0,
                    realized_pnl=current_row.realized_pnl or 0.0,
                    status=current_row.status,
                    opened_at=current_row.opened_at,
                    updated_at=current_row.updated_at,
                )
            risk = check_execution_risk(
                intent="OPEN_LONG" if normalized_side == "BUY" else "CLOSE_LONG",
                symbol=normalized_symbol,
                quantity=float(quantity),
                price=fill_ref,
            )
            if not risk.get("allowed", True):
                blocking_reasons.append(risk.get("blocked_reason") or "Risk gate blocked.")
            warnings_list.extend(risk.get("warnings") or [])
            cash_allowed, cash_block_reason = _validate_cash_only_order(
                side=normalized_side,
                symbol=normalized_symbol,
                quantity=float(quantity),
                estimated_price=fill.fill_price if fill.fill_price > 0 else fill_ref,
                fee_amount=fill.fee_amount,
                current_position=current_position,
            )
            if not cash_allowed and cash_block_reason:
                blocking_reasons.append(cash_block_reason)
        except Exception as exc:
            warnings_list.append(f"Risk gate check failed: {exc}")

    is_safe = len(blocking_reasons) == 0

    # Side cost: BUY increases cash out, SELL increases cash in
    estimated_total_cost = round(
        fill.fill_price * fill.filled_quantity + fill.fee_amount, 4
    ) if normalized_side == "BUY" else round(
        fill.fill_price * fill.filled_quantity - fill.fee_amount, 4
    )

    preview_id = f"prev-{uuid4().hex[:16]}"
    trace_id = f"trace-{uuid4().hex[:16]}"
    expires_ts = time.monotonic() + _PREVIEW_TTL_SECONDS
    expires_at_str = datetime.now(tz=timezone.utc).strftime(
        f"%Y-%m-%dT%H:%M:%SZ"
    )  # approximate wall-clock for display

    preview = ExecutionPreview(
        preview_id=preview_id,
        trace_id=trace_id,
        symbol=normalized_symbol,
        side=normalized_side,
        quantity=float(quantity),
        order_type=normalized_order_type,
        reference_price=ref_price_val,
        estimated_fill_price=fill.fill_price,
        estimated_fee=fill.fee_amount,
        estimated_slippage=fill.slippage_adj,
        estimated_spread=fill.spread_adj,
        estimated_total_cost=estimated_total_cost,
        halt_status=halt_info,
        risk_check=risk,
        is_safe_to_execute=is_safe,
        blocking_reasons=blocking_reasons,
        warnings=warnings_list,
        fill_preview=fill.to_audit_dict(),
        expires_at=expires_at_str,
    )

    # Stash params needed for confirm step
    with _preview_lock:
        # Evict expired entries opportunistically
        now_mono = time.monotonic()
        expired_keys = [k for k, v in _preview_store.items() if v["expires_ts"] < now_mono]
        for k in expired_keys:
            del _preview_store[k]
        _preview_store[preview_id] = {
            "preview": preview,
            "trace_id": trace_id,
            "expires_ts": expires_ts,
            "params": {
                "symbol": normalized_symbol,
                "side": normalized_side,
                "quantity": float(quantity),
                "order_type": normalized_order_type,
                "limit_price": float(limit_price) if limit_price else None,
                "strategy_mode": strategy_mode,
                "notes": notes,
            },
        }

    log_event(logger, logging.DEBUG, "execution.preview.created",
              symbol=normalized_symbol, preview_id=preview_id, is_safe=is_safe)
    return preview


def confirm_paper_order(preview_id: str) -> ExecutionConfirmResult:
    """Phase 2 — confirm a previously computed preview, placing the paper order.

    The preview must exist and must not have expired (TTL = 5 minutes).
    Returns an ``ExecutionConfirmResult`` describing the placed order.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    normalized_preview_id = str(preview_id or "").strip()
    correlation_id = f"confirm-{uuid4().hex[:12]}"

    with _preview_lock:
        entry = _preview_store.get(normalized_preview_id)

    if entry is None:
        return ExecutionConfirmResult(
            client_order_id="",
            preview_id=normalized_preview_id,
            symbol="",
            status="REJECTED",
            blocked_reason="Preview ID not found or already used.",
            audit_correlation_id=correlation_id,
        )

    trace_id = entry.get("trace_id")

    if time.monotonic() > entry["expires_ts"]:
        with _preview_lock:
            _preview_store.pop(normalized_preview_id, None)
        return ExecutionConfirmResult(
            client_order_id="",
            preview_id=normalized_preview_id,
            trace_id=trace_id,
            symbol=entry["params"]["symbol"],
            status="REJECTED",
            blocked_reason="Preview has expired. Request a new preview.",
            audit_correlation_id=correlation_id,
        )

    preview: ExecutionPreview = entry["preview"]

    if not preview.is_safe_to_execute:
        return ExecutionConfirmResult(
            client_order_id="",
            preview_id=normalized_preview_id,
            trace_id=trace_id,
            symbol=preview.symbol,
            status="HALTED" if preview.halt_status.get("halted") else "REJECTED",
            blocked_reason="; ".join(preview.blocking_reasons) or "Execution blocked.",
            audit_correlation_id=correlation_id,
        )

    # Consume preview — remove from store so it cannot be double-confirmed
    with _preview_lock:
        _preview_store.pop(normalized_preview_id, None)

    params = entry["params"]
    client_order_id = f"confirm-{normalized_preview_id}"

    try:
        order_result = create_paper_order(
            symbol=params["symbol"],
            side=params["side"],
            quantity=params["quantity"],
            order_type=params["order_type"],
            limit_price=params.get("limit_price"),
            strategy_mode=params.get("strategy_mode"),
            notes=f"[preview:{normalized_preview_id}] {params.get('notes') or ''}".strip(),
            client_order_id=client_order_id,
            trace_id=trace_id,
        )
        status = order_result.get("status", "FILLED")
        return ExecutionConfirmResult(
            order_id=order_result.get("id"),
            client_order_id=order_result.get("client_order_id") or client_order_id,
            preview_id=normalized_preview_id,
            trace_id=trace_id,
            symbol=params["symbol"],
            status=status,
            fill_price=order_result.get("fill_price") or preview.estimated_fill_price,
            filled_quantity=params["quantity"],
            fee=preview.estimated_fee,
            is_partial=(status == "PARTIAL_FILL"),
            audit_correlation_id=correlation_id,
        )
    except ExecutionHaltedError as exc:
        return ExecutionConfirmResult(
            client_order_id=client_order_id,
            preview_id=normalized_preview_id,
            trace_id=trace_id,
            symbol=params["symbol"],
            status="HALTED",
            blocked_reason=str(exc),
            audit_correlation_id=correlation_id,
        )
    except Exception as exc:
        log_event(logger, logging.ERROR, "execution.confirm.failed",
                  preview_id=normalized_preview_id, error=str(exc))
        return ExecutionConfirmResult(
            client_order_id=client_order_id,
            preview_id=normalized_preview_id,
            trace_id=trace_id,
            symbol=params["symbol"],
            status="REJECTED",
            blocked_reason=f"Order placement failed: {exc}",
            audit_correlation_id=correlation_id,
        )


def cancel_paper_order(order_id: int) -> dict:
    with session_scope() as session:
        repo = ExecutionRepository(session)
        row = repo.get_order_row(order_id)
        if row is None:
            raise LookupError(f"Paper order not found: {order_id}")
        canceled = repo.cancel_order(row, note="Canceled manually")
        repo.append_audit_event(ExecutionEventRecord(
            event_type="paper_order_canceled",
            symbol=canceled.symbol,
            strategy_mode=canceled.strategy_mode,
            payload=canceled.model_dump(mode="json"),
        ))
    return canceled.model_dump(mode="json")


def get_paper_control_panel(*, broker_refresh: bool = False, limit: int = 50) -> dict:
    portfolio = get_internal_portfolio(limit=500)
    open_orders = list_paper_orders(limit=limit, status="OPEN")
    all_orders = list_paper_orders(limit=limit, status=None)
    trades = get_trade_history(limit=limit)
    signals = get_signal_history(limit=limit)
    alerts = get_alert_history(limit=limit)
    audit = get_execution_audit(limit=limit)
    broker = get_broker_summary(refresh=broker_refresh)

    return {
        "paper_mode_only": True,
        "broker": broker,
        "portfolio": portfolio,
        "open_orders": open_orders,
        "orders": all_orders,
        "trades": trades,
        "signals": signals,
        "alerts": alerts,
        "audit": audit,
        "summary": {
            "open_positions": portfolio.get("summary", {}).get("open_positions", 0),
            "open_orders": open_orders.get("count", 0),
            "recent_trades": len(trades.get("items", [])),
            "recent_alerts": alerts.get("count", 0),
            "broker_connected": bool(broker.get("connected")),
            "broker_mode": broker.get("mode") or "paper",
        },
    }
