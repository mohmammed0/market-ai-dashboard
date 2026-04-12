from __future__ import annotations

from fastapi import HTTPException


def infer_error_status(detail: str, default_status: int = 400) -> int:
    message = str(detail or "").strip().lower()
    if not message:
        return int(default_status)
    if "not found" in message or "missing" in message:
        return 404
    if "capacity" in message or "too many" in message or "busy" in message:
        return 429
    if "already running" in message or "duplicate" in message or "active" in message:
        return 409
    if (
        "invalid" in message
        or "required" in message
        or "unsupported" in message
        or "must be" in message
        or "cannot" in message
    ):
        return 400
    if "disabled" in message or "unavailable" in message:
        return 503
    return int(default_status)


def to_http_exception(exc: Exception, default_status: int = 400) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc

    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        if isinstance(exc, LookupError):
            status_code = 404
        elif isinstance(exc, ValueError):
            status_code = 400
        else:
            status_code = infer_error_status(str(exc), default_status=default_status)

    return HTTPException(status_code=int(status_code), detail=str(exc))


def raise_for_error_payload(payload: dict | None, *, default_status: int = 400) -> dict | None:
    if isinstance(payload, dict) and payload.get("error"):
        raise HTTPException(
            status_code=infer_error_status(payload.get("error"), default_status=default_status),
            detail=str(payload.get("error")),
        )
    return payload
