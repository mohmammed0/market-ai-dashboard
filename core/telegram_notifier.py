"""Telegram notification delivery via Bot API.

Credentials are read from os.environ at call time (never cached at import).
Set via Settings UI -> stored in DB -> synced to os.environ at startup.

Environment variables:
    TELEGRAM_BOT_TOKEN  - Bot token from @BotFather
    TELEGRAM_CHAT_ID    - Target chat or channel ID
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org"


def is_telegram_configured() -> bool:
    """Return True if both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set and non-empty."""
    import os
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    return bool(token and chat_id)


def get_telegram_status() -> dict:
    """Return configuration status for the Telegram notifier."""
    import os
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    return {
        "configured": bool(token and chat_id),
        "bot_token_set": bool(token),
        "chat_id_set": bool(chat_id),
        "last_error": None,
    }


def send_telegram_message(text: str, parse_mode: str = "HTML") -> dict:
    """Send a message via the Telegram Bot API.

    Returns a dict with keys:
        ok    (bool)          - True on success
        error (str | None)    - Error description on failure, None on success
    """
    import os
    import httpx

    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

    if not token or not chat_id:
        return {"ok": False, "error": "Telegram credentials not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)."}

    url = f"{_TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}

    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        data = response.json()
        if response.status_code == 200 and data.get("ok"):
            logger.debug("telegram.send_message.ok chat_id=%s", chat_id)
            return {"ok": True, "error": None}
        error_desc = data.get("description") or f"HTTP {response.status_code}"
        logger.warning("telegram.send_message.failed error=%s", error_desc)
        return {"ok": False, "error": error_desc}
    except Exception as exc:
        error_desc = str(exc) or exc.__class__.__name__
        logger.warning("telegram.send_message.exception error=%s", error_desc)
        return {"ok": False, "error": error_desc}
