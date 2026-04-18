from __future__ import annotations

from datetime import UTC, datetime
import threading
from typing import Any

from backend.app.core.logging_utils import get_logger, log_event
from backend.app.models.market_data import QuoteSnapshot
from backend.app.services.storage import dumps_json, session_scope
from core.live_service import create_live_engine

logger = get_logger(__name__)

_ENGINE_LOCK = threading.Lock()
_ENGINE = None
_ENGINE_SYMBOLS: set[str] = set()
_LAST_QUOTES: dict[str, dict[str, Any]] = {}
_LAST_ERRORS: list[dict[str, Any]] = []
_LAST_STATUS: dict[str, Any] = {
    "running": False,
    "mode": "inactive",
    "symbols": [],
    "connected": False,
    "last_event_at": None,
    "last_error": None,
}


def _normalized_symbols(symbols: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in symbols or []:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        normalized.append(symbol)
        seen.add(symbol)
    return normalized


def _engine_mode(engine: Any) -> str:
    explicit_mode = str(getattr(engine, "provider_mode", "") or "").strip().lower()
    if explicit_mode:
        return explicit_mode
    return "alpaca_stream" if getattr(engine, "api_key", None) and getattr(engine, "api_secret", None) else "polling"


def _replace_engine(symbols: list[str], poll_interval: int = 3) -> None:
    global _ENGINE, _ENGINE_SYMBOLS

    if _ENGINE is not None:
        try:
            _ENGINE.stop()
        except Exception:
            logger.debug("live_stream previous engine stop failed", exc_info=True)

    _ENGINE = create_live_engine()
    _ENGINE.symbols = symbols
    _ENGINE.poll_interval = max(1, int(poll_interval or 3))
    _ENGINE.start()
    _ENGINE_SYMBOLS = set(symbols)
    _LAST_STATUS.update(
        {
            "running": True,
            "mode": _engine_mode(_ENGINE),
            "symbols": symbols,
            "connected": False,
            "last_error": None,
        }
    )
    engine_reason = str(getattr(_ENGINE, "reason", "") or "").strip()
    if engine_reason:
        _LAST_STATUS["last_error"] = {
            "message": engine_reason,
            "captured_at": datetime.now(UTC).isoformat(),
        }
    log_event(logger, 20, "live_stream.engine_started", symbols=symbols, mode=_LAST_STATUS["mode"])


def ensure_live_stream(symbols: list[str] | None = None, *, poll_interval: int = 3) -> dict[str, Any]:
    normalized = _normalized_symbols(symbols) or list(_ENGINE_SYMBOLS) or ["AAPL", "MSFT", "NVDA", "SPY"]
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _replace_engine(normalized, poll_interval=poll_interval)
        else:
            requested = set(normalized)
            if not requested.issubset(_ENGINE_SYMBOLS):
                merged = sorted(_ENGINE_SYMBOLS | requested)
                _replace_engine(merged, poll_interval=poll_interval)
    return get_live_stream_status()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _normalize_quote_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(payload.get("symbol") or payload.get("S") or "").strip().upper()
    if not symbol:
        return None

    price = _safe_float(payload.get("price"))
    if price is None and event_type == "trade":
        price = _safe_float(payload.get("p"))
    if price is None and event_type == "quote":
        bid_price = _safe_float(payload.get("bp"))
        ask_price = _safe_float(payload.get("ap"))
        if bid_price is not None and ask_price is not None:
            price = round((bid_price + ask_price) / 2.0, 6)
        else:
            price = ask_price if ask_price is not None else bid_price
    if price is None and event_type == "bar":
        price = _safe_float(payload.get("close") or payload.get("c"))

    prev_close = _safe_float(payload.get("prev_close"))
    change = _safe_float(payload.get("change"))
    change_pct = _safe_float(payload.get("change_pct"))
    volume = _safe_float(payload.get("volume") or payload.get("v") or payload.get("size") or payload.get("s"))
    source = str(payload.get("source") or payload.get("T") or "live_stream").strip() or "live_stream"

    if price is not None and prev_close not in {None, 0.0} and change is None:
        change = price - float(prev_close)
    if price is not None and prev_close not in {None, 0.0} and change_pct is None:
        change_pct = ((price / float(prev_close)) - 1.0) * 100.0

    return {
        "symbol": symbol,
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "volume": volume,
        "source": source,
        "captured_at": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "payload": payload,
    }


def _persist_quote_snapshot(snapshot: dict[str, Any]) -> None:
    price = _safe_float(snapshot.get("price"))
    if price is None:
        return
    with session_scope() as session:
        session.add(
            QuoteSnapshot(
                symbol=str(snapshot.get("symbol") or "").strip().upper(),
                price=price,
                prev_close=_safe_float(snapshot.get("prev_close")),
                change=_safe_float(snapshot.get("change")),
                change_pct=_safe_float(snapshot.get("change_pct")),
                volume=_safe_float(snapshot.get("volume")),
                source=str(snapshot.get("source") or "live_stream")[:50],
                payload_json=dumps_json(snapshot),
            )
        )


def drain_live_stream_events(*, max_events: int = 250) -> dict[str, Any]:
    processed = 0
    persisted = 0
    with _ENGINE_LOCK:
        engine = _ENGINE
    if engine is None:
        return {"processed": 0, "persisted": 0}
    _LAST_STATUS["mode"] = _engine_mode(engine)

    while processed < max(1, int(max_events)):
        event = engine.get_event(timeout=0.0)
        if event is None:
            break
        processed += 1
        event_type = str(event.get("type") or "message").strip().lower()
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        _LAST_STATUS["last_event_at"] = datetime.now(UTC).isoformat()

        if event_type in {"quote", "trade", "bar"}:
            normalized = _normalize_quote_event(event_type, payload)
            if normalized is None:
                continue
            _LAST_QUOTES[normalized["symbol"]] = normalized
            _persist_quote_snapshot(normalized)
            persisted += 1
            continue

        if event_type in {"status", "subscription"}:
            _LAST_STATUS["mode"] = _engine_mode(engine)
            _LAST_STATUS["connected"] = True
            _LAST_STATUS["detail"] = payload
            _LAST_STATUS["last_error"] = None
            continue

        if event_type == "error":
            error_payload = {
                "message": str(payload.get("message") or payload.get("msg") or "Live stream error."),
                "captured_at": datetime.now(UTC).isoformat(),
                "payload": payload,
            }
            _LAST_ERRORS.append(error_payload)
            _LAST_ERRORS[:] = _LAST_ERRORS[-10:]
            _LAST_STATUS["last_error"] = error_payload
            _LAST_STATUS["connected"] = False

    return {"processed": processed, "persisted": persisted}


def get_live_stream_status() -> dict[str, Any]:
    with _ENGINE_LOCK:
        engine = _ENGINE
    return {
        "running": bool(_LAST_STATUS.get("running")),
        "mode": _engine_mode(engine) if engine is not None else (_LAST_STATUS.get("mode") or "inactive"),
        "symbols": list(_LAST_STATUS.get("symbols") or []),
        "connected": bool(_LAST_STATUS.get("connected")),
        "last_event_at": _LAST_STATUS.get("last_event_at"),
        "last_error": _LAST_STATUS.get("last_error"),
    }


def get_live_stream_snapshot(
    symbols: list[str] | None = None,
    *,
    poll_interval: int = 3,
    max_events: int = 250,
) -> dict[str, Any]:
    requested_symbols = _normalized_symbols(symbols)
    ensure_live_stream(requested_symbols, poll_interval=poll_interval)
    drain_stats = drain_live_stream_events(max_events=max_events)
    if requested_symbols:
        items = [_LAST_QUOTES[symbol] for symbol in requested_symbols if symbol in _LAST_QUOTES]
    else:
        items = list(_LAST_QUOTES.values())
    return {
        "items": items,
        "count": len(items),
        "requested_symbols": requested_symbols,
        "stream": get_live_stream_status(),
        "drain": drain_stats,
        "errors": _LAST_ERRORS[-5:],
    }


__all__ = [
    "drain_live_stream_events",
    "ensure_live_stream",
    "get_live_stream_snapshot",
    "get_live_stream_status",
]
