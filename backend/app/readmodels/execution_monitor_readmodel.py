from __future__ import annotations

from backend.app.execution.service import (
    get_alert_history,
    get_execution_audit,
    get_internal_portfolio,
    get_signal_history,
    get_trade_history,
    list_paper_orders,
)
from backend.app.services.execution_halt import get_halt_status


def build_execution_monitor_readmodel(*, limit: int = 100) -> dict:
    return {
        "portfolio": get_internal_portfolio(limit=max(limit, 500)),
        "open_orders": list_paper_orders(limit=limit, status="OPEN"),
        "orders": list_paper_orders(limit=limit, status=None),
        "trades": get_trade_history(limit=limit),
        "signals": get_signal_history(limit=limit),
        "alerts": get_alert_history(limit=limit),
        "audit": get_execution_audit(limit=limit),
        "halt_status": get_halt_status(),
    }


__all__ = ["build_execution_monitor_readmodel"]

