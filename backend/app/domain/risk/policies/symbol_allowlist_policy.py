from __future__ import annotations


def symbol_is_allowed(symbol: str, allowlist: set[str] | None = None) -> bool:
    if not allowlist:
        return True
    return str(symbol or "").strip().upper() in {item.upper() for item in allowlist}


__all__ = ["symbol_is_allowed"]

