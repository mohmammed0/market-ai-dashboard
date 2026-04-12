"""LLM Gateway — unified interface for local AI providers (Ollama).

OpenAI has been permanently removed. All AI inference now routes through
the local Ollama inference system.

Provider selection (AI_PROVIDER env var):
  - "ollama"  → Ollama (default)
  - "auto"    → Ollama only (OpenAI fallback removed)
"""

from __future__ import annotations

import logging
from typing import Any

from backend.app.config import AI_PROVIDER
from backend.app.core.logging_utils import get_logger, log_event

logger = get_logger(__name__)


class LLMUnavailableError(RuntimeError):
    pass


def get_llm_status() -> dict:
    """Return status of the configured local AI provider (Ollama)."""
    result: dict[str, Any] = {"active_provider": AI_PROVIDER}

    try:
        from backend.app.services.ollama_client import get_ollama_runtime_status
        result["ollama"] = get_ollama_runtime_status()
    except Exception as exc:
        result["ollama"] = {"status": "error", "detail": str(exc)[:200]}

    # OpenAI permanently removed — always report standby
    result["openai"] = {
        "status": "standby",
        "detail": "OpenAI integration has been permanently removed.",
        "enabled": False,
    }

    # Effective status driven entirely by Ollama
    ollama_ready = result.get("ollama", {}).get("status") == "ready"

    if ollama_ready:
        result["effective_status"] = "ready"
        result["effective_provider"] = "ollama"
    else:
        result["effective_status"] = "unavailable"
        result["effective_provider"] = None

    return result


def llm_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    timeout: float | None = None,
    force_provider: str | None = None,
) -> dict[str, Any]:
    """Send a chat completion to the local model (Ollama).

    Returns dict with keys: content, provider, model, latency_seconds.
    Raises LLMUnavailableError when Ollama is not reachable.
    """
    # Any provider value resolves to Ollama — OpenAI is gone.
    return _call_ollama(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)


def _call_ollama(messages, **kwargs) -> dict:
    from backend.app.services.ollama_client import (
        OllamaRequestError,
        OllamaUnavailableError,
        ollama_chat_completion,
    )
    return ollama_chat_completion(messages, **kwargs)
