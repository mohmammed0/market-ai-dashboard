from __future__ import annotations

from backend.app.services.market_universe import get_market_overview
from core.market_data_providers import get_market_data_provider_status


def build_market_snapshot_readmodel() -> dict:
    return {
        "overview": get_market_overview(),
        "provider_status": get_market_data_provider_status(),
    }


__all__ = ["build_market_snapshot_readmodel"]

