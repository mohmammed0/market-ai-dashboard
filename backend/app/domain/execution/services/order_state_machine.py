from __future__ import annotations

from packages.contracts.enums import ExecutionStatus, can_transition


def transition_execution_status(current: ExecutionStatus, target: ExecutionStatus) -> ExecutionStatus:
    if not can_transition(current, target):
        raise ValueError(f"Invalid execution status transition: {current} -> {target}")
    return target


__all__ = ["transition_execution_status"]

