from __future__ import annotations

from typing import Protocol


class LLMAdapter(Protocol):
    def generate(self, prompt: str, *, system_prompt: str | None = None) -> dict: ...


__all__ = ["LLMAdapter"]

