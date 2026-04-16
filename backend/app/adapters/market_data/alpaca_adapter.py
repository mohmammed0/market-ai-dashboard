from __future__ import annotations

from backend.app.services.market_data import fetch_quote_snapshots


class AlpacaMarketDataAdapter:
    provider_name = "alpaca"

    def get_quotes(self, symbols: list[str]) -> dict:
        return fetch_quote_snapshots(symbols)

    def get_candles(self, symbol: str, interval: str = "1Day") -> dict:
        return {"symbol": symbol, "interval": interval, "provider": self.provider_name, "items": []}

    def get_status(self) -> dict:
        return {"provider": self.provider_name, "available": True}


__all__ = ["AlpacaMarketDataAdapter"]

