from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowRegistration:
    workflow_name: str
    description: str
    owner: str


WORKFLOW_REGISTRY: tuple[WorkflowRegistration, ...] = (
    WorkflowRegistration("automation.run", "Run a named automation workflow.", "automation"),
    WorkflowRegistration("backtest.run", "Run a backtest workflow.", "research_training"),
    WorkflowRegistration("scan.run", "Run a market scan workflow.", "strategy_runtime"),
    WorkflowRegistration("strategy.evaluate", "Run strategy evaluation.", "research_training"),
)


def list_workflow_registrations() -> list[dict]:
    return [item.__dict__.copy() for item in WORKFLOW_REGISTRY]


__all__ = ["WorkflowRegistration", "WORKFLOW_REGISTRY", "list_workflow_registrations"]

