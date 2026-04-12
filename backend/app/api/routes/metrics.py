"""Observability / metrics endpoints.

GET  /api/metrics          - Prometheus text-format metrics scrape endpoint
GET  /api/metrics/summary  - JSON metrics summary (human-readable)
GET  /api/metrics/tools    - Tool gateway usage and recent call log
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from backend.app.services.observability import get_metrics_summary, prometheus_text_export
from backend.app.services.tool_gateway import get_tool_gateway

router = APIRouter(prefix="/metrics", tags=["observability"])


@router.get("", response_class=PlainTextResponse, include_in_schema=True)
def metrics_prometheus():
    """Prometheus text-format metrics scrape endpoint.

    Add ``http://host:8000/api/metrics`` as a scrape target in
    ``prometheus.yml`` to collect these metrics.
    """
    return prometheus_text_export()


@router.get("/summary")
def metrics_summary():
    """JSON metrics summary for the operations dashboard."""
    return {
        "metrics": get_metrics_summary(),
    }


@router.get("/tools")
def tool_gateway_status():
    """Tool gateway call counters and recent audit log."""
    gw = get_tool_gateway()
    return {
        "registered_tools": gw.list_tools(),
        "call_counters": gw.get_counters(),
        "recent_calls": gw.get_audit_log(limit=20),
    }
