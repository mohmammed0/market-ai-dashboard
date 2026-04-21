"""Automation job orchestration entrypoints."""

from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter

from backend.app.config import AUTOMATION_DEFAULT_PRESET
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.services.automation.auto_trading import _auto_trading_cycle
from backend.app.services.automation.common import _record_run
from backend.app.services.automation.cycles import (
    _alert_cycle,
    _autonomous_cycle,
    _breadth_cycle,
    _daily_summary,
    _market_cycle,
    _retrain_cycle,
)

logger = get_logger(__name__)

JOB_NAMES = {
    "market_cycle": "Market Cycle",
    "alert_cycle": "Alert Cycle",
    "breadth_cycle": "Breadth Cycle",
    "retrain_cycle": "Retrain Cycle",
    "autonomous_cycle": "Autonomous Cycle",
    "daily_summary": "Daily Summary",
    "auto_trading_cycle": "Auto Trading Cycle",
}


def run_automation_job(job_name: str, dry_run: bool = False, preset: str = AUTOMATION_DEFAULT_PRESET) -> dict:
    normalized = str(job_name or "").strip().lower()
    started_at = datetime.utcnow()
    handlers = {
        "market_cycle": lambda: _market_cycle(dry_run=dry_run, preset=preset),
        "alert_cycle": lambda: _alert_cycle(dry_run=dry_run, preset=preset),
        "breadth_cycle": lambda: _breadth_cycle(dry_run=dry_run, preset=preset),
        "retrain_cycle": lambda: _retrain_cycle(dry_run=dry_run),
        "autonomous_cycle": lambda: _autonomous_cycle(dry_run=dry_run, preset=preset),
        "daily_summary": lambda: _daily_summary(dry_run=dry_run, preset=preset),
        "auto_trading_cycle": lambda: _auto_trading_cycle(dry_run=dry_run, preset=preset),
    }
    handler = handlers.get(normalized)
    if handler is None:
        return {"error": f"Unsupported automation job: {job_name}"}

    started_perf = perf_counter()
    log_event(logger, logging.INFO, "automation.run.started", job_name=normalized, dry_run=dry_run, preset=preset)
    try:
        detail, artifacts = handler()
        result = _record_run(normalized, "completed", started_at, dry_run, detail, artifacts)
        result["duration_seconds"] = round(perf_counter() - started_perf, 4)
        log_event(logger, logging.INFO, "automation.run.completed", job_name=normalized, dry_run=dry_run, duration_seconds=result["duration_seconds"], artifacts=len(artifacts))
        return result
    except Exception as exc:
        result = _record_run(normalized, "error", started_at, dry_run, str(exc), [])
        result["duration_seconds"] = round(perf_counter() - started_perf, 4)
        result["error"] = str(exc)
        log_event(logger, logging.ERROR, "automation.run.failed", job_name=normalized, dry_run=dry_run, duration_seconds=result["duration_seconds"], error=str(exc))
        return result
