from __future__ import annotations


def daily_loss_within_limit(*, current_daily_loss_pct: float, max_daily_loss_pct: float) -> bool:
    return float(current_daily_loss_pct) <= float(max_daily_loss_pct)


__all__ = ["daily_loss_within_limit"]

