from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from typing import Any

from backend.app.config import LOG_EVENTS_ENABLED, LOG_FILE_BACKUP_COUNT, LOG_FILE_MAX_BYTES, OPS_LOGS_DIR
from core.runtime_paths import ensure_runtime_directories


_EVENTS_LOGGER_NAME = "market_ai.events"
_APP_LOG_PATH = OPS_LOGS_DIR / "app.log"
_EVENTS_LOG_PATH = OPS_LOGS_DIR / "events.jsonl"
_CONFIGURED = False

_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(https://api\.telegram\.org/bot)([^/\s\"']+)(/)", re.IGNORECASE),
        r"\1***REDACTED***\3",
    ),
    (
        re.compile(r"((?:Authorization|authorization)\s*[:=]\s*Bearer\s+)([A-Za-z0-9._\-]+)"),
        r"\1***REDACTED***",
    ),
    (
        re.compile(
            r"((?:bot_token|api_key|secret_key|password|access_token|worker_token|auth_secret_key)[\"']?\s*[:=]\s*[\"']?)([^\"',\s}]+)",
            re.IGNORECASE,
        ),
        r"\1***REDACTED***",
    ),
    (
        re.compile(
            r"((?:TELEGRAM_BOT_TOKEN|ALPACA_API_KEY|ALPACA_SECRET_KEY|MARKET_AI_AUTH_SECRET_KEY|MARKET_AI_WORKER_TOKEN)=)([^\s]+)",
            re.IGNORECASE,
        ),
        r"\1***REDACTED***",
    ),
)


def redact_secrets(text: str) -> str:
    sanitized = str(text or "")
    for pattern, replacement in _REDACTION_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED

    level_value = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    if _CONFIGURED:
        logging.getLogger().setLevel(level_value)
        logging.getLogger(_EVENTS_LOGGER_NAME).setLevel(level_value)
        return

    ensure_runtime_directories()
    formatter = RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level_value)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level_value)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    app_handler = RotatingFileHandler(
        _APP_LOG_PATH,
        maxBytes=max(int(LOG_FILE_MAX_BYTES or 0), 1024 * 1024),
        backupCount=max(int(LOG_FILE_BACKUP_COUNT or 0), 1),
        encoding="utf-8",
    )
    app_handler.setLevel(level_value)
    app_handler.setFormatter(formatter)
    root.addHandler(app_handler)

    events_logger = logging.getLogger(_EVENTS_LOGGER_NAME)
    events_logger.handlers.clear()
    events_logger.setLevel(level_value)
    events_logger.propagate = False
    if LOG_EVENTS_ENABLED:
        events_handler = RotatingFileHandler(
            _EVENTS_LOG_PATH,
            maxBytes=max(int(LOG_FILE_MAX_BYTES or 0), 1024 * 1024),
            backupCount=max(int(LOG_FILE_BACKUP_COUNT or 0), 1),
            encoding="utf-8",
        )
        events_handler.setLevel(level_value)
        events_handler.setFormatter(RedactingFormatter("%(message)s"))
        events_logger.addHandler(events_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, event: str, **context: Any) -> None:
    payload = {
        "event": event,
        "logger": logger.name,
        "level": logging.getLevelName(level),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **context,
    }
    try:
        message = redact_secrets(json.dumps(payload, default=str, sort_keys=True))
    except Exception:
        message = f"{event} | context_encode_failed"
    logger.log(level, message)
    if LOG_EVENTS_ENABLED and logger.name != _EVENTS_LOGGER_NAME:
        logging.getLogger(_EVENTS_LOGGER_NAME).log(level, message)


def get_log_paths() -> dict[str, str]:
    return {
        "app_log": str(_APP_LOG_PATH),
        "events_log": str(_EVENTS_LOG_PATH),
    }


def _tail_lines(path: Path, limit: int = 100) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return list(deque(handle, maxlen=max(int(limit or 0), 1)))


def read_recent_events(limit: int = 100) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in _tail_lines(_EVENTS_LOG_PATH, limit=limit):
        text = str(line or "").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                items.append(payload)
            else:
                items.append({"message": text})
        except Exception:
            items.append({"message": text})
    return items[-limit:]


def read_recent_app_log(limit: int = 100) -> list[str]:
    return [line.rstrip("\r\n") for line in _tail_lines(_APP_LOG_PATH, limit=limit)]
