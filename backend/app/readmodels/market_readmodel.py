from __future__ import annotations

from backend.app.market_data.service import (
    fetch_quote_snapshots,
    get_market_data_provider_status,
    get_market_overview,
    get_market_universe_facets,
    list_currency_references,
)


def build_market_readmodel(*, symbols: list[str] | None = None) -> dict:
    symbols = symbols or ["AAPL", "MSFT", "NVDA", "SPY"]
    return {
        "overview": get_market_overview(),
        "provider_status": get_market_data_provider_status(),
        "facets": get_market_universe_facets(),
        "currencies": list_currency_references(limit=30, major_only=True),
        "quotes": fetch_quote_snapshots(symbols),
    }


__all__ = ["build_market_readmodel"]
