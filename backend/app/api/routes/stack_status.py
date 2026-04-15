"""Stack Status API — Operator visibility into live vs fallback state.

GET /api/stack         — Full stack validation report
GET /api/stack/summary — Compact one-line-per-subsystem summary
GET /api/stack/llm     — Local LLM provider status
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.services.stack_validator import validate_stack
from backend.app.services.llm_gateway import get_llm_status

router = APIRouter(prefix="/stack", tags=["stack"])


@router.get("")
def get_stack_status():
    """Full stack validation with connectivity probes.

    Returns a structured report showing each subsystem's live state:
    - active: service is configured and reachable
    - fallback: service not configured, using safe local alternative
    - unavailable: service configured but not reachable
    - misconfigured: service configured but missing dependencies
    """
    return validate_stack()


@router.get("/summary")
def get_stack_summary():
    """Compact stack summary for dashboards and monitoring.

    Returns one line per subsystem with status and active mode.
    """
    report = validate_stack()
    lines = []
    for sub in report["subsystems"]:
        lines.append({
            "subsystem": sub["subsystem"],
            "status": sub.get("status", "unknown"),
            "mode": sub.get("mode", sub.get("configured_backend", "-")),
            "verified": sub.get("verified", False),
            "latency_ms": sub.get("latency_ms"),
        })
    return {
        "items": lines,
        "summary": report["summary"],
        "validated_at": report["validated_at"],
    }


@router.get("/llm")
def get_llm_status_endpoint():
    """LLM provider availability status.

    Returns configuration and runtime status of the local AI runtime,
    plus the active provider determined by AI_PROVIDER config.
    """
    return get_llm_status()
