from __future__ import annotations

import logging

from backend.app.core.logging_utils import get_logger, log_event

logger = get_logger(__name__)


def emit_counter(metric_name: str, *, value: int = 1, **labels) -> dict:
    payload = {"metric_name": metric_name, "value": int(value), "labels": labels}
    log_event(logger, logging.INFO, "metrics.counter", **payload)
    return payload


__all__ = ["emit_counter"]

