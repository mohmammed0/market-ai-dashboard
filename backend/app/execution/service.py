"""Execution domain service facade.

The current implementation delegates to the existing application-layer
execution service so we can migrate callers incrementally without breaking
the runtime contract.
"""

from backend.app.application.execution.service import (
    cancel_paper_order,
    confirm_paper_order,
    create_paper_order,
    get_alert_history,
    get_execution_audit,
    get_internal_portfolio,
    get_signal_history,
    get_trade_history,
    list_paper_orders,
    preview_paper_order,
    refresh_signals,
)

__all__ = [
    "cancel_paper_order",
    "confirm_paper_order",
    "create_paper_order",
    "get_alert_history",
    "get_execution_audit",
    "get_internal_portfolio",
    "get_signal_history",
    "get_trade_history",
    "list_paper_orders",
    "preview_paper_order",
    "refresh_signals",
]
