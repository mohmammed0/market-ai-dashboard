from __future__ import annotations

from hashlib import sha256


def build_idempotency_key(*parts: object) -> str:
    normalized = "|".join("" if part is None else str(part).strip() for part in parts)
    return sha256(normalized.encode("utf-8")).hexdigest()


__all__ = ["build_idempotency_key"]

