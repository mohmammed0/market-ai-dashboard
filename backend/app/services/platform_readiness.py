"""Platform Readiness — Commercial-grade readiness aggregation.

Provides a single unified view answering the operator's key questions:
- Is the system healthy?
- Is execution safe?
- Is the active stack real or fallback?
- Are strategies trustworthy?
- Are workflows healthy?

Environment Modes
-----------------
The platform derives an explicit environment mode from the actual runtime
state — not from configuration alone.  This prevents local fallback mode
from being mislabeled as fully healthy commercial readiness.

Modes (deterministic, inspectable):
    local_dev_fallback   Database is SQLite OR majority of services are fallback.
                         Usable for development but not commercially trustworthy.
    local_live           Database is PostgreSQL AND core services are active.
                         Suitable for staging/local proving.
    production_ready     All subsystems active, no fallbacks, no issues.
                         Fully commercial-grade.

Grades (layered on top of mode):
    healthy              production_ready mode, no issues.
    operational          local_live mode — live services active, acceptable for staging.
    local_fallback       local_dev_fallback mode — running on fallbacks, not commercial.
    degraded             Some services unavailable or misconfigured.
    restricted           Execution halted — investigation required.
    critical             Critical subsystem failure (database down, probe errors).

No new probes or health checks are invented here.  This module aggregates
existing subsystem status calls into a structured readiness report.
"""

from __future__ import annotations

import time
from typing import Any


# ── Core subsystems that matter for commercial readiness ──────────────
# Database is always required.  These four are the live-stack services.
_LIVE_STACK_SUBSYSTEMS = {"redis", "mlflow", "prefect", "celery"}


def derive_environment_mode(
    stack_summary: dict[str, Any],
    subsystems: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive the environment mode from actual runtime stack state.

    Returns
    -------
    dict with ``mode``, ``label``, ``reason``, and ``service_states``.
    """
    # Categorize each subsystem
    service_states: dict[str, str] = {}
    for sub in subsystems:
        service_states[sub.get("name", sub.get("subsystem", "?"))] = sub.get("status", "unknown")

    active_count = stack_summary.get("active", 0)
    fallback_count = stack_summary.get("fallback", 0)
    unavailable_count = stack_summary.get("unavailable", 0)
    misconfigured_count = stack_summary.get("misconfigured", 0)
    total = stack_summary.get("total", 5)

    # Is the database a real production-grade backend?
    db_status = service_states.get("database", "unknown")
    db_is_postgresql = False
    for sub in subsystems:
        if sub.get("name", sub.get("subsystem")) == "database":
            db_is_postgresql = sub.get("mode", sub.get("configured_backend", "")) == "postgresql"
            break

    # Count live-stack services that are active
    live_services_active = sum(
        1 for name in _LIVE_STACK_SUBSYSTEMS
        if service_states.get(name) == "active"
    )
    live_services_fallback = sum(
        1 for name in _LIVE_STACK_SUBSYSTEMS
        if service_states.get(name) == "fallback"
    )

    # ── Decision rules (deterministic) ────────────────────────────────
    if active_count == total and fallback_count == 0 and unavailable_count == 0 and misconfigured_count == 0:
        mode = "production_ready"
        label = "All subsystems active — production-grade readiness"
        reason = f"All {total} subsystems verified active with no fallbacks"
    elif db_is_postgresql and live_services_active >= 2:
        mode = "local_live"
        label = "Live services active — suitable for staging and proving"
        reason = (
            f"PostgreSQL active, {live_services_active}/{len(_LIVE_STACK_SUBSYSTEMS)} "
            f"live-stack services active"
            + (f", {live_services_fallback} in fallback" if live_services_fallback else "")
        )
    else:
        mode = "local_dev_fallback"
        label = "Development fallback mode — not commercially trustworthy"
        reason = _fallback_reason(db_is_postgresql, live_services_active, live_services_fallback, fallback_count)

    return {
        "mode": mode,
        "label": label,
        "reason": reason,
        "service_states": service_states,
        "live_services_active": live_services_active,
        "live_services_total": len(_LIVE_STACK_SUBSYSTEMS),
        "db_backend": "postgresql" if db_is_postgresql else "sqlite",
    }


def _fallback_reason(db_is_pg: bool, active: int, fallback: int, total_fallback: int) -> str:
    parts: list[str] = []
    if not db_is_pg:
        parts.append("Database is SQLite (not PostgreSQL)")
    if active == 0:
        parts.append("No live-stack services active")
    elif active < 2:
        parts.append(f"Only {active} live-stack service active (need >= 2 for local_live)")
    if fallback > 0:
        parts.append(f"{fallback} live-stack services running in fallback mode")
    return "; ".join(parts) if parts else f"{total_fallback} subsystem(s) in fallback"


def compute_grade(
    env_mode: str,
    stack_summary: dict[str, Any],
    execution_halted: bool | None,
    has_probe_errors: bool,
) -> dict[str, Any]:
    """Compute the readiness grade from environment mode and runtime state.

    Grade hierarchy (highest severity wins):
        critical > restricted > degraded > local_fallback > operational > healthy

    Returns dict with ``grade``, ``grade_label``, ``upgrade_hint``.
    """
    unavailable = stack_summary.get("unavailable", 0)
    misconfigured = stack_summary.get("misconfigured", 0)

    # ── Critical: probe errors or database down ───────────────────────
    if has_probe_errors:
        return {
            "grade": "critical",
            "grade_label": "Critical subsystem failure — investigation required",
            "upgrade_hint": "Fix probe errors; ensure database is reachable",
        }

    # ── Restricted: execution halted ──────────────────────────────────
    if execution_halted:
        return {
            "grade": "restricted",
            "grade_label": "Execution halted — trading operations restricted",
            "upgrade_hint": "Clear execution halt via DELETE /api/execution/halt",
        }

    # ── Degraded: services unavailable or misconfigured ───────────────
    if unavailable > 0 or misconfigured > 0:
        return {
            "grade": "degraded",
            "grade_label": (
                f"{unavailable} unavailable, {misconfigured} misconfigured "
                f"— some capabilities impaired"
            ),
            "upgrade_hint": "Fix unavailable/misconfigured services to restore full capability",
        }

    # ── Mode-based grading (no failures, just capability level) ───────
    if env_mode == "production_ready":
        return {
            "grade": "healthy",
            "grade_label": "All systems operational — production-grade readiness",
            "upgrade_hint": None,
        }

    if env_mode == "local_live":
        return {
            "grade": "operational",
            "grade_label": "Live services active — suitable for staging and local proving",
            "upgrade_hint": "Activate remaining fallback services for full production readiness",
        }

    # local_dev_fallback
    return {
        "grade": "local_fallback",
        "grade_label": "Development fallback mode — functional but not commercially trustworthy",
        "upgrade_hint": (
            "Start live services (docker compose -f docker-compose.services.yml up -d), "
            "switch to PostgreSQL, and activate .env.local-live"
        ),
    }


def get_platform_readiness() -> dict[str, Any]:
    """Aggregate readiness across all platform dimensions.

    Returns a structured report with:
    - ``environment_mode``: derived runtime mode (local_dev_fallback / local_live / production_ready)
    - ``grade``: overall readiness grade
    - ``grade_label``: human-readable grade description
    - ``issues``: list of active problems
    - ``dimensions``: per-area readiness details
    """
    t0 = time.time()
    issues: list[str] = []
    dimensions: dict[str, Any] = {}
    has_probe_errors = False

    # ── 1. Stack Health ────────────────────────────────────���──────────
    try:
        from backend.app.services.stack_validator import validate_stack  # noqa: PLC0415
        stack = validate_stack()
        summary = stack["summary"]

        subsystem_list = []
        for s in stack.get("subsystems", []):
            entry = {
                "name": s["subsystem"],
                "status": s.get("status"),
                "mode": s.get("mode", s.get("configured_backend")),
                "verified": s.get("verified", False),
            }
            if s.get("latency_ms"):
                entry["latency_ms"] = s["latency_ms"]
            if s.get("reason"):
                entry["reason"] = s["reason"]
            subsystem_list.append(entry)

        dimensions["stack"] = {
            "active": summary["active"],
            "fallback": summary["fallback"],
            "unavailable": summary["unavailable"],
            "misconfigured": summary["misconfigured"],
            "subsystems": subsystem_list,
        }

        if summary["unavailable"] > 0:
            issues.append(f"{summary['unavailable']} subsystem(s) unavailable")
        if summary["misconfigured"] > 0:
            issues.append(f"{summary['misconfigured']} subsystem(s) misconfigured")
        if summary["fallback"] > 0:
            issues.append(
                f"{summary['fallback']} subsystem(s) running in fallback mode"
            )
    except Exception as e:
        dimensions["stack"] = {"status": "error", "error": str(e)[:100]}
        issues.append("Stack validation failed")
        summary = {"active": 0, "fallback": 0, "unavailable": 0, "misconfigured": 0, "total": 5}
        subsystem_list = []
        has_probe_errors = True

    # ── 2. Execution Safety ───────────────────────────────────────────
    execution_halted: bool | None = None
    try:
        from backend.app.services.execution_halt import get_halt_status  # noqa: PLC0415
        halt = get_halt_status()
        execution_halted = bool(halt.get("halted"))

        from backend.app.services.runtime_control import get_runtime_control_plane  # noqa: PLC0415
        control = get_runtime_control_plane()
        broker = control.get("broker_runtime", {})

        dimensions["execution"] = {
            "status": "halted" if execution_halted else "safe",
            "halted": execution_halted,
            "halt_reason": halt.get("reason") if execution_halted else None,
            "broker_mode": broker.get("effective_mode", "unknown"),
            "order_submission_enabled": broker.get("order_submission_enabled", False),
            "live_execution_enabled": broker.get("live_execution_enabled", False),
        }
        if execution_halted:
            issues.append(f"Execution halted: {halt.get('reason', 'unknown')}")
    except Exception as e:
        dimensions["execution"] = {"status": "error", "error": str(e)[:100]}
        issues.append("Execution safety check failed")
        has_probe_errors = True

    # ── 3. Strategy Trustworthiness ───────────────────────────────────
    try:
        from backend.app.services.strategy_readiness import get_readiness_summary  # noqa: PLC0415
        readiness = get_readiness_summary(limit=10)
        sr_summary = readiness.get("summary", {})
        total_eval = readiness.get("total", 0)
        dimensions["strategies"] = {
            "status": "assessed" if total_eval > 0 else "no_evaluations",
            "total_evaluated": total_eval,
            "review_ready": sr_summary.get("review_ready", 0),
            "candidate": sr_summary.get("candidate", 0),
            "exploratory": sr_summary.get("exploratory", 0),
            "rejected": sr_summary.get("rejected", 0),
        }
    except Exception as e:
        dimensions["strategies"] = {"status": "error", "error": str(e)[:100]}

    # ── 4. Orchestration / Workflow Health ─────────────────────────────
    try:
        from backend.app.services.orchestration_gateway import get_orchestration_status  # noqa: PLC0415
        orch = get_orchestration_status()
        orch_summary = orch.get("summary", {})
        dimensions["orchestration"] = {
            "status": "healthy",
            "heavy_workflows": orch_summary.get("heavy_workflows", "unknown"),
            "recurring_tasks": orch_summary.get("recurring_tasks", "unknown"),
            "experiment_tracking": orch_summary.get("experiment_tracking", "unknown"),
            "scheduler": orch_summary.get("scheduler", "unknown"),
        }
    except Exception as e:
        dimensions["orchestration"] = {"status": "error", "error": str(e)[:100]}
        issues.append("Orchestration health check failed")

    # ── 5. Cache Status ───────────────────────────────────────────────
    try:
        from backend.app.services.cache import get_cache_status  # noqa: PLC0415
        cache = get_cache_status()
        dimensions["cache"] = {
            "status": "active" if cache.get("ready") else "fallback",
            "provider": cache.get("provider", "unknown"),
        }
    except Exception as e:
        dimensions["cache"] = {"status": "error", "error": str(e)[:100]}

    # ── Derive environment mode + grade ───────────────────────────────
    env_mode = derive_environment_mode(summary, subsystem_list)
    grade_info = compute_grade(
        env_mode=env_mode["mode"],
        stack_summary=summary,
        execution_halted=execution_halted,
        has_probe_errors=has_probe_errors,
    )

    return {
        "environment_mode": env_mode,
        "grade": grade_info["grade"],
        "grade_label": grade_info["grade_label"],
        "upgrade_hint": grade_info.get("upgrade_hint"),
        "issues": issues,
        "dimensions": dimensions,
        "assessed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assessment_ms": round((time.time() - t0) * 1000, 1),
    }
