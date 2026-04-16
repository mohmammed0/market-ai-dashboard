from __future__ import annotations


def regime_allows_risk(*, regime: str, blocked_regimes: set[str] | None = None) -> bool:
    if not blocked_regimes:
        return True
    return str(regime or "").strip().lower() not in {item.lower() for item in blocked_regimes}


__all__ = ["regime_allows_risk"]

