from __future__ import annotations

from typing import Any


def build_ai_explanation_readmodel(
    *,
    signal_facts: dict[str, Any] | None = None,
    portfolio_facts: dict[str, Any] | None = None,
    market_facts: dict[str, Any] | None = None,
    risk_facts: dict[str, Any] | None = None,
) -> dict:
    return {
        "signal_facts": signal_facts or {},
        "portfolio_facts": portfolio_facts or {},
        "market_facts": market_facts or {},
        "risk_facts": risk_facts or {},
    }


__all__ = ["build_ai_explanation_readmodel"]

