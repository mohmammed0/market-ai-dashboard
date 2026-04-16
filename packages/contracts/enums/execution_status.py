from __future__ import annotations

from enum import StrEnum


class ExecutionStatus(StrEnum):
    DRAFT = "DRAFT"
    RISK_PENDING = "RISK_PENDING"
    RISK_REJECTED = "RISK_REJECTED"
    APPROVED = "APPROVED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    RECONCILING = "RECONCILING"
    RECONCILED = "RECONCILED"
    FAILED = "FAILED"


ALLOWED_EXECUTION_TRANSITIONS: dict[ExecutionStatus, set[ExecutionStatus]] = {
    ExecutionStatus.DRAFT: {ExecutionStatus.RISK_PENDING},
    ExecutionStatus.RISK_PENDING: {ExecutionStatus.RISK_REJECTED, ExecutionStatus.APPROVED},
    ExecutionStatus.RISK_REJECTED: set(),
    ExecutionStatus.APPROVED: {ExecutionStatus.SUBMITTING},
    ExecutionStatus.SUBMITTING: {ExecutionStatus.SUBMITTED, ExecutionStatus.REJECTED, ExecutionStatus.FAILED},
    ExecutionStatus.SUBMITTED: {ExecutionStatus.ACKNOWLEDGED, ExecutionStatus.REJECTED, ExecutionStatus.FAILED},
    ExecutionStatus.ACKNOWLEDGED: {
        ExecutionStatus.PARTIALLY_FILLED,
        ExecutionStatus.FILLED,
        ExecutionStatus.CANCEL_PENDING,
        ExecutionStatus.RECONCILING,
    },
    ExecutionStatus.PARTIALLY_FILLED: {
        ExecutionStatus.FILLED,
        ExecutionStatus.CANCEL_PENDING,
        ExecutionStatus.RECONCILING,
    },
    ExecutionStatus.FILLED: {ExecutionStatus.RECONCILING, ExecutionStatus.RECONCILED},
    ExecutionStatus.CANCEL_PENDING: {ExecutionStatus.CANCELED, ExecutionStatus.FAILED},
    ExecutionStatus.CANCELED: {ExecutionStatus.RECONCILING, ExecutionStatus.RECONCILED},
    ExecutionStatus.REJECTED: {ExecutionStatus.RECONCILING, ExecutionStatus.RECONCILED},
    ExecutionStatus.RECONCILING: {ExecutionStatus.RECONCILED, ExecutionStatus.FAILED},
    ExecutionStatus.RECONCILED: set(),
    ExecutionStatus.FAILED: {ExecutionStatus.RECONCILING},
}


def can_transition(current: ExecutionStatus, target: ExecutionStatus) -> bool:
    return target in ALLOWED_EXECUTION_TRANSITIONS.get(current, set())


__all__ = ["ExecutionStatus", "ALLOWED_EXECUTION_TRANSITIONS", "can_transition"]

