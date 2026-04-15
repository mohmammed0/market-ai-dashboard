from __future__ import annotations

import os

from backend.app.config import (
    RISK_DEFAULT_PORTFOLIO_VALUE,
    RISK_DEFAULT_STOP_PCT,
    RISK_DEFAULT_TARGET_PCT,
    RISK_MAX_DAILY_LOSS_PCT,
    RISK_MAX_TRADE_PCT,
)


def build_trade_risk_plan(
    entry_price: float,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    portfolio_value: float = RISK_DEFAULT_PORTFOLIO_VALUE,
    risk_per_trade_pct: float = RISK_MAX_TRADE_PCT,
    max_daily_loss_pct: float = RISK_MAX_DAILY_LOSS_PCT,
    atr_pct: float | None = None,
) -> dict:
    entry = float(entry_price or 0.0)
    if entry <= 0:
        return {"error": "Entry price must be greater than zero."}

    stop = float(stop_loss_price) if stop_loss_price not in (None, 0) else entry * (1 - (float(atr_pct or RISK_DEFAULT_STOP_PCT) / 100.0))
    target = float(take_profit_price) if take_profit_price not in (None, 0) else entry * (1 + (float(RISK_DEFAULT_TARGET_PCT) / 100.0))
    per_share_risk = max(entry - stop, 0.01)
    account_risk_budget = max(float(portfolio_value) * float(risk_per_trade_pct) / 100.0, 0.0)
    quantity = int(account_risk_budget / per_share_risk) if account_risk_budget > 0 else 0
    total_position_value = round(quantity * entry, 2)
    reward_per_share = max(target - entry, 0.0)
    reward_risk_ratio = round(reward_per_share / per_share_risk, 2) if per_share_risk else None
    warnings = []

    if reward_risk_ratio is not None and reward_risk_ratio < 1.5:
        warnings.append("Reward/risk is below the preferred 1.5 threshold.")
    if total_position_value > portfolio_value * 0.25:
        warnings.append("Position value exceeds 25% of the portfolio and may raise concentration risk.")
    if stop >= entry:
        warnings.append("Stop loss is not below entry price.")

    return {
        "entry_price": round(entry, 4),
        "stop_loss_price": round(stop, 4),
        "take_profit_price": round(target, 4),
        "per_share_risk": round(per_share_risk, 4),
        "reward_per_share": round(reward_per_share, 4),
        "reward_risk_ratio": reward_risk_ratio,
        "risk_budget_dollars": round(account_risk_budget, 2),
        "max_daily_loss_dollars": round(float(portfolio_value) * float(max_daily_loss_pct) / 100.0, 2),
        "suggested_quantity": int(quantity),
        "position_value": total_position_value,
        "warnings": warnings,
    }


def check_execution_risk(
    intent: str,
    symbol: str,
    quantity: float,
    price: float,
    portfolio_value: float = RISK_DEFAULT_PORTFOLIO_VALUE,
    risk_per_trade_pct: float = RISK_MAX_TRADE_PCT,
) -> dict:
    """Pre-trade risk gate.  Returns ``{"allowed": bool, ...}``.

    Rules
    -----
    - CLOSE / NONE intents are always allowed (closing a losing position is safe).
    - OPEN intents are blocked when ``quantity × price`` exceeds the configured
      per-trade risk budget (``risk_per_trade_pct`` % of ``portfolio_value``).
    - A zero or negative execution price is always blocked.
    """
    normalized_intent = str(intent or "").strip().upper()
    if normalized_intent in {"CLOSE_LONG", "CLOSE_SHORT", "NONE"}:
        return {"allowed": True, "blocked_reason": None, "warnings": []}

    price_f = float(price or 0.0)
    quantity_f = max(float(quantity or 0.0), 0.0)

    if price_f <= 0.0:
        return {
            "allowed": False,
            "blocked_reason": "Execution price must be greater than zero.",
            "warnings": [],
        }

    position_value = price_f * quantity_f
    risk_budget = float(portfolio_value) * float(risk_per_trade_pct) / 100.0
    warnings: list[str] = []

    if position_value > float(portfolio_value) * 0.25:
        warnings.append(
            f"Position value ${position_value:.2f} exceeds 25% of portfolio (${portfolio_value:.2f})."
        )

    if risk_budget > 0 and position_value > risk_budget:
        return {
            "allowed": False,
            "blocked_reason": (
                f"{symbol} position value ${position_value:.2f} exceeds the per-trade risk budget "
                f"${risk_budget:.2f} ({risk_per_trade_pct}% of ${portfolio_value:.2f})."
            ),
            "warnings": warnings,
            "position_value": round(position_value, 4),
            "risk_budget": round(risk_budget, 4),
        }

    return {
        "allowed": True,
        "blocked_reason": None,
        "warnings": warnings,
        "position_value": round(position_value, 4),
        "risk_budget": round(risk_budget, 4),
    }


def get_risk_dashboard(portfolio_value: float = RISK_DEFAULT_PORTFOLIO_VALUE) -> dict:
    # Local import to avoid circular dependency: risk_engine → portfolio_intelligence → portfolio/service → execution/service → risk_engine
    from backend.app.application.portfolio.service import get_portfolio_exposure  # noqa: PLC0415
    exposure = get_portfolio_exposure()
    summary = exposure.get("summary", {})
    alerts = list(exposure.get("warnings", []))
    total_market_value = float(summary.get("total_market_value", 0.0) or 0.0)
    gross_exposure_pct = round((total_market_value / float(portfolio_value)) * 100.0, 2) if portfolio_value else 0.0
    if gross_exposure_pct > 80:
        alerts.append("Gross paper exposure exceeds 80% of the configured portfolio value.")

    return {
        "portfolio_value": float(portfolio_value),
        "max_risk_per_trade_pct": float(RISK_MAX_TRADE_PCT),
        "max_daily_loss_pct": float(RISK_MAX_DAILY_LOSS_PCT),
        "default_stop_pct": float(RISK_DEFAULT_STOP_PCT),
        "default_target_pct": float(RISK_DEFAULT_TARGET_PCT),
        "gross_exposure_pct": gross_exposure_pct,
        "portfolio_summary": summary,
        "portfolio_warnings": alerts,
    }


# --- Trailing Stop Loss ---

DEFAULT_TRAILING_STOP_PCT = float(os.getenv("MARKET_AI_TRAILING_STOP_PCT", "5.0"))


def compute_trailing_stop(
    side: str,
    current_price: float,
    high_water_mark: float | None,
    trailing_stop_pct: float = DEFAULT_TRAILING_STOP_PCT,
    existing_trailing_stop: float | None = None,
) -> dict:
    """Compute trailing stop price for a position.

    For LONG: stop trails below the highest price seen.
    For SHORT: stop trails above the lowest price seen.

    Returns:
        {
            "trailing_stop_price": float,   - current stop level
            "high_water_mark": float,       - best price seen
            "triggered": bool,              - True if stop hit
            "distance_pct": float,          - how far price is from stop
        }
    """
    price = float(current_price or 0.0)
    pct = max(float(trailing_stop_pct or DEFAULT_TRAILING_STOP_PCT), 0.1)

    if side.upper() == "LONG":
        # Track highest price
        hwm = max(price, float(high_water_mark or price))
        stop = round(hwm * (1 - pct / 100.0), 4)
        # Never lower the stop
        if existing_trailing_stop and existing_trailing_stop > stop:
            stop = existing_trailing_stop
        triggered = price <= stop
        distance = round((price - stop) / price * 100, 2) if price > 0 else 0
    else:
        # SHORT: track lowest price
        hwm = min(price, float(high_water_mark or price)) if high_water_mark else price
        stop = round(hwm * (1 + pct / 100.0), 4)
        # Never raise the stop for shorts
        if existing_trailing_stop and existing_trailing_stop < stop:
            stop = existing_trailing_stop
        triggered = price >= stop
        distance = round((stop - price) / price * 100, 2) if price > 0 else 0

    return {
        "trailing_stop_price": stop,
        "high_water_mark": hwm,
        "triggered": triggered,
        "distance_pct": distance,
        "trailing_stop_pct": pct,
    }


def evaluate_positions_trailing_stops(positions: list[dict], quotes: dict[str, float]) -> list[dict]:
    """Evaluate trailing stops for all open positions.

    Args:
        positions: list of position dicts with symbol, side, trailing_stop_pct, etc.
        quotes: {symbol: current_price} lookup

    Returns:
        list of triggered positions with close recommendations
    """
    triggered = []
    for pos in positions:
        symbol = pos.get("symbol", "")
        current_price = quotes.get(symbol, pos.get("current_price", 0))
        if not current_price or current_price <= 0:
            continue

        trailing_pct = pos.get("trailing_stop_pct")
        if not trailing_pct:
            trailing_pct = DEFAULT_TRAILING_STOP_PCT

        result = compute_trailing_stop(
            side=pos.get("side", "LONG"),
            current_price=current_price,
            high_water_mark=pos.get("high_water_mark"),
            trailing_stop_pct=trailing_pct,
            existing_trailing_stop=pos.get("trailing_stop_price"),
        )

        if result["triggered"]:
            entry = float(pos.get("avg_entry_price", 0))
            sign = 1 if pos.get("side") == "LONG" else -1
            pnl = round((current_price - entry) * float(pos.get("quantity", 0)) * sign, 2)
            triggered.append({
                **pos,
                "current_price": current_price,
                "trailing_stop": result,
                "realized_pnl_estimate": pnl,
                "action": "CLOSE",
            })

    return triggered
