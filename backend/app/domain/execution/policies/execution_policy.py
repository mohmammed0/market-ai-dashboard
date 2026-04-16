from __future__ import annotations

from pydantic import BaseModel


class ExecutionPolicy(BaseModel):
    allow_short_selling: bool = False
    require_risk_approval: bool = True
    require_idempotency_key: bool = True


DEFAULT_EXECUTION_POLICY = ExecutionPolicy()

__all__ = ["DEFAULT_EXECUTION_POLICY", "ExecutionPolicy"]

