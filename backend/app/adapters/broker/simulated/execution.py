from __future__ import annotations

from backend.app.application.execution.service import confirm_paper_order, create_paper_order, preview_paper_order


def preview_order(**kwargs):
    return preview_paper_order(**kwargs)


def submit_order(**kwargs):
    return create_paper_order(**kwargs)


def confirm_order(preview_id: str):
    return confirm_paper_order(preview_id)


__all__ = ["confirm_order", "preview_order", "submit_order"]

