"""Auto-trading cycle and market-session gating logic.

Broker-managed execution remains the canonical execution/account truth path.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from backend.app.config import AUTOMATION_DEFAULT_PRESET, AUTO_TRADING_QUANTITY, DEFAULT_SAMPLE_SYMBOLS
from backend.app.services.automation.common import _analysis_window, _preferred_local_symbols, _rotate_symbol_batch, _utc_today_iso
from backend.app.services.market_universe import resolve_universe_preset
from backend.app.services.signal_runtime import build_smart_analysis


def _auto_trading_cycle(dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> tuple[str, list[dict]]:
    """Auto-trading cycle: scan all symbols, generate signals, auto-execute BUY orders.

    Paper-mode friendly: if MARKET_AI_PAPER_TRADING_24_7=1 OR Alpaca is not properly
    configured, we run the cycle against the INTERNAL paper_positions table with no
    market-hours restriction and no broker dependency. This lets the bot trade
    continuously for simulation/learning.
    """
    import os

    from backend.app.services.runtime_settings import get_auto_trading_config

    paper_24_7 = str(os.environ.get("MARKET_AI_PAPER_TRADING_24_7", "1")).strip() in {"1", "true", "True", "yes"}

    # Check runtime settings
    auto_config = get_auto_trading_config()
    # In paper-only mode we only need auto_trading.enabled — Alpaca is irrelevant for
    # internal paper positions. This unblocks trading when broker creds are missing/invalid.
    paper_ready = bool(auto_config["auto_trading_enabled"])
    effective_ready = paper_ready if paper_24_7 else auto_config["ready"]

    if not effective_ready:
        return (
            f"auto_trading_cycle skipped: not ready (auto_trading={auto_config['auto_trading_enabled']}, "
            f"order_sub={auto_config['order_submission_enabled']}, alpaca_configured={auto_config['alpaca_configured']}, paper_24_7={paper_24_7})",
            [{"artifact_type": "auto_trading_status", "artifact_key": "skipped", "payload": {**auto_config, "paper_24_7": paper_24_7}}],
        )

    broker_sync_result = None
    if not paper_24_7 and auto_config.get("order_submission_enabled") and auto_config.get("alpaca_configured"):
        try:
            from backend.app.application.execution.service import sync_internal_positions_from_broker

            broker_sync_result = sync_internal_positions_from_broker(strategy_mode="classic")
            if str(auto_config.get("trading_mode") or "cash").strip().lower() == "cash" and int(broker_sync_result.get("short_positions") or 0) > 0:
                return (
                    "auto_trading_cycle skipped: broker account has short positions while cash mode is active",
                    [
                        {
                            "artifact_type": "auto_trading_status",
                            "artifact_key": "cash_mode_short_positions",
                            "payload": {
                                **auto_config,
                                "paper_24_7": paper_24_7,
                                "broker_sync": broker_sync_result,
                            },
                        }
                    ],
                )
        except Exception as exc:
            return (
                f"auto_trading_cycle skipped: broker sync failed ({exc})",
                [
                    {
                        "artifact_type": "auto_trading_status",
                        "artifact_key": "broker_sync_failed",
                        "payload": {
                            **auto_config,
                            "paper_24_7": paper_24_7,
                            "error": str(exc),
                        },
                    }
                ],
            )

    if dry_run:
        return (
            "auto_trading_cycle dry_run=True",
            [{"artifact_type": "auto_trading_status", "artifact_key": "dry_run", "payload": {"dry_run": True, **auto_config, "broker_sync": broker_sync_result}}],
        )

    # Market-hours check: bypass when paper_24_7 is enabled (pure internal simulation).
    market_open = _is_us_market_open() if not paper_24_7 else True
    if not market_open:
        return (
            "auto_trading_cycle skipped: market is closed",
            [{"artifact_type": "auto_trading_status", "artifact_key": "market_closed", "payload": {"market_open": False, "broker_sync": broker_sync_result}}],
        )

    # Cap symbols per cycle so the schedule doesn't overlap with itself.
    # Each full ML analysis takes ~2 min on a 2-vCPU box, so for a 5-min cycle we
    # typically pick 2 symbols (see MARKET_AI_AUTO_TRADING_SYMBOL_LIMIT in .env).
    try:
        symbol_limit = int(os.environ.get("MARKET_AI_AUTO_TRADING_SYMBOL_LIMIT", "10"))
    except Exception:
        symbol_limit = 10
    symbol_limit = max(1, min(symbol_limit, 500))
    full_portfolio_mode = str(os.environ.get("MARKET_AI_AUTO_TRADING_USE_FULL_PORTFOLIO", "0")).strip().lower() in {"1", "true", "yes", "on"}
    universe_preset = str(auto_config.get("universe_preset") or preset or AUTOMATION_DEFAULT_PRESET).strip().upper()
    use_top_market_cap_rotation = universe_preset == "TOP_500_MARKET_CAP"
    symbols = list(DEFAULT_SAMPLE_SYMBOLS)
    rotation_state = {"offset": 0, "next_offset": 0, "pool_size": len(symbols), "batch_size": 0}
    ranked_universe_symbols: list[str] = []
    if use_top_market_cap_rotation:
        try:
            top_market_cap = resolve_universe_preset("TOP_500_MARKET_CAP", limit=500)
            ranked_universe_symbols = list(top_market_cap.get("symbols") or [])
            rotated_batch, rotation_state = _rotate_symbol_batch(ranked_universe_symbols, symbol_limit)
            if rotated_batch:
                symbols = rotated_batch
        except Exception:
            ranked_universe_symbols = []

    # Rotation: prefer symbols that don't already have an open position so each
    # cycle has a real chance to generate a NEW trade. Reserve one slot for a
    # held name so exit signals still get re-evaluated periodically.
    import random as _random

    try:
        from backend.app.application.execution.service import get_internal_portfolio

        held_payload = get_internal_portfolio(limit=500) or {}
        held_positions = {
            str(pos.get("symbol") or "").upper(): str(pos.get("side") or "").upper()
            for pos in (held_payload.get("items") or [])
            if (pos.get("status") or "").upper() == "OPEN"
        }
        held = set(held_positions.keys())
    except Exception:
        held_positions = {}
        held = set()

    if use_top_market_cap_rotation and ranked_universe_symbols:
        held_pool = [s for s in ranked_universe_symbols if s in held]
        rotation = [s for s in symbols if s not in held]
        if held_pool and held_pool[0] not in rotation:
            rotation = [held_pool[0], *rotation]
        symbols = list(dict.fromkeys(rotation))[:symbol_limit] or list(DEFAULT_SAMPLE_SYMBOLS)[:symbol_limit]
    else:
        unheld = [s for s in symbols if s not in held]
        held_pool = [s for s in symbols if s in held]
        _random.shuffle(unheld)
        _random.shuffle(held_pool)
        if symbol_limit >= 2 and held_pool and unheld:
            rotation = unheld[: symbol_limit - 1] + held_pool[:1]
        else:
            rotation = (unheld + held_pool)[:symbol_limit]
        symbols = rotation[:symbol_limit] or list(DEFAULT_SAMPLE_SYMBOLS)[:symbol_limit]
    candidate_symbols = list(symbols)
    if full_portfolio_mode and not use_top_market_cap_rotation:
        mover_limit = max(symbol_limit * 4, 12)
        try:
            local_candidates = []
            for candidate in _preferred_local_symbols(preset):
                normalized = str(candidate or "").upper()
                if not normalized.isalpha():
                    continue
                if len(normalized) > 5:
                    continue
                if normalized.endswith(("W", "U", "R")):
                    continue
                local_candidates.append(normalized)
                if len(local_candidates) >= 80:
                    break
            snapshot_symbols = local_candidates or list(DEFAULT_SAMPLE_SYMBOLS)
            from backend.app.services.market_data import fetch_quote_snapshots

            mover_snapshots = fetch_quote_snapshots(snapshot_symbols, include_profile=False)
            mover_items = [
                item
                for item in (mover_snapshots or {}).get("items", [])
                if float(item.get("last_price") or item.get("price") or 0.0) >= 5.0
            ]
            mover_symbols = [
                str(item.get("symbol") or "").upper()
                for item in sorted(
                    mover_items,
                    key=lambda entry: abs(float(entry.get("change_pct") or 0.0)),
                    reverse=True,
                )
                if str(item.get("symbol") or "").strip()
            ][:mover_limit]
            candidate_symbols = list(dict.fromkeys(held_pool + mover_symbols))
        except Exception:
            candidate_symbols = list(dict.fromkeys(held_pool + list(DEFAULT_SAMPLE_SYMBOLS)[:mover_limit]))
    elif use_top_market_cap_rotation:
        candidate_symbols = list(symbols)

    # Run signal refresh with auto-execute.
    # Use a shorter analysis window for auto-trading so each symbol finishes fast
    # enough that cycles don't pile up behind the 5-min schedule.
    from backend.app.application.execution.service import refresh_signals
    from datetime import datetime as _dt, timedelta as _td

    try:
        lookback_days = int(os.environ.get("MARKET_AI_AUTO_TRADING_ANALYSIS_LOOKBACK_DAYS", "0"))
    except Exception:
        lookback_days = 0

    if lookback_days > 0:
        end_date = _utc_today_iso()
        start_date = (_dt.utcnow() - _td(days=lookback_days)).strftime("%Y-%m-%d")
    else:
        start_date, end_date = _analysis_window()

    # --- dynamic position sizing: aim for NOTIONAL_PER_TRADE dollars per symbol.
    # In full-portfolio mode we size from the internal paper wallet cash balance,
    # which makes the next entry consume all currently available cash.
    # Fetch quotes up-front (cheap) to size each order in shares. Falls back to the
    # flat AUTO_TRADING_QUANTITY when a quote is unavailable.
    fallback_qty = max(AUTO_TRADING_QUANTITY, 1.0)
    try:
        notional_per_trade = float(os.environ.get("MARKET_AI_AUTO_TRADING_NOTIONAL_PER_TRADE", "0") or 0.0)
    except Exception:
        notional_per_trade = 0.0
    portfolio_cash_balance = 0.0
    portfolio_equity = 0.0
    try:
        from backend.app.application.execution.service import get_internal_portfolio

        portfolio_payload = get_internal_portfolio(limit=500) or {}
        portfolio_summary = portfolio_payload.get("summary") or {}
        portfolio_cash_balance = float(portfolio_summary.get("cash_balance") or 0.0)
        portfolio_equity = float(portfolio_summary.get("total_equity") or 0.0)
    except Exception:
        portfolio_payload = {}
        portfolio_summary = {}

    if full_portfolio_mode:
        notional_per_trade = max(portfolio_cash_balance, 0.0)
        if notional_per_trade <= 0:
            notional_per_trade = max(portfolio_equity, 0.0)

    price_lookup: dict[str, float] = {}
    quote_symbols = list(
        dict.fromkeys(candidate_symbols if full_portfolio_mode and candidate_symbols else symbols)
    )
    if notional_per_trade > 0 and quote_symbols:
        try:
            from backend.app.services.market_data import fetch_quote_snapshots

            snap = fetch_quote_snapshots(quote_symbols, include_profile=False)
            for item in (snap or {}).get("items", []):
                sym = str(item.get("symbol") or "").upper()
                px = float(item.get("last_price") or item.get("price") or 0.0)
                if sym and px > 0:
                    price_lookup[sym] = px
        except Exception:
            price_lookup = {}

    def _compute_qty(symbol: str, budget: float | None = None) -> float:
        effective_budget = float(notional_per_trade if budget is None else budget or 0.0)
        if effective_budget <= 0:
            return fallback_qty
        px = price_lookup.get(symbol.upper(), 0.0)
        if px <= 0:
            return fallback_qty
        shares = max(int(effective_budget // px), 1)
        return float(shares)

    # Loop per symbol when dynamic sizing is active so each order can carry its
    # own share count. Small N here (typically 2) keeps this practical.
    aggregate_items: list[dict] = []
    last_correlation: str | None = None
    allocated_quantities: dict[str, float] = {}
    selected_execution_candidates: list[dict] = []
    try:
        if notional_per_trade > 0:
            if full_portfolio_mode and candidate_symbols:
                preview_candidates: list[dict] = []
                actionable_candidates: list[dict] = []
                for index, sym in enumerate(candidate_symbols):
                    try:
                        preview_result = build_smart_analysis(sym, start_date, end_date, include_dl=False, include_ensemble=True)
                        if "error" in preview_result:
                            preview_candidates.append({"symbol": sym, "error": preview_result.get("error")})
                            continue
                        signal_view = extract_signal_view(preview_result, mode="classic")
                        signal_value = str(signal_view.get("signal") or "HOLD").upper()
                        current_side = held_positions.get(sym.upper())
                        desired_side = "LONG" if signal_value == "BUY" else "SHORT" if signal_value == "SELL" else None
                        preview_entry = {
                            "symbol": sym,
                            "signal": signal_value,
                            "confidence": float(signal_view.get("confidence") or 0.0),
                            "price": float(signal_view.get("price") or price_lookup.get(sym.upper()) or 0.0),
                            "current_side": current_side,
                            "result": preview_result,
                        }
                        preview_candidates.append(preview_entry)
                        if desired_side and current_side != desired_side and preview_entry["price"] >= 5.0:
                            actionable_candidates.append(preview_entry)
                    except Exception as exc:
                        preview_candidates.append({"symbol": sym, "error": str(exc)})
                actionable_candidates = [
                    item for item in sorted(actionable_candidates, key=lambda entry: float(entry.get("confidence") or 0.0), reverse=True)
                    if float(item.get("price") or price_lookup.get(item.get("symbol", "").upper()) or 0.0) > 0
                ]
                if actionable_candidates:
                    selected_candidates = actionable_candidates[:symbol_limit]
                    selected_execution_candidates = list(selected_candidates)
                    symbols = [item["symbol"] for item in selected_candidates]
                    budget_per_symbol = max(float(notional_per_trade) * 0.995 / len(selected_candidates), 0.0)
                    for item in selected_candidates:
                        qty = _compute_qty(item["symbol"], budget=budget_per_symbol)
                        if qty > 0:
                            allocated_quantities[item["symbol"].upper()] = qty
            if not full_portfolio_mode and symbols and not allocated_quantities:
                for sym in symbols:
                    qty = _compute_qty(sym, budget=float(notional_per_trade))
                    if qty > 0:
                        allocated_quantities[sym.upper()] = qty
            if full_portfolio_mode and symbols and not allocated_quantities:
                new_entry_symbols = [sym for sym in symbols if sym.upper() not in held_positions] or list(symbols)
                budget_per_symbol = max(float(notional_per_trade) * 0.995 / len(new_entry_symbols), 0.0)
                for sym in new_entry_symbols:
                    qty = _compute_qty(sym, budget=budget_per_symbol)
                    if qty > 0:
                        allocated_quantities[sym.upper()] = qty
            if full_portfolio_mode and selected_execution_candidates:
                from backend.app.application.execution.service import (
                    _apply_trade_intent,
                    _build_quote_lookup,
                    _build_signal_snapshot,
                    _build_trade_intents,
                    _record_signal_alerts,
                    get_alert_history,
                    get_internal_portfolio,
                    get_signal_history,
                )
                from backend.app.domain.execution.contracts import ExecutionEventRecord, PositionState, SignalRecord
                from backend.app.repositories.execution import ExecutionRepository
                from backend.app.services.storage import session_scope

                last_correlation = f"paper-refresh-{uuid4().hex[:12]}"
                quote_lookup = _build_quote_lookup(symbols)
                with session_scope() as session:
                    repo = ExecutionRepository(session)
                    for item in selected_execution_candidates:
                        sym = item["symbol"]
                        signal_snapshot = _build_signal_snapshot(
                            sym,
                            "classic",
                            item.get("result") or build_smart_analysis(sym, start_date, end_date, include_dl=False, include_ensemble=True),
                            start_date,
                            end_date,
                            quote_lookup=quote_lookup,
                        )
                        previous_signal = repo.latest_signal(sym, "classic")
                        repo.append_signal(
                            SignalRecord(
                                symbol=sym,
                                strategy_mode="classic",
                                signal=signal_snapshot.signal,
                                confidence=signal_snapshot.confidence,
                                price=signal_snapshot.price,
                                reasoning=signal_snapshot.reasoning,
                                payload=signal_snapshot.analysis_payload,
                            )
                        )
                        _record_signal_alerts(repo, "classic", signal_snapshot, previous_signal)
                        repo.append_audit_event(
                            ExecutionEventRecord(
                                event_type="signal_recorded",
                                symbol=sym,
                                strategy_mode="classic",
                                correlation_id=last_correlation,
                                payload=signal_snapshot.model_dump(),
                            )
                        )
                        current_row = repo.get_open_position_row(sym, "classic")
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
                        qty = allocated_quantities.get(sym.upper(), fallback_qty)
                        intents = _build_trade_intents(current_position, signal_snapshot, qty)
                        for intent in intents:
                            _apply_trade_intent(repo, current_row, intent, correlation_id=last_correlation)
                            if intent.intent.startswith("CLOSE"):
                                current_row = None
                        aggregate_items.append(
                            {
                                "symbol": sym,
                                "strategy_mode": "classic",
                                "signal": signal_snapshot.signal,
                                "confidence": signal_snapshot.confidence,
                                "price": signal_snapshot.price,
                                "reasoning": signal_snapshot.reasoning,
                            }
                        )
                    repo.append_audit_event(
                        ExecutionEventRecord(
                            event_type="refresh_completed",
                            correlation_id=last_correlation,
                            payload={"symbols": symbols, "mode": "classic", "results": len(aggregate_items)},
                        )
                    )
                result = {
                    "items": aggregate_items,
                    "correlation_id": last_correlation,
                    "portfolio": get_internal_portfolio(limit=500),
                    "alerts": get_alert_history(limit=20),
                    "signals": get_signal_history(limit=20),
                }
            else:
                result = refresh_signals(
                    symbols=symbols,
                    mode="classic",
                    start_date=start_date,
                    end_date=end_date,
                    auto_execute=True,
                    quantity=fallback_qty,
                    quantity_map=allocated_quantities,
                )
                aggregate_items = list(result.get("items", []))
                last_correlation = result.get("correlation_id") or last_correlation
            quantity = fallback_qty  # reported default; per-symbol used above
        else:
            result = refresh_signals(
                symbols=symbols,
                mode="classic",
                start_date=start_date,
                end_date=end_date,
                auto_execute=True,
                quantity=fallback_qty,
            )
            quantity = fallback_qty
    except Exception as exc:
        return (
            f"auto_trading_cycle failed: {exc}",
            [{"artifact_type": "auto_trading_error", "artifact_key": "execution_failed", "payload": {"error": str(exc)}}],
        )

    # Summarize results
    items = result.get("items", [])
    buy_signals = [i for i in items if i.get("signal") == "BUY"]
    sell_signals = [i for i in items if i.get("signal") == "SELL"]
    hold_signals = [i for i in items if i.get("signal") == "HOLD"]
    errors = [i for i in items if i.get("error")]

    summary = {
        "generated_at": datetime.utcnow().isoformat(),
        "universe_preset": universe_preset,
        "use_top_market_cap_rotation": use_top_market_cap_rotation,
        "broker_sync": broker_sync_result,
        "symbols_scanned": len(symbols),
        "buy_signals": len(buy_signals),
        "sell_signals": len(sell_signals),
        "hold_signals": len(hold_signals),
        "errors": len(errors),
        "auto_executed": True,
        "quantity_per_trade": quantity,
        "full_portfolio_mode": full_portfolio_mode,
        "notional_per_trade": round(float(notional_per_trade or 0.0), 4),
        "portfolio_cash_balance": round(float(portfolio_cash_balance or 0.0), 4),
        "allocated_quantities": allocated_quantities,
        "correlation_id": result.get("correlation_id"),
        "rotation": rotation_state,
        "rotation_pool_size": len(ranked_universe_symbols),
        "top_buys": [
            {"symbol": i["symbol"], "confidence": i.get("confidence", 0), "price": i.get("price", 0)}
            for i in sorted(buy_signals, key=lambda x: x.get("confidence", 0), reverse=True)[:5]
        ],
        "portfolio": result.get("portfolio", {}),
    }

    # Send Telegram notification
    try:
        from backend.app.services.trade_notifier import notify_auto_trading_summary

        notify_auto_trading_summary(
            symbols_scanned=len(symbols),
            buy_count=len(buy_signals),
            sell_count=len(sell_signals),
            hold_count=len(hold_signals),
            errors=len(errors),
            top_buys=summary.get("top_buys", []),
        )
    except Exception:
        pass

    detail = (
        f"auto_trading_cycle preset={universe_preset} scanned={len(symbols)} buys={len(buy_signals)} "
        f"sells={len(sell_signals)} holds={len(hold_signals)} errors={len(errors)} "
        f"qty={quantity}"
    )

    artifacts = [
        {"artifact_type": "auto_trading_summary", "artifact_key": _utc_today_iso(), "payload": summary},
        {"artifact_type": "auto_trading_signals", "artifact_key": "latest", "payload": items},
        {"artifact_type": "auto_trading_rotation", "artifact_key": universe_preset.lower(), "payload": rotation_state},
    ]

    return detail, artifacts


def _is_us_market_open() -> bool:
    """Check if the US stock market is currently open (9:30 AM - 4:00 PM ET, weekdays)."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    now_et = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/New_York"))

    # Weekend check
    if now_et.weekday() >= 5:
        return False

    # Market hours: 9:30 AM to 4:00 PM ET
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now_et <= market_close
