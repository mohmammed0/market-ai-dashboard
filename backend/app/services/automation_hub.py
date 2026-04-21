"""Compatibility facade for automation services.

Canonical implementation now lives under `backend.app.services.automation.*`.
This module preserves legacy imports and behavior for existing callers.
"""

from backend.app.services.automation.auto_trading import _auto_trading_cycle, _is_us_market_open
from backend.app.services.automation.common import (
    _analysis_window,
    _available_local_symbols,
    _build_ranked_candidates,
    _preferred_local_symbols,
    _record_run,
    _refresh_symbol_history,
    _review_and_promote,
    _rotate_symbol_batch,
    _select_symbols_for_cycle,
    _training_overlap_guard,
    _training_window,
    _utc_today_iso,
)
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
    "_analysis_window",
    "_auto_trading_cycle",
    "_autonomous_cycle",
    "_available_local_symbols",
    "_breadth_cycle",
    "_build_ranked_candidates",
    "_daily_summary",
    "_is_us_market_open",
    "_market_cycle",
    "_preferred_local_symbols",
    "_record_run",
    "_refresh_symbol_history",
    "_retrain_cycle",
    "_review_and_promote",
    "_rotate_symbol_batch",
    "_select_symbols_for_cycle",
    "_training_overlap_guard",
    "_training_window",
    "_utc_today_iso",
    "get_automation_status",
    "run_automation_job",
]
