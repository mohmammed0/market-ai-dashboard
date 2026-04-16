"""Risk domain service facade.

This boundary owns deterministic pre-trade guardrails.  It can consume
portfolio facts such as available cash and held quantity, but it must remain
free of broker-side effects.
"""

from __future__ import annotations

from backend.app.services.risk_engine import (
    build_trade_risk_plan,
    check_execution_risk,
    get_risk_dashboard,
)


def assess_execution_guardrails(
    *,
    intent: str,
    side: str,
    symbol: str,
    quantity: float,
    price: float,
    fee_amount: float = 0.0,
    portfolio_value: float | None = None,
    risk_per_trade_pct: float | None = None,
    available_cash: float | None = None,
    current_side: str | None = None,
    current_quantity: float | None = None,
    trading_mode: str = "cash",
) -> dict:
    """Return a unified pre-trade decision for execution.

    The result intentionally combines pure risk-budget checks with cash-only
    and long-only portfolio rules so execution can ask a single domain service
    whether an action is allowed.
    """

    normalized_intent = str(intent or "").strip().upper()
    normalized_side = str(side or "").strip().upper()
    symbol_text = str(symbol or "").strip().upper()
    qty = max(float(quantity or 0.0), 0.0)
    px = max(float(price or 0.0), 0.0)
    fee = max(float(fee_amount or 0.0), 0.0)
    held_qty = max(float(current_quantity or 0.0), 0.0)
    held_side = str(current_side or "").strip().upper() or None
    normalized_trading_mode = "margin" if str(trading_mode or "").strip().lower() == "margin" else "cash"
    margin_enabled = normalized_trading_mode == "margin"

    kwargs: dict[str, float] = {}
    if portfolio_value is not None:
        kwargs["portfolio_value"] = float(portfolio_value)
    if risk_per_trade_pct is not None:
        kwargs["risk_per_trade_pct"] = float(risk_per_trade_pct)

    risk_check = check_execution_risk(
        intent=normalized_intent,
        symbol=symbol_text,
        quantity=qty,
        price=px,
        **kwargs,
    )

    cash_check = {
        "allowed": True,
        "blocked_reason": None,
        "required_cash": None,
        "available_cash": None,
        "held_quantity": held_qty,
        "held_side": held_side,
        "trading_mode": normalized_trading_mode,
    }

    if normalized_side == "BUY":
        required_cash = round((qty * px) + fee, 4)
        cash_check["required_cash"] = required_cash
        cash_check["available_cash"] = None if available_cash is None else round(float(available_cash), 4)
        if normalized_intent == "CLOSE_SHORT" and held_side == "SHORT" and held_qty > 0:
            pass
        elif margin_enabled:
            if available_cash is not None and required_cash > float(available_cash):
                cash_check["available_cash_warning"] = (
                    f"{symbol_text} buy exceeds current cash by ${required_cash - float(available_cash):.2f}; "
                    "margin mode will rely on broker buying power."
                )
        elif available_cash is not None and required_cash > float(available_cash):
            cash_check["allowed"] = False
            cash_check["blocked_reason"] = (
                f"{symbol_text} buy requires ${required_cash:.2f} cash, but only "
                f"${float(available_cash):.2f} is available. Cash-only execution blocks margin usage."
            )
    elif normalized_side == "SELL":
        if normalized_intent == "CLOSE_LONG" and held_side == "LONG" and held_qty > 0 and qty - held_qty <= 1e-9:
            pass
        elif margin_enabled:
            if held_side == "LONG" and held_qty > 0 and qty - held_qty > 1e-9:
                cash_check["borrow_warning"] = (
                    f"{symbol_text} sell exceeds held quantity and will open or extend a short position in margin mode."
                )
        elif held_side != "LONG" or held_qty <= 0:
            cash_check["allowed"] = False
            cash_check["blocked_reason"] = (
                f"{symbol_text} cannot be sold because no long shares are currently held. "
                "Short selling is disabled."
            )
        elif qty - held_qty > 1e-9:
            cash_check["allowed"] = False
            cash_check["blocked_reason"] = (
                f"{symbol_text} sell quantity {qty:.4f} exceeds held long quantity {held_qty:.4f}. "
                "Cash-only execution blocks short selling."
            )

    blocking_reasons = [
        reason
        for reason in [risk_check.get("blocked_reason"), cash_check.get("blocked_reason")]
        if reason
    ]

    return {
        "allowed": risk_check.get("allowed", False) and cash_check.get("allowed", False),
        "blocking_reasons": blocking_reasons,
        "blocked_reason": None if not blocking_reasons else blocking_reasons[0],
        "warnings": list(risk_check.get("warnings") or []),
        "risk_check": risk_check,
        "cash_check": cash_check,
        "trading_mode": normalized_trading_mode,
    }


__all__ = [
    "assess_execution_guardrails",
    "build_trade_risk_plan",
    "get_risk_dashboard",
]
