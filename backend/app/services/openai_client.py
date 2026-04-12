from __future__ import annotations

from backend.app.config import OPENAI_TIMEOUT_SECONDS
from backend.app.services.runtime_settings import get_openai_runtime_config

try:
    from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None
    APIConnectionError = APIError = APITimeoutError = RateLimitError = Exception


class OpenAIUnavailableError(RuntimeError):
    pass


class OpenAIRequestError(RuntimeError):
    pass


def get_openai_runtime_status() -> dict:
    config = get_openai_runtime_config()
    sdk_installed = OpenAI is not None
    configured = bool(config["api_key"])
    requested_enabled = bool(config["enabled"])
    runtime_enabled = bool(requested_enabled and configured and sdk_installed)

    if not requested_enabled:
        detail = "OpenAI integration is disabled by configuration."
        status = "standby"
    elif not sdk_installed:
        detail = "openai package is not installed in the backend environment."
        status = "error"
    elif not configured:
        detail = "OpenAI API key is missing."
        status = "warning"
    else:
        detail = "OpenAI integration is ready."
        status = "ready"

    return {
        "enabled": runtime_enabled,
        "requested_enabled": requested_enabled,
        "runtime_enabled": runtime_enabled,
        "configured": configured,
        "sdk_installed": sdk_installed,
        "status": status,
        "model": config["model"],
        "timeout_seconds": OPENAI_TIMEOUT_SECONDS,
        "enabled_source": config["enabled_source"],
        "api_key_source": config["api_key_source"],
        "model_source": config["model_source"],
        "detail": detail,
    }


def get_openai_client():
    status = get_openai_runtime_status()
    if not status["enabled"]:
        raise OpenAIUnavailableError(status["detail"])
    config = get_openai_runtime_config()
    return OpenAI(api_key=config["api_key"], timeout=OPENAI_TIMEOUT_SECONDS, max_retries=1)
