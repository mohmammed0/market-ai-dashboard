from __future__ import annotations

from pydantic import BaseModel


class RiskProfile(BaseModel):
    profile_name: str = "default"
    max_position_pct: float = 10.0
    max_daily_loss_pct: float = 2.0
    max_symbol_concentration_pct: float = 20.0


__all__ = ["RiskProfile"]

