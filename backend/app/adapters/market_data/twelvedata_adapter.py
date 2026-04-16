from __future__ import annotations


class TwelveDataMarketDataAdapter:
    provider_name = "twelvedata"

    def get_quotes(self, symbols: list[str]) -> dict:
        return {"provider": self.provider_name, "symbols": symbols, "items": []}

    def get_candles(self, symbol: str, interval: str = "1Day") -> dict:
        return {"symbol": symbol, "interval": interval, "provider": self.provider_name, "items": []}

    def get_status(self) -> dict:
        return {"provider": self.provider_name, "available": False, "detail": "Adapter scaffold only."}


__all__ = ["TwelveDataMarketDataAdapter"]

