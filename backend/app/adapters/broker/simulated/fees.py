from __future__ import annotations


def estimate_fee(quantity: float, fill_price: float, basis_points: float = 0.0) -> float:
    return round(float(quantity or 0.0) * float(fill_price or 0.0) * (float(basis_points or 0.0) / 10000.0), 4)


__all__ = ["estimate_fee"]

