"""Trailing stop monitor.

The legacy implementation depended on internal simulated paper positions and
simulated fills. Broker-managed execution is now the only source of truth, so
this scheduler job is intentionally disabled until broker-native trailing-stop
state is wired into the broker account path.
"""

from __future__ import annotations

import logging

from backend.app.core.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def run_trailing_stop_check() -> dict:
    detail = (
        "Trailing stop monitor is disabled because internal paper positions and "
        "simulated fills are no longer active. Broker-managed trailing-stop "
        "automation has not been implemented yet."
    )
    log_event(logger, logging.INFO, "trailing_stop.check.disabled", detail=detail)
    return {
        "checked": 0,
        "triggered": 0,
        "updated": 0,
        "errors": 0,
        "closed_positions": [],
        "status": "disabled",
        "detail": detail,
        "broker_managed_only": True,
        "internal_paper_enabled": False,
    }
