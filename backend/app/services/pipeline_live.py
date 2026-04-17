from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from backend.app.services import get_cache


PIPELINE_LIVE_STATE_KEY = "pipeline:live:state"
PIPELINE_LIVE_TTL_SECONDS = 60 * 60 * 24
PIPELINE_MAX_EVENTS = 200
PIPELINE_MAX_RECENT_CYCLES = 32


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _empty_state() -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "updated_at": now,
        "events": [],
        "active_cycles": {},
        "recent_cycles": [],
        "stats": {
            "total_cycles": 0,
            "completed_cycles": 0,
            "failed_cycles": 0,
            "last_cycle_component": None,
            "last_cycle_status": None,
        },
    }


def _load_state() -> dict[str, Any]:
    raw = get_cache().get(PIPELINE_LIVE_STATE_KEY)
    if not isinstance(raw, dict):
        return _empty_state()
    state = dict(raw)
    if not isinstance(state.get("events"), list):
        state["events"] = []
    if not isinstance(state.get("active_cycles"), dict):
        state["active_cycles"] = {}
    if not isinstance(state.get("recent_cycles"), list):
        state["recent_cycles"] = []
    if not isinstance(state.get("stats"), dict):
        state["stats"] = _empty_state()["stats"]
    state.setdefault("updated_at", _utc_now_iso())
    return state


def _save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = _utc_now_iso()
    get_cache().set(PIPELINE_LIVE_STATE_KEY, state, ttl_seconds=PIPELINE_LIVE_TTL_SECONDS)


def _append_event(
    state: dict[str, Any],
    *,
    component: str,
    stage: str,
    message: str,
    level: str = "info",
    cycle_id: str | None = None,
    symbol: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "id": uuid4().hex[:12],
        "at": _utc_now_iso(),
        "epoch": time.time(),
        "level": str(level or "info").strip().lower(),
        "component": str(component or "pipeline").strip().lower() or "pipeline",
        "stage": str(stage or "update").strip().lower() or "update",
        "message": str(message or "").strip() or "pipeline update",
        "cycle_id": str(cycle_id or "").strip() or None,
        "symbol": str(symbol or "").strip().upper() or None,
        "details": details if isinstance(details, dict) else None,
    }
    state["events"].insert(0, event)
    if len(state["events"]) > PIPELINE_MAX_EVENTS:
        state["events"] = state["events"][:PIPELINE_MAX_EVENTS]
    return event


def start_cycle(
    component: str,
    *,
    symbols: list[str] | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> str:
    state = _load_state()
    cycle_id = uuid4().hex[:12]
    prepared_symbols = [str(value or "").strip().upper() for value in (symbols or []) if str(value or "").strip()]
    now_epoch = time.time()
    cycle = {
        "id": cycle_id,
        "component": str(component or "pipeline").strip().lower() or "pipeline",
        "status": "running",
        "started_at": _utc_now_iso(),
        "started_epoch": now_epoch,
        "updated_at": _utc_now_iso(),
        "updated_epoch": now_epoch,
        "completed_at": None,
        "completed_epoch": None,
        "symbols": prepared_symbols,
        "symbol_count": len(prepared_symbols),
        "processed_count": 0,
        "failed_count": 0,
        "stage": "start",
        "summary": None,
        "details": details if isinstance(details, dict) else None,
    }
    state["active_cycles"][cycle_id] = cycle
    _append_event(
        state,
        component=cycle["component"],
        stage="start",
        message=message or f"بدأت دورة {cycle['component']}",
        level="info",
        cycle_id=cycle_id,
        details=details,
    )
    _save_state(state)
    return cycle_id


def log_cycle_stage(
    cycle_id: str,
    *,
    stage: str,
    message: str,
    level: str = "info",
    symbol: str | None = None,
    details: dict[str, Any] | None = None,
    processed_count: int | None = None,
    failed_count: int | None = None,
) -> None:
    state = _load_state()
    cycle = state["active_cycles"].get(cycle_id)
    component = "pipeline"
    if isinstance(cycle, dict):
        component = str(cycle.get("component") or component)
        cycle["stage"] = str(stage or "update").strip().lower() or "update"
        cycle["updated_at"] = _utc_now_iso()
        cycle["updated_epoch"] = time.time()
        if processed_count is not None:
            cycle["processed_count"] = max(0, int(processed_count))
        if failed_count is not None:
            cycle["failed_count"] = max(0, int(failed_count))
        if isinstance(details, dict):
            cycle["details"] = {**(cycle.get("details") or {}), **details}
    _append_event(
        state,
        component=component,
        stage=stage,
        message=message,
        level=level,
        cycle_id=cycle_id,
        symbol=symbol,
        details=details,
    )
    _save_state(state)


def complete_cycle(
    cycle_id: str,
    *,
    status: str = "completed",
    message: str | None = None,
    summary: dict[str, Any] | None = None,
) -> None:
    state = _load_state()
    cycle = state["active_cycles"].pop(cycle_id, None)
    now_epoch = time.time()
    normalized_status = str(status or "completed").strip().lower() or "completed"
    if not isinstance(cycle, dict):
        cycle = {
            "id": cycle_id,
            "component": "pipeline",
            "status": normalized_status,
            "started_at": None,
            "started_epoch": None,
            "updated_at": _utc_now_iso(),
            "updated_epoch": now_epoch,
            "completed_at": _utc_now_iso(),
            "completed_epoch": now_epoch,
            "symbols": [],
            "symbol_count": 0,
            "processed_count": 0,
            "failed_count": 0,
            "stage": normalized_status,
            "summary": summary if isinstance(summary, dict) else None,
            "details": None,
        }
    else:
        cycle["status"] = normalized_status
        cycle["stage"] = normalized_status
        cycle["completed_at"] = _utc_now_iso()
        cycle["completed_epoch"] = now_epoch
        cycle["updated_at"] = cycle["completed_at"]
        cycle["updated_epoch"] = now_epoch
        cycle["summary"] = summary if isinstance(summary, dict) else cycle.get("summary")

    started_epoch = cycle.get("started_epoch")
    if isinstance(started_epoch, (int, float)):
        cycle["elapsed_seconds"] = round(max(0.0, now_epoch - float(started_epoch)), 3)
    else:
        cycle["elapsed_seconds"] = None

    state["recent_cycles"].insert(0, cycle)
    if len(state["recent_cycles"]) > PIPELINE_MAX_RECENT_CYCLES:
        state["recent_cycles"] = state["recent_cycles"][:PIPELINE_MAX_RECENT_CYCLES]

    stats = state["stats"]
    stats["total_cycles"] = int(stats.get("total_cycles") or 0) + 1
    if normalized_status == "completed":
        stats["completed_cycles"] = int(stats.get("completed_cycles") or 0) + 1
    else:
        stats["failed_cycles"] = int(stats.get("failed_cycles") or 0) + 1
    stats["last_cycle_component"] = cycle.get("component")
    stats["last_cycle_status"] = normalized_status

    _append_event(
        state,
        component=str(cycle.get("component") or "pipeline"),
        stage=normalized_status,
        message=message or f"انتهت دورة {cycle.get('component') or 'pipeline'} بحالة {normalized_status}",
        level="error" if normalized_status not in {"completed", "ok", "success"} else "info",
        cycle_id=cycle_id,
        details=summary,
    )
    _save_state(state)


def record_event(
    component: str,
    *,
    stage: str,
    message: str,
    level: str = "info",
    symbol: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    state = _load_state()
    _append_event(
        state,
        component=component,
        stage=stage,
        message=message,
        level=level,
        symbol=symbol,
        details=details,
    )
    _save_state(state)


def get_pipeline_feed(*, limit_events: int = 40, limit_cycles: int = 8) -> dict[str, Any]:
    state = _load_state()
    now_epoch = time.time()
    active_cycles = []
    for cycle in state.get("active_cycles", {}).values():
        if not isinstance(cycle, dict):
            continue
        payload = dict(cycle)
        started_epoch = payload.get("started_epoch")
        if isinstance(started_epoch, (int, float)):
            payload["elapsed_seconds"] = round(max(0.0, now_epoch - float(started_epoch)), 3)
        else:
            payload["elapsed_seconds"] = None
        active_cycles.append(payload)

    active_cycles.sort(key=lambda item: float(item.get("started_epoch") or 0.0), reverse=True)
    events = [event for event in state.get("events", []) if isinstance(event, dict)][: max(1, int(limit_events or 1))]
    recent_cycles = [cycle for cycle in state.get("recent_cycles", []) if isinstance(cycle, dict)][: max(1, int(limit_cycles or 1))]

    return {
        "updated_at": state.get("updated_at"),
        "active_cycles": active_cycles,
        "recent_cycles": recent_cycles,
        "events": events,
        "stats": state.get("stats", {}),
    }
