from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from backend.app.services.broker.registry import get_market_session_status as get_broker_market_session_status

_ET = ZoneInfo("America/New_York")

_CANONICAL_SESSION_ALIASES = {
    "": "fully_closed",
    "closed": "fully_closed",
    "fully_closed": "fully_closed",
    "weekend": "fully_closed",
    "holiday": "fully_closed",
    "pre_open_preparation": "preopen_preparation",
    "preopen_preparation": "preopen_preparation",
    "pre_market_live_session": "premarket_live",
    "pre_market_live": "premarket_live",
    "premarket_live": "premarket_live",
    "premarket": "premarket_live",
    "opening_auction_window": "opening_handoff_window",
    "opening_handoff_window": "opening_handoff_window",
    "opening_handoff": "opening_handoff_window",
    "regular": "regular_session",
    "regular_market": "regular_session",
    "regular_session": "regular_session",
    "market_open": "regular_session",
    "after_hours": "after_hours",
    "afterhours": "after_hours",
    "overnight": "overnight_if_supported",
    "overnight_if_supported": "overnight_if_supported",
}

_LEGACY_SESSION_ALIASES = {
    "fully_closed": "fully_closed",
    "preopen_preparation": "pre_open_preparation",
    "premarket_live": "pre_market_live_session",
    "opening_handoff_window": "opening_auction_window",
    "regular_session": "regular_session",
    "after_hours": "after_hours",
    "overnight_if_supported": "overnight_if_supported",
}


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    return text not in {"0", "false", "no", "off"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _parse_dt(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_session_state(value: Any, default: str = "fully_closed") -> str:
    normalized = str(value or "").strip().lower()
    return _CANONICAL_SESSION_ALIASES.get(normalized, default)


def legacy_session_state(value: Any, default: str = "fully_closed") -> str:
    canonical = normalize_session_state(value, default=normalize_session_state(default))
    return _LEGACY_SESSION_ALIASES.get(canonical, canonical)


def session_matches(value: Any, *states: str) -> bool:
    normalized = normalize_session_state(value)
    targets = {normalize_session_state(state) for state in states if str(state or "").strip()}
    return normalized in targets


def _session_code_from_clock(now_et: datetime, market_open: bool) -> str:
    hhmm = now_et.hour * 100 + now_et.minute
    if market_open:
        if 930 <= hhmm < 935:
            return "opening_handoff_window"
        return "regular_session"
    if now_et.weekday() >= 5:
        return "fully_closed"
    if 0 <= hhmm < 400:
        return "preopen_preparation"
    if 400 <= hhmm < 925:
        return "premarket_live"
    if 925 <= hhmm < 930:
        return "opening_handoff_window"
    if 1600 <= hhmm < 2000:
        return "after_hours"
    if hhmm >= 2000:
        return "overnight_if_supported"
    return "fully_closed"


def _readiness_phase(minutes_to_open: float | None, market_open: bool, session_state: str) -> str:
    if session_matches(session_state, "opening_handoff_window"):
        return "open_handoff"
    if market_open:
        return "market_live"
    if session_matches(session_state, "after_hours"):
        return "post_close_review"
    if session_matches(session_state, "premarket_live"):
        if minutes_to_open is not None and minutes_to_open <= 1:
            return "t_minus_1"
        if minutes_to_open is not None and minutes_to_open <= 5:
            return "t_minus_5"
        if minutes_to_open is not None and minutes_to_open <= 15:
            return "t_minus_15"
        return "premarket_live"
    if minutes_to_open is None:
        return "standby"
    if minutes_to_open <= 1:
        return "t_minus_1"
    if minutes_to_open <= 5:
        return "t_minus_5"
    if minutes_to_open <= 15:
        return "t_minus_15"
    if minutes_to_open <= 30:
        return "t_minus_30"
    if minutes_to_open <= 60:
        return "t_minus_60"
    if minutes_to_open <= 90:
        return "t_minus_90"
    return "standby"


def _build_snapshot(*, now_utc: datetime, broker_payload: dict, session_state: str, market_open: bool, next_open: datetime | None, next_close: datetime | None, source: str, notes: list[str], is_trading_day: bool, is_early_close: bool) -> dict:
    minutes_to_open = None if market_open or next_open is None else max((next_open - now_utc).total_seconds() / 60.0, 0.0)
    minutes_to_close = max((next_close - now_utc).total_seconds() / 60.0, 0.0) if market_open and next_close is not None else None
    extended_hours_capable = _safe_bool(broker_payload.get("extended_hours_available"), True)
    after_hours_capable = _safe_bool(broker_payload.get("after_hours_available"), True)
    extended_hours_window_open = session_matches(session_state, "premarket_live", "after_hours", "overnight_if_supported")
    extended_hours_available = bool(extended_hours_capable and extended_hours_window_open and is_trading_day)
    after_hours_available = bool(after_hours_capable and session_matches(session_state, "after_hours") and is_trading_day)
    opening_handoff_window = bool(session_matches(session_state, "opening_handoff_window"))

    if market_open:
        session_quality = "good" if not opening_handoff_window else "normal"
    elif session_matches(session_state, "premarket_live", "after_hours"):
        session_quality = "poor"
    else:
        session_quality = "closed"

    readiness_phase = _readiness_phase(minutes_to_open, market_open, session_state)
    transition_at = next_close if market_open else next_open

    payload_notes = list(notes)
    if opening_handoff_window:
        payload_notes.append("opening_handoff_active")
    if extended_hours_available:
        payload_notes.append("extended_hours_window_open")

    return {
        "session_state": session_state,
        "session_code": session_state,
        "session_state_legacy": legacy_session_state(session_state),
        "session_code_legacy": legacy_session_state(session_state),
        "market_open": market_open,
        "is_trading_day": bool(is_trading_day),
        "is_early_close": bool(is_early_close),
        "next_open_at": next_open.isoformat() if next_open else None,
        "next_close_at": next_close.isoformat() if next_close else None,
        "minutes_to_open": round(_safe_float(minutes_to_open, 0.0), 2) if minutes_to_open is not None else None,
        "minutes_to_close": round(_safe_float(minutes_to_close, 0.0), 2) if minutes_to_close is not None else None,
        "extended_hours_available": bool(extended_hours_available),
        "extended_hours_order_placement_allowed": bool(extended_hours_available),
        "opening_handoff_window": opening_handoff_window,
        "opening_auction_window": opening_handoff_window,
        "opening_order_planning_allowed": bool(is_trading_day and not market_open),
        "after_hours_available": bool(after_hours_available),
        "session_quality": session_quality,
        "session_notes": payload_notes,
        "readiness_phase": readiness_phase,
        "readiness_window_active": readiness_phase in {"t_minus_90", "t_minus_60", "t_minus_30", "t_minus_15", "t_minus_5", "t_minus_1", "open_handoff", "premarket_live"},
        "session_transition_at": transition_at.isoformat() if transition_at else None,
        "source": source,
        "broker_session": broker_payload,
        "generated_at": now_utc.isoformat(),
    }


def _fallback_snapshot() -> dict:
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(_ET)
    market_open = bool(now_et.weekday() < 5 and (now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30)) and now_et.hour < 16)
    session_state = _session_code_from_clock(now_et, market_open)

    open_et = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if now_et.weekday() >= 5:
        days_ahead = (7 - now_et.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 1
        open_et = open_et + timedelta(days=days_ahead)
        close_et = close_et + timedelta(days=days_ahead)
    elif now_et > close_et:
        open_et = open_et + timedelta(days=1)
        close_et = close_et + timedelta(days=1)

    return _build_snapshot(
        now_utc=now_utc,
        broker_payload={},
        session_state=session_state,
        market_open=market_open,
        next_open=open_et.astimezone(timezone.utc),
        next_close=close_et.astimezone(timezone.utc),
        source="fallback",
        notes=["fallback_calendar"],
        is_trading_day=now_et.weekday() < 5,
        is_early_close=False,
    )


def get_market_session_snapshot(*, refresh: bool = False) -> dict:
    broker_payload = get_broker_market_session_status(refresh=refresh)
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(_ET)

    if not isinstance(broker_payload, dict) or not broker_payload:
        return _fallback_snapshot()

    market_open = _safe_bool(broker_payload.get("market_open"), False)
    next_open = _parse_dt(broker_payload.get("next_open_at"))
    next_close = _parse_dt(broker_payload.get("next_close_at"))
    clock_ts = _parse_dt(broker_payload.get("clock_timestamp") or broker_payload.get("clock_at")) or now_utc
    clock_et = clock_ts.astimezone(_ET)

    if next_open is None:
        open_et = clock_et.replace(hour=9, minute=30, second=0, microsecond=0)
        if clock_et.weekday() >= 5 or clock_et > open_et:
            open_et = open_et + timedelta(days=1)
        next_open = open_et.astimezone(timezone.utc)
    if next_close is None:
        close_et = clock_et.replace(hour=16, minute=0, second=0, microsecond=0)
        if clock_et.weekday() >= 5 or clock_et > close_et:
            close_et = close_et + timedelta(days=1)
        next_close = close_et.astimezone(timezone.utc)

    broker_session_code = str(broker_payload.get("session_code") or broker_payload.get("session_state") or "").strip().lower()
    inferred_session_code = _session_code_from_clock(clock_et, market_open)
    canonical_broker_state = normalize_session_state(broker_session_code)

    if broker_session_code in {"", "fully_closed", "closed", "regular_session", "regular_market"}:
        session_state = inferred_session_code if not market_open else ("opening_handoff_window" if inferred_session_code == "opening_handoff_window" else "regular_session")
    else:
        session_state = canonical_broker_state

    calendar_is_trading_day = clock_et.weekday() < 5
    is_trading_day = _safe_bool(broker_payload.get("is_trading_day"), calendar_is_trading_day)
    if not calendar_is_trading_day:
        is_trading_day = False
        if not market_open:
            session_state = "fully_closed"

    notes = broker_payload.get("session_notes") if isinstance(broker_payload.get("session_notes"), list) else []
    if broker_session_code and canonical_broker_state != session_state:
        notes = [*notes, f"broker_session_normalized:{canonical_broker_state}"]

    return _build_snapshot(
        now_utc=now_utc,
        broker_payload=broker_payload,
        session_state=session_state,
        market_open=market_open,
        next_open=next_open,
        next_close=next_close,
        source=str(broker_payload.get("source") or broker_payload.get("provider") or "broker_clock"),
        notes=notes,
        is_trading_day=bool(is_trading_day),
        is_early_close=_safe_bool(broker_payload.get("is_early_close"), False),
    )
