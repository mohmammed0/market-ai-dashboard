from __future__ import annotations

from fastapi import APIRouter, Body

from backend.app.services.position_sizing import (
    atr_position_size,
    combined_sizing,
    half_kelly,
    kelly_fraction,
)

router = APIRouter(prefix="/position-sizing", tags=["risk"])


@router.post("/kelly")
def calculate_kelly(
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    account_equity: float = 100000,
):
    """Calculate Kelly fraction and recommended position size."""
    full_k = kelly_fraction(win_rate, avg_win_pct, avg_loss_pct)
    half_k = half_kelly(win_rate, avg_win_pct, avg_loss_pct)
    return {
        "full_kelly_fraction": full_k,
        "half_kelly_fraction": half_k,
        "full_kelly_equity": round(account_equity * full_k, 2),
        "half_kelly_equity": round(account_equity * half_k, 2),
        "account_equity": account_equity,
        "win_rate": win_rate,
        "avg_win_pct": avg_win_pct,
        "avg_loss_pct": avg_loss_pct,
        "recommendation": "Use half-Kelly for live trading to reduce variance.",
    }


@router.post("/atr")
def calculate_atr_size(
    account_equity: float,
    atr_value: float,
    price: float,
    risk_pct: float = 1.0,
):
    """ATR-based position sizing."""
    return atr_position_size(
        account_equity=account_equity,
        atr_value=atr_value,
        risk_per_trade_pct=risk_pct,
        price=price,
    )


@router.post("/combined")
def calculate_combined(body: dict = Body(...)):
    """Combined Kelly + ATR sizing.

    Expected body:
    {
        "account_equity": 100000,
        "win_rate": 0.55,
        "avg_win_pct": 2.0,
        "avg_loss_pct": 1.0,
        "atr_value": 3.5,
        "price": 150.0,
        "risk_per_trade_pct": 1.0
    }
    """
    try:
        return combined_sizing(
            account_equity=float(body.get("account_equity", 100000)),
            win_rate=float(body.get("win_rate", 0.5)),
            avg_win_pct=float(body.get("avg_win_pct", 2.0)),
            avg_loss_pct=float(body.get("avg_loss_pct", 1.0)),
            atr_value=float(body.get("atr_value", 1.0)),
            price=float(body.get("price", 100.0)),
            risk_per_trade_pct=float(body.get("risk_per_trade_pct", 1.0)),
        )
    except Exception as exc:
        return {"error": str(exc)}
