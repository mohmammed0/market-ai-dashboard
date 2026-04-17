from __future__ import annotations

from collections import defaultdict, deque
from threading import RLock
from time import time

from fastapi import HTTPException, Request

_WINDOW_SECONDS = 60
_events_by_key: dict[str, deque[float]] = defaultdict(deque)
_lock = RLock()


def _client_identity(request: Request) -> str:
    forwarded_for = str(request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    if request.client is not None and request.client.host:
        return str(request.client.host)
    return "unknown"


def enforce_rate_limit(
    request: Request,
    *,
    bucket: str,
    per_minute: int,
    window_seconds: int = _WINDOW_SECONDS,
) -> None:
    limit = int(per_minute or 0)
    if limit <= 0:
        return

    client_id = _client_identity(request)
    route_path = str(request.url.path or "").strip()
    cache_key = f"{bucket}:{client_id}:{route_path}"
    now = time()
    cutoff = now - max(1, int(window_seconds))

    with _lock:
        events = _events_by_key[cache_key]
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for {bucket}. Try again in a minute.",
            )
        events.append(now)

