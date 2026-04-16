from __future__ import annotations

from backend.app.repositories.platform_events import PlatformEventRepository
from backend.app.services.storage import session_scope
from backend.app.automation.service import (
    run_automation_workflow,
    run_backtest_workflow,
    run_scan_workflow,
    run_strategy_evaluation_workflow,
)


WORKFLOW_DISPATCHERS = {
    "automation.run": run_automation_workflow,
    "backtest.run": run_backtest_workflow,
    "scan.run": run_scan_workflow,
    "strategy.evaluate": run_strategy_evaluation_workflow,
}


def dispatch_workflow(workflow_name: str, payload: dict) -> dict:
    handler = WORKFLOW_DISPATCHERS.get(str(workflow_name or "").strip())
    if handler is None:
        raise KeyError(f"Unknown workflow: {workflow_name}")
    correlation_id = None
    if isinstance(payload, dict):
        correlation_id = payload.get("correlation_id")
    with session_scope() as session:
        repo = PlatformEventRepository(session)
        workflow_run = repo.create_workflow_run(
            workflow_name=workflow_name,
            correlation_id=correlation_id,
            payload=payload,
        )
        try:
            result = handler(payload)
            repo.complete_workflow_run(workflow_run, status="completed", result=result)
            return result
        except Exception as exc:
            repo.complete_workflow_run(
                workflow_run,
                status="failed",
                result={"error": str(exc)},
            )
            raise


__all__ = ["WORKFLOW_DISPATCHERS", "dispatch_workflow"]
