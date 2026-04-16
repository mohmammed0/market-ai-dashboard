from __future__ import annotations


def strategy_is_enabled(strategy_id: str, enabled_strategies: set[str] | None = None) -> bool:
    if not enabled_strategies:
        return True
    return str(strategy_id or "").strip() in enabled_strategies


__all__ = ["strategy_is_enabled"]

