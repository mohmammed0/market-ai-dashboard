from __future__ import annotations

from backend.app.adapters.market_data.alpaca_adapter import AlpacaMarketDataAdapter
from backend.app.adapters.market_data.polygon_adapter import PolygonMarketDataAdapter
from backend.app.adapters.market_data.tiingo_adapter import TiingoMarketDataAdapter
from backend.app.adapters.market_data.twelvedata_adapter import TwelveDataMarketDataAdapter
from backend.app.adapters.market_data.yahoo_adapter import YahooMarketDataAdapter


ADAPTERS = {
    "alpaca": AlpacaMarketDataAdapter,
    "polygon": PolygonMarketDataAdapter,
    "tiingo": TiingoMarketDataAdapter,
    "twelvedata": TwelveDataMarketDataAdapter,
    "yahoo": YahooMarketDataAdapter,
}


def get_market_data_adapter(provider_name: str = "alpaca"):
    adapter_cls = ADAPTERS.get(str(provider_name or "").strip().lower(), AlpacaMarketDataAdapter)
    return adapter_cls()


__all__ = ["ADAPTERS", "get_market_data_adapter"]

