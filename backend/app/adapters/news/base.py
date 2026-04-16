from __future__ import annotations

from typing import Protocol


class NewsAdapter(Protocol):
    def analyze_news(self, payload: dict) -> dict: ...


__all__ = ["NewsAdapter"]

