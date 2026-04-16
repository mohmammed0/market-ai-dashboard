from __future__ import annotations


def broker_is_healthy(status: dict) -> bool:
    return bool(status.get("enabled")) and bool(status.get("connected", True))


__all__ = ["broker_is_healthy"]

