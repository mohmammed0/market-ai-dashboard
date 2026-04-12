"""Prefect Flow Definitions — Live workflow execution through Prefect.

Wraps existing application workflow functions with Prefect @flow and @task
decorators so they execute through Prefect's runtime when available:

- Flow runs are tracked in the Prefect server
- Task-level observability
- Retry and failure handling via Prefect

The orchestration gateway calls these flows directly (local execution tracked
by the Prefect server) without requiring pre-registered deployments.

Usage:
    from backend.app.services.prefect_flows import get_flow
    flow_fn = get_flow("batch_inference")
    result = flow_fn(payload={...})
"""

from __future__ import annotations

from typing import Any, Callable

from backend.app.core.logging_utils import get_logger

logger = get_logger(__name__)

_FLOW_REGISTRY: dict[str, Callable] = {}
_REGISTERED: bool = False


def get_flow(workflow_name: str) -> Callable | None:
    """Get a registered Prefect flow by workflow name. Returns None if not found."""
    global _REGISTERED
    if not _REGISTERED:
        _register_flows()
        _REGISTERED = True
    return _FLOW_REGISTRY.get(workflow_name)


def list_flows() -> list[str]:
    """Return names of all registered Prefect flows."""
    global _REGISTERED
    if not _REGISTERED:
        _register_flows()
        _REGISTERED = True
    return list(_FLOW_REGISTRY.keys())


def _register_flows():
    """Register all Prefect flows. Called lazily to avoid import-time overhead."""
    try:
        from prefect import flow, task  # type: ignore[import-not-found]
    except ImportError:
        logger.debug("prefect not installed — no flows registered")
        return

    @task(name="execute_strategy_evaluation", retries=1)
    def strategy_evaluation_task(payload: dict) -> dict:
        from backend.app.services.job_workflows import run_strategy_evaluation_workflow  # noqa: PLC0415
        return run_strategy_evaluation_workflow(payload)

    @flow(name="strategy_evaluation", log_prints=True)
    def strategy_evaluation_flow(payload: dict) -> dict:
        """Run strategy evaluation through Prefect with full tracking."""
        flow_run_id = _get_flow_run_id()
        print(f"[Prefect] strategy_evaluation flow_run={flow_run_id}")
        print(f"[Prefect] instrument={payload.get('instrument', '?')}")
        result = strategy_evaluation_task(payload)
        if isinstance(result, dict):
            result["_prefect_flow_run_id"] = flow_run_id
        return result

    @task(name="execute_batch_inference", retries=1)
    def batch_inference_task(payload: dict) -> dict:
        from backend.app.services.job_workflows import run_batch_inference_workflow  # noqa: PLC0415
        return run_batch_inference_workflow(payload)

    @flow(name="batch_inference", log_prints=True)
    def batch_inference_flow(payload: dict) -> dict:
        """Run batch inference through Prefect with full tracking."""
        flow_run_id = _get_flow_run_id()
        print(f"[Prefect] batch_inference flow_run={flow_run_id}")
        print(f"[Prefect] symbols={payload.get('symbols', [])}")
        result = batch_inference_task(payload)
        if isinstance(result, dict):
            result["_prefect_flow_run_id"] = flow_run_id
        return result

    _FLOW_REGISTRY["strategy_evaluation"] = strategy_evaluation_flow
    _FLOW_REGISTRY["batch_inference"] = batch_inference_flow
    logger.info("Prefect flows registered: %s", list(_FLOW_REGISTRY.keys()))


def _get_flow_run_id() -> str | None:
    """Extract the current flow run ID from Prefect context."""
    try:
        from prefect.context import get_run_context  # type: ignore[import-not-found]
        ctx = get_run_context()
        return str(ctx.flow_run.id)
    except Exception:
        return None
