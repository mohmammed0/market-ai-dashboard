"""Notification channel management endpoints (Telegram, etc.)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/notifications", tags=["notifications"])


class TelegramConfig(BaseModel):
    bot_token: str
    chat_id: str


@router.get("/telegram/status")
def telegram_status():
    """Return Telegram bot configuration status."""
    from core.telegram_notifier import get_telegram_status
    return get_telegram_status()


@router.post("/telegram/test")
def test_telegram():
    """Send a test message to verify Telegram bot is working."""
    from core.telegram_notifier import send_telegram_message, is_telegram_configured
    if not is_telegram_configured():
        return {"ok": False, "error": "Telegram is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID via /notifications/telegram/configure."}
    result = send_telegram_message(
        "✅ <b>Market AI Dashboard</b>\n\nTelegram integration is working correctly.",
        parse_mode="HTML",
    )
    return result


@router.post("/telegram/configure")
def configure_telegram(body: TelegramConfig):
    """Save Telegram bot credentials to DB runtime settings and sync to os.environ."""
    import os
    try:
        from backend.app.services.runtime_settings import set_runtime_setting
        set_runtime_setting("telegram_bot_token", body.bot_token.strip())
        set_runtime_setting("telegram_chat_id", body.chat_id.strip())
        os.environ["TELEGRAM_BOT_TOKEN"] = body.bot_token.strip()
        os.environ["TELEGRAM_CHAT_ID"] = body.chat_id.strip()
        return {"ok": True, "message": "Telegram credentials saved. Use /notifications/telegram/test to verify."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
