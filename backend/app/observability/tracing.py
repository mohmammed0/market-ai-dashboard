from __future__ import annotations

from uuid import uuid4


def build_trace_context(correlation_id: str | None = None) -> dict:
    trace_id = correlation_id or f"trace-{uuid4().hex[:16]}"
    return {"trace_id": trace_id, "correlation_id": correlation_id or trace_id}


__all__ = ["build_trace_context"]

