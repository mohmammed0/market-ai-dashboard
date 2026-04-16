from __future__ import annotations

from backend.app.services.dashboard_hub import get_dashboard_lite, get_dashboard_summary


def build_dashboard_readmodel(*, compact: bool = True) -> dict:
    if compact:
        return get_dashboard_lite().model_dump(mode="json")
    return get_dashboard_summary()


__all__ = ["build_dashboard_readmodel"]

