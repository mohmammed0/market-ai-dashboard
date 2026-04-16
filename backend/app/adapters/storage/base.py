from __future__ import annotations

from typing import Protocol


class StorageAdapter(Protocol):
    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, content: str) -> None: ...


__all__ = ["StorageAdapter"]

