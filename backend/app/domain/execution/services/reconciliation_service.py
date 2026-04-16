from __future__ import annotations

from backend.app.adapters.broker.alpaca import reconcile as reconcile_alpaca


def reconcile_execution_state(*, broker: str = "alpaca") -> dict:
    if str(broker or "").strip().lower() == "alpaca":
        return reconcile_alpaca()
    return {"broker": broker, "detail": "No reconciliation adapter configured.", "orders": [], "positions": []}


__all__ = ["reconcile_execution_state"]

