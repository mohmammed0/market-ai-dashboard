"""openai_client.py — OpenAI integration (PERMANENTLY DISABLED).

OpenAI has been removed from this project in favour of the local model
inference system (Ollama).  This module is kept only so that existing
imports from llm_gateway / runtime_settings do not break. Every function
in this module returns a disabled/unavailable response and never attempts
a real network call.
"""

from __future__ import annotations

from backend.app.config import OPENAI_TIMEOUT_SECONDS

# OpenAI SDK is no longer installed — all classes are stubbed out.
OpenAI = None
APIConnectionError = APIError = APITimeoutError = RateLimitError = Exception


class OpenAIUnavailableError(RuntimeError):
    pass


class OpenAIRequestError(RuntimeError):
    pass


def get_openai_runtime_status() -> dict:
    """Always returns disabled/standby — OpenAI has been permanently removed."""
    return {
        "enabled": False,
        "requested_enabled": False,
        "runtime_enabled": False,
        "configured": False,
        "sdk_installed": False,
        "status": "standby",
        "model": "none",
        "timeout_seconds": OPENAI_TIMEOUT_SECONDS,
        "enabled_source": "hardcoded",
        "api_key_source": "hardcoded",
        "model_source": "hardcoded",
        "detail": "OpenAI integration has been permanently removed. Use local model (Ollama).",
    }


def get_openai_client():
    raise OpenAIUnavailableError(
        "OpenAI integration has been permanently removed. Use the local model (Ollama) instead."
    )
