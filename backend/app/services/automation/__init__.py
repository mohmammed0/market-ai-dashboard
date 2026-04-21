"""Automation service package.

Split of the former `automation_hub` into focused modules with a compatibility
facade retained at `backend.app.services.automation_hub`.
"""

from backend.app.services.automation.auto_trading import _auto_trading_cycle, _is_us_market_open
from backend.app.services.automation.cycles import (
    _alert_cycle,
    _autonomous_cycle,
    _breadth_cycle,
    _daily_summary,
    _market_cycle,
    _retrain_cycle,
)
from backend.app.services.automation.diagnostics import get_automation_status
from backend.app.services.automation.orchestration import JOB_NAMES, run_automation_job

__all__ = [
    "JOB_NAMES",
    "_alert_cycle",
    "_auto_trading_cycle",
    "_autonomous_cycle",
    "_breadth_cycle",
    "_daily_summary",
    "_is_us_market_open",
    "_market_cycle",
    "_retrain_cycle",
    "get_automation_status",
    "run_automation_job",
]
