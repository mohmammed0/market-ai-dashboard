"""Execution halt (kill switch) service.

Stores a single persistent flag in the ``runtime_settings`` table under the key
``execution.halt_enabled``.  No new table or migration is required — the table
was created in migration 20260407_0003_runtime_settings.

Public interface
----------------
- ``is_halted() -> bool``          — fast gate check; call before any execution
- ``enable_halt(reason, by)``      — set the kill switch
- ``disable_halt(by)``             — clear the kill switch
- ``get_halt_status() -> dict``    — structured status for the API response
"""

from __future__ import annotations

import logging
from datetime import datetime

from backend.app.core.logging_utils import get_logger, log_event
from backend.app.models.runtime_settings import RuntimeSetting
from backend.app.services.storage import session_scope

logger = get_logger(__name__)

_HALT_KEY = "execution.halt_enabled"
_HALT_REASON_KEY = "execution.halt_reason"
_HALT_BY_KEY = "execution.halt_enabled_by"
_HALT_AT_KEY = "execution.halt_enabled_at"


def _read_setting(session, key: str) -> str | None:
    row = session.query(RuntimeSetting).filter(RuntimeSetting.key == key).first()
    return None if row is None else row.value_text


def _write_setting(session, key: str, value: str) -> None:
    row = session.query(RuntimeSetting).filter(RuntimeSetting.key == key).first()
    if row is None:
        session.add(RuntimeSetting(key=key, value_text=value, is_secret=False))
    else:
        row.value_text = value
        row.updated_at = datetime.utcnow()
    session.flush()


def is_halted() -> bool:
    """Return True if the execution kill switch is currently active."""
    with session_scope() as session:
        return _read_setting(session, _HALT_KEY) == "true"


def enable_halt(reason: str = "", enabled_by: str = "api") -> dict:
    """Activate the kill switch.  All new execution attempts will be blocked."""
    now_iso = datetime.utcnow().isoformat()
    with session_scope() as session:
        _write_setting(session, _HALT_KEY, "true")
        _write_setting(session, _HALT_REASON_KEY, reason or "")
        _write_setting(session, _HALT_BY_KEY, enabled_by)
        _write_setting(session, _HALT_AT_KEY, now_iso)
    log_event(logger, logging.WARNING, "execution.halt.enabled", reason=reason, enabled_by=enabled_by)
    return get_halt_status()


def disable_halt(disabled_by: str = "api") -> dict:
    """Clear the kill switch.  Execution is permitted again."""
    with session_scope() as session:
        _write_setting(session, _HALT_KEY, "false")
    log_event(logger, logging.INFO, "execution.halt.disabled", disabled_by=disabled_by)
    return get_halt_status()


def get_halt_status() -> dict:
    """Return the current halt state as a structured dict suitable for API responses."""
    with session_scope() as session:
        halted = _read_setting(session, _HALT_KEY) == "true"
        reason = _read_setting(session, _HALT_REASON_KEY) or ""
        enabled_by = _read_setting(session, _HALT_BY_KEY) or ""
        enabled_at = _read_setting(session, _HALT_AT_KEY) or ""
    return {
        "halted": halted,
        "reason": reason,
        "enabled_by": enabled_by,
        "enabled_at": enabled_at,
    }
