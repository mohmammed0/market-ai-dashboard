from __future__ import annotations

from backend.app.application.broker.service import get_broker_status


def broker_health_guard() -> dict:
    status = get_broker_status()
    return {
        "healthy": bool(status.get("connected")) or not bool(status.get("enabled")),
        "status": status,
    }


__all__ = ["broker_health_guard"]

