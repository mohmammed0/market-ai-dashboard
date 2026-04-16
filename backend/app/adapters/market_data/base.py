from __future__ import annotations

from typing import Protocol


class MarketDataAdapter(Protocol):
    provider_name: str

    def get_quotes(self, symbols: list[str]) -> dict: ...
    def get_candles(self, symbol: str, interval: str = "1Day") -> dict: ...
    def get_status(self) -> dict: ...


__all__ = ["MarketDataAdapter"]

