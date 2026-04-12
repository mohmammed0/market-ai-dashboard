"""LLM Gateway — unified interface for AI providers (Ollama / OpenAI).

All AI consumers (ai_overlay, ai_news_analyst, etc.) should use this
gateway instead of importing openai_client or ollama_client directly.

Provider selection:
  - AI_PROVIDER="ollama"  → Ollama only
  - AI_PROVIDER="openai"  → OpenAI only
  - AI_PROVIDER="auto"    → Try Ollama first, fall back to OpenAI
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
    """Return combined status of all configured AI providers."""
    result: dict[str, Any] = {"active_provider": AI_PROVIDER}

    try:
        from backend.app.services.ollama_client import get_ollama_runtime_status
        result["ollama"] = get_ollama_runtime_status()
    except Exception as exc:
        result["ollama"] = {"status": "error", "detail": str(exc)[:200]}

    try:
        from backend.app.services.openai_client import get_openai_runtime_status
        result["openai"] = get_openai_runtime_status()
    except Exception as exc:
        result["openai"] = {"status": "error", "detail": str(exc)[:200]}

    # Determine effective status
    ollama_ready = result.get("ollama", {}).get("status") == "ready"
    openai_ready = result.get("openai", {}).get("status") == "ready"

    if AI_PROVIDER == "ollama":
        result["effective_status"] = "ready" if ollama_ready else "unavailable"
        result["effective_provider"] = "ollama"
    elif AI_PROVIDER == "openai":
        result["effective_status"] = "ready" if openai_ready else "unavailable"
        result["effective_provider"] = "openai"
    else:  # auto
        if ollama_ready:
            result["effective_status"] = "ready"
            result["effective_provider"] = "ollama"
        elif openai_ready:
            result["effective_status"] = "ready"
            result["effective_provider"] = "openai"
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
    """Send a chat completion. Returns dict with 'content', 'provider', 'model', 'latency_seconds'."""

    provider = force_provider or AI_PROVIDER

    if provider == "ollama":
        return _call_ollama(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    elif provider == "openai":
        return _call_openai(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    elif provider == "auto":
        return _call_auto(messages, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    else:
        raise LLMUnavailableError(f"Unknown AI_PROVIDER: {provider}")


def _call_ollama(messages, **kwargs) -> dict:
    from backend.app.services.ollama_client import (
        OllamaRequestError,
        OllamaUnavailableError,
        ollama_chat_completion,
    )
    return ollama_chat_completion(messages, **kwargs)


def _call_openai(messages, *, temperature=0.3, max_tokens=1024, timeout=None) -> dict:
    import time
    from backend.app.services.openai_client import get_openai_client, get_openai_runtime_status

    status = get_openai_runtime_status()
    if not status["enabled"]:
        from backend.app.services.openai_client import OpenAIUnavailableError
        raise OpenAIUnavailableError(status["detail"])

    client = get_openai_client()
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=status["model"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    latency = round(time.perf_counter() - started, 3)
    content = response.choices[0].message.content if response.choices else ""

    return {
        "content": content,
        "model": status["model"],
        "provider": "openai",
        "latency_seconds": latency,
    }


def _call_auto(messages, **kwargs) -> dict:
    """Try Ollama first, fall back to OpenAI."""
    # Try Ollama
    try:
        from backend.app.services.ollama_client import get_ollama_runtime_status
        ollama_status = get_ollama_runtime_status()
        if ollama_status.get("status") == "ready":
            result = _call_ollama(messages, **kwargs)
            log_event(logger, logging.DEBUG, "llm_gateway.auto.ollama_ok")
            return result
    except Exception as exc:
        log_event(logger, logging.WARNING, "llm_gateway.auto.ollama_failed", error=str(exc)[:200])

    # Fall back to OpenAI
    try:
        result = _call_openai(messages, **kwargs)
        log_event(logger, logging.DEBUG, "llm_gateway.auto.openai_fallback_ok")
        return result
    except Exception as exc:
        log_event(logger, logging.WARNING, "llm_gateway.auto.openai_failed", error=str(exc)[:200])

    raise LLMUnavailableError(
        "No AI provider available. Configure Ollama (local) or OpenAI (remote)."
    )
