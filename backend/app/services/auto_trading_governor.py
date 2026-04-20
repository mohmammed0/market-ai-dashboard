from __future__ import annotations

from datetime import datetime, timedelta
import logging
from uuid import uuid4

from backend.app.config import (
    AUTO_TRADING_CYCLE_LEASE_SECONDS,
    AUTO_TRADING_DAILY_LOSS_AUTO_HALT,
    RISK_MAX_DAILY_LOSS_PCT,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.models import PaperTrade, SchedulerLease
from backend.app.services.execution_halt import enable_halt, get_halt_status
from backend.app.services.storage import session_scope

logger = get_logger(__name__)

AUTO_TRADING_CYCLE_LEASE_NAME = "automation.auto_trading_cycle"


def acquire_auto_trading_cycle_lease(*, holder_id: str | None = None, ttl_seconds: int | None = None) -> dict:
    """Acquire an exclusive lease for the auto-trading cycle.

    Prevents overlapping auto-trading runs when scheduler ticks while a prior
    cycle is still running.
    """
    holder = str(holder_id or f"auto-trading-{uuid4().hex[:12]}").strip()
    now = datetime.utcnow()
    ttl = max(int(ttl_seconds or AUTO_TRADING_CYCLE_LEASE_SECONDS), 30)
    expires_at = now + timedelta(seconds=ttl)

    with session_scope() as session:
        row = session.query(SchedulerLease).filter(SchedulerLease.lease_name == AUTO_TRADING_CYCLE_LEASE_NAME).first()
        if row is not None and row.expires_at is not None and row.expires_at > now:
            return {
                "acquired": False,
                "lease_name": AUTO_TRADING_CYCLE_LEASE_NAME,
                "active_holder_id": row.holder_id,
                "active_acquired_at": row.acquired_at.isoformat() if row.acquired_at else None,
                "active_expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "requested_holder_id": holder,
                "requested_ttl_seconds": ttl,
            }

        if row is None:
            row = SchedulerLease(
                lease_name=AUTO_TRADING_CYCLE_LEASE_NAME,
                holder_id=holder,
                acquired_at=now,
                expires_at=expires_at,
            )
            session.add(row)
        else:
            row.holder_id = holder
            row.acquired_at = now
            row.expires_at = expires_at
        session.flush()

    log_event(
        logger,
        logging.INFO,
        "auto_trading.lease.acquired",
        lease_name=AUTO_TRADING_CYCLE_LEASE_NAME,
        holder_id=holder,
        ttl_seconds=ttl,
    )
    return {
        "acquired": True,
        "lease_name": AUTO_TRADING_CYCLE_LEASE_NAME,
        "holder_id": holder,
        "acquired_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": ttl,
    }


def release_auto_trading_cycle_lease(*, holder_id: str | None, force: bool = False) -> dict:
    holder = str(holder_id or "").strip()
    with session_scope() as session:
        row = session.query(SchedulerLease).filter(SchedulerLease.lease_name == AUTO_TRADING_CYCLE_LEASE_NAME).first()
        if row is None:
            return {
                "released": False,
                "lease_name": AUTO_TRADING_CYCLE_LEASE_NAME,
                "reason": "missing_lease",
            }
        if not force and holder and row.holder_id != holder:
            return {
                "released": False,
                "lease_name": AUTO_TRADING_CYCLE_LEASE_NAME,
                "reason": "holder_mismatch",
                "active_holder_id": row.holder_id,
                "requested_holder_id": holder,
            }
        session.delete(row)

    log_event(
        logger,
        logging.INFO,
        "auto_trading.lease.released",
        lease_name=AUTO_TRADING_CYCLE_LEASE_NAME,
        holder_id=holder or None,
        force=bool(force),
    )
    return {
        "released": True,
        "lease_name": AUTO_TRADING_CYCLE_LEASE_NAME,
        "holder_id": holder or None,
    }


def build_daily_realized_loss_snapshot(portfolio_summary: dict | None = None) -> dict:
    summary = portfolio_summary if isinstance(portfolio_summary, dict) else {}
    daily_loss_limit_pct = max(float(RISK_MAX_DAILY_LOSS_PCT), 0.0)
    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    close_actions = {"CLOSE", "CLOSE_LONG", "CLOSE_SHORT", "EXIT"}
    realized_pnl_today = 0.0
    close_trades_count = 0

    try:
        with session_scope() as session:
            rows = (
                session.query(PaperTrade.realized_pnl)
                .filter(
                    PaperTrade.created_at >= day_start,
                    PaperTrade.created_at < day_end,
                    PaperTrade.action.in_(close_actions),
                )
                .all()
            )
            close_trades_count = len(rows)
            realized_pnl_today = round(sum(float(row[0] or 0.0) for row in rows), 4)
    except Exception:
        realized_pnl_today = 0.0
        close_trades_count = 0

    starting_cash = float(summary.get("starting_cash") or 0.0)
    if starting_cash <= 0:
        import os

        starting_cash = float(os.environ.get("MARKET_AI_PAPER_STARTING_CASH", "100000") or 100000)
    base_equity = max(float(starting_cash), 1.0)
    daily_loss_dollars = max(-realized_pnl_today, 0.0)
    daily_loss_pct = round((daily_loss_dollars / base_equity) * 100.0, 4) if base_equity > 0 else 0.0
    breached = bool(daily_loss_limit_pct > 0 and daily_loss_pct >= daily_loss_limit_pct)

    return {
        "window_start_utc": day_start.isoformat(),
        "window_end_utc": day_end.isoformat(),
        "close_trades_count": close_trades_count,
        "realized_pnl_today": realized_pnl_today,
        "daily_loss_dollars": round(daily_loss_dollars, 4),
        "daily_loss_pct": daily_loss_pct,
        "max_daily_loss_pct": round(daily_loss_limit_pct, 4),
        "breached": breached,
    }


def evaluate_daily_loss_guard(
    portfolio_summary: dict | None = None,
    *,
    auto_halt_enabled: bool | None = None,
) -> dict:
    snapshot = build_daily_realized_loss_snapshot(portfolio_summary)
    should_auto_halt = AUTO_TRADING_DAILY_LOSS_AUTO_HALT if auto_halt_enabled is None else bool(auto_halt_enabled)
    try:
        halt_status = get_halt_status()
    except Exception as exc:
        halt_status = {
            "halted": False,
            "reason": "",
            "enabled_by": "",
            "enabled_at": "",
            "error": str(exc),
        }
    halted = bool(halt_status.get("halted"))
    halted_now = False

    if snapshot.get("breached") and should_auto_halt:
        if not halted:
            loss_pct = float(snapshot.get("daily_loss_pct") or 0.0)
            limit_pct = float(snapshot.get("max_daily_loss_pct") or 0.0)
            reason = (
                "Auto-trading halted after breaching daily loss limit: "
                f"{loss_pct:.2f}% >= {limit_pct:.2f}%."
            )
            try:
                halt_status = enable_halt(reason=reason, enabled_by="auto_trading_cycle")
                halted = bool(halt_status.get("halted"))
                halted_now = halted
            except Exception as exc:
                halt_status = {
                    "halted": False,
                    "reason": reason,
                    "enabled_by": "auto_trading_cycle",
                    "enabled_at": "",
                    "error": str(exc),
                }
                halted = False
                halted_now = False
        else:
            halted = True

    return {
        "daily_risk": snapshot,
        "breached": bool(snapshot.get("breached")),
        "auto_halt_enabled": should_auto_halt,
        "halted": halted,
        "halted_now": halted_now,
        "halt_status": halt_status,
    }
