"""
Kelly Criterion + ATR-based position sizing.

Kelly fraction = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
ATR sizing = risk_per_trade / ATR_value
"""
from __future__ import annotations

import math


def kelly_fraction(
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    max_fraction: float = 0.25,
) -> float:
    """Full Kelly, capped at max_fraction (25% by default for safety).

    Kelly fraction = (win_rate * avg_win - loss_rate * avg_loss) / avg_win
    """
    try:
        win_rate = float(win_rate)
        avg_win_pct = float(avg_win_pct)
        avg_loss_pct = float(avg_loss_pct)
        max_fraction = float(max_fraction)

        if avg_win_pct <= 0:
            return 0.0

        loss_rate = 1.0 - win_rate
        kelly = (win_rate * avg_win_pct - loss_rate * avg_loss_pct) / avg_win_pct
        kelly = max(kelly, 0.0)
        return round(min(kelly, max_fraction), 6)
    except Exception:
        return 0.0


def half_kelly(
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
) -> float:
    """Half-Kelly — recommended for live trading."""
    full = kelly_fraction(win_rate, avg_win_pct, avg_loss_pct, max_fraction=0.25)
    return round(full * 0.5, 6)


def atr_position_size(
    account_equity: float,
    atr_value: float,
    risk_per_trade_pct: float = 1.0,
    price: float = None,
    atr_multiplier: float = 1.0,
) -> dict:
    """ATR-based position sizing.

    shares = (account_equity * risk_pct) / (atr_multiplier * atr_value)
    Returns: {shares, dollar_risk, stop_distance, position_value}
    """
    try:
        account_equity = float(account_equity)
        atr_value = float(atr_value)
        risk_per_trade_pct = float(risk_per_trade_pct)
        atr_multiplier = float(atr_multiplier)

        if atr_value <= 0 or account_equity <= 0:
            return {
                "shares": 0,
                "dollar_risk": 0.0,
                "stop_distance": 0.0,
                "position_value": 0.0,
                "error": "Invalid ATR or equity value",
            }

        dollar_risk = account_equity * (risk_per_trade_pct / 100.0)
        stop_distance = atr_multiplier * atr_value
        shares = dollar_risk / stop_distance if stop_distance > 0 else 0
        shares = math.floor(shares)  # whole shares only

        position_value = shares * float(price) if price else shares * atr_value
        return {
            "shares": shares,
            "dollar_risk": round(dollar_risk, 2),
            "stop_distance": round(stop_distance, 4),
            "position_value": round(position_value, 2),
            "atr_value": round(atr_value, 4),
            "risk_per_trade_pct": risk_per_trade_pct,
        }
    except Exception as exc:
        return {"shares": 0, "dollar_risk": 0.0, "stop_distance": 0.0, "position_value": 0.0, "error": str(exc)}


def combined_sizing(
    account_equity: float,
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    atr_value: float,
    price: float,
    risk_per_trade_pct: float = 1.0,
) -> dict:
    """Combine Kelly + ATR: use Kelly for sizing direction, ATR for stop placement.

    Returns full sizing recommendation dict.
    """
    try:
        account_equity = float(account_equity)
        price = float(price)
        risk_per_trade_pct = float(risk_per_trade_pct)

        full_k = kelly_fraction(win_rate, avg_win_pct, avg_loss_pct)
        half_k = half_kelly(win_rate, avg_win_pct, avg_loss_pct)

        # ATR sizing gives us the share count based on volatility-adjusted risk
        atr_size = atr_position_size(account_equity, atr_value, risk_per_trade_pct, price)

        # Kelly fraction scales the equity allocation
        kelly_equity = account_equity * full_k
        half_kelly_equity = account_equity * half_k
        kelly_shares = math.floor(kelly_equity / price) if price > 0 else 0
        half_kelly_shares = math.floor(half_kelly_equity / price) if price > 0 else 0

        # Recommended: take the minimum of Kelly and ATR sizing (conservative)
        recommended_shares = min(atr_size["shares"], kelly_shares) if kelly_shares > 0 else atr_size["shares"]
        recommended_value = round(recommended_shares * price, 2)

        return {
            "kelly_fraction": full_k,
            "half_kelly_fraction": half_k,
            "kelly_shares": kelly_shares,
            "half_kelly_shares": half_kelly_shares,
            "atr_shares": atr_size["shares"],
            "recommended_shares": recommended_shares,
            "recommended_position_value": recommended_value,
            "stop_distance": atr_size["stop_distance"],
            "dollar_risk": atr_size["dollar_risk"],
            "kelly_equity_allocation": round(kelly_equity, 2),
            "half_kelly_equity_allocation": round(half_kelly_equity, 2),
            "account_equity": account_equity,
            "price": price,
            "atr_value": round(float(atr_value), 4),
            "win_rate": win_rate,
            "avg_win_pct": avg_win_pct,
            "avg_loss_pct": avg_loss_pct,
        }
    except Exception as exc:
        return {"error": str(exc), "recommended_shares": 0}
