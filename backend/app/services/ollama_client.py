"""Ollama local LLM client — drop-in companion to openai_client.py.

Provides the same interface pattern so ai_overlay.py and ai_news_analyst.py
can switch providers transparently.

Designed for 8GB RAM servers running quantized 7B models (Mistral, Phi-3).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from backend.app.config import (
    OLLAMA_BASE_URL,
    OLLAMA_CONTEXT_LENGTH,
    OLLAMA_ENABLED,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
)
from backend.app.core.logging_utils import get_logger, log_event

logger = get_logger(__name__)


class OllamaUnavailableError(RuntimeError):
    pass


class OllamaRequestError(RuntimeError):
    pass


def get_ollama_runtime_status() -> dict:
    """Check if Ollama server is reachable and model is loaded."""
    if not OLLAMA_ENABLED:
        return {
            "enabled": False,
            "status": "standby",
            "model": OLLAMA_MODEL,
            "base_url": OLLAMA_BASE_URL,
            "detail": "Ollama integration is disabled by configuration.",
            "server_reachable": False,
            "model_loaded": False,
        }

    server_reachable = False
    model_loaded = False
    detail = ""

    try:
        resp = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        resp.raise_for_status()
        server_reachable = True
        models = resp.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        base_model = OLLAMA_MODEL.split(":")[0] if ":" in OLLAMA_MODEL else OLLAMA_MODEL
        model_loaded = any(
            OLLAMA_MODEL in name or base_model in name for name in model_names
        )
        if model_loaded:
            detail = f"Ollama ready with model {OLLAMA_MODEL}."
            status = "ready"
        else:
            detail = f"Ollama server reachable but model '{OLLAMA_MODEL}' not found. Available: {model_names[:5]}"
            status = "warning"
    except httpx.ConnectError:
        detail = f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. Is the server running?"
        status = "error"
    except Exception as exc:
        detail = f"Ollama health check failed: {str(exc)[:200]}"
        status = "error"

    return {
        "enabled": OLLAMA_ENABLED,
        "status": status,
        "model": OLLAMA_MODEL,
        "base_url": OLLAMA_BASE_URL,
        "timeout_seconds": OLLAMA_TIMEOUT_SECONDS,
        "context_length": OLLAMA_CONTEXT_LENGTH,
        "detail": detail,
        "server_reachable": server_reachable,
        "model_loaded": model_loaded,
    }


def ollama_chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Send a chat completion request to Ollama. Returns OpenAI-compatible dict."""
    if not OLLAMA_ENABLED:
        raise OllamaUnavailableError("Ollama integration is disabled.")

    used_model = model or OLLAMA_MODEL
    used_timeout = timeout or OLLAMA_TIMEOUT_SECONDS

    payload = {
        "model": used_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": OLLAMA_CONTEXT_LENGTH,
        },
    }

    started = time.perf_counter()
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=used_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        latency = round(time.perf_counter() - started, 3)

        content = data.get("message", {}).get("content", "")
        log_event(logger, logging.DEBUG, "ollama.chat.ok",
                  model=used_model, latency_s=latency, content_len=len(content))

        return {
            "content": content,
            "model": data.get("model", used_model),
            "provider": "ollama",
            "latency_seconds": latency,
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
        }

    except httpx.ConnectError as exc:
        raise OllamaUnavailableError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}: {exc}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaRequestError(
            f"Ollama request timed out after {used_timeout}s"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise OllamaRequestError(
            f"Ollama HTTP error {exc.response.status_code}: {exc.response.text[:300]}"
        ) from exc
    except Exception as exc:
        raise OllamaRequestError(f"Ollama request failed: {exc}") from exc


def ollama_generate(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    system: str | None = None,
) -> dict[str, Any]:
    """Simple generate endpoint (non-chat). Useful for one-shot prompts."""
    if not OLLAMA_ENABLED:
        raise OllamaUnavailableError("Ollama integration is disabled.")

    used_model = model or OLLAMA_MODEL

    payload: dict[str, Any] = {
        "model": used_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": OLLAMA_CONTEXT_LENGTH,
        },
    }
    if system:
        payload["system"] = system

    started = time.perf_counter()
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        latency = round(time.perf_counter() - started, 3)

        return {
            "content": data.get("response", ""),
            "model": data.get("model", used_model),
            "provider": "ollama",
            "latency_seconds": latency,
        }
    except Exception as exc:
        raise OllamaRequestError(f"Ollama generate failed: {exc}") from exc
