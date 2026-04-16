"""Automation and workflow facade.

This is the stable entry point for scheduled jobs, long-running workflows,
and background-job executors.
"""

from __future__ import annotations

from backend.app.services.automation_hub import get_automation_status
from backend.app.services.continuous_learning import get_continuous_learning_status
from backend.app.services.job_workflows import (
    run_automation_workflow,
    run_backtest_workflow,
    run_batch_inference_workflow,
    run_paper_signal_refresh_workflow,
    run_ranking_scan_workflow,
    run_scan_workflow,
    run_strategy_evaluation_workflow,
    run_vectorbt_backtest_workflow,
)
from core.market_data_providers import get_market_data_provider_status


def get_automation_runtime_status(limit: int = 20) -> dict:
    from backend.app.services.scheduler_runtime import get_scheduler_status

    return {
        "automation": get_automation_status(limit=limit),
        "continuous_learning": get_continuous_learning_status(limit=limit),
        "scheduler": get_scheduler_status(),
        "market_data_provider": get_market_data_provider_status(),
    }


__all__ = [
    "get_automation_runtime_status",
    "run_automation_workflow",
    "run_backtest_workflow",
    "run_batch_inference_workflow",
    "run_paper_signal_refresh_workflow",
    "run_ranking_scan_workflow",
    "run_scan_workflow",
    "run_strategy_evaluation_workflow",
    "run_vectorbt_backtest_workflow",
]
