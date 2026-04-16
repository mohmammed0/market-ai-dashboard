from __future__ import annotations


def concentration_within_limit(*, symbol_weight_pct: float, max_symbol_concentration_pct: float) -> bool:
    return float(symbol_weight_pct) <= float(max_symbol_concentration_pct)


__all__ = ["concentration_within_limit"]

