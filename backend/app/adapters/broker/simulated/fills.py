from __future__ import annotations

from backend.app.application.execution.service import list_paper_orders


def list_fill_backed_orders(limit: int = 100, status: str | None = None) -> dict:
    return list_paper_orders(limit=limit, status=status)


__all__ = ["list_fill_backed_orders"]

