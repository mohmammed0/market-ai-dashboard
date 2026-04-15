"""Notification channel management endpoints (Telegram, etc.)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/notifications", tags=["notifications"])


class TelegramConfig(BaseModel):
    bot_token: str
    chat_id: str


def _sync_telegram_from_db() -> None:
    """Sync Telegram creds from DB into this worker's os.environ (idempotent).

    With multiple uvicorn workers, only the worker handling /configure gets the
    in-memory env update. Call this at the start of status/test to cover the
    case where a different worker handles the follow-up request.
    """
    try:
        from backend.app.services.telegram_sync import sync_telegram_credentials_from_runtime
        sync_telegram_credentials_from_runtime(force_refresh=True)
    except Exception:
        pass


@router.get("/telegram/status")
def telegram_status():
    """Return Telegram bot configuration status."""
    _sync_telegram_from_db()
    from core.telegram_notifier import get_telegram_status
    return get_telegram_status()


@router.post("/telegram/test")
def test_telegram():
    """Send a test message to verify Telegram bot is working."""
    _sync_telegram_from_db()
    from core.telegram_notifier import send_telegram_message, is_telegram_configured
    if not is_telegram_configured():
        return {
            "ok": False,
            "error": "Telegram is not configured. Save bot_token and chat_id first.",
            "detail": "احفظ Bot Token و Chat ID أولًا ثم أعد اختبار الإرسال.",
        }
    result = send_telegram_message(
        "✅ <b>Market AI Dashboard</b>\n\nTelegram integration is working correctly.",
        parse_mode="HTML",
    )
    if result.get("ok"):
        return {
            "ok": True,
            "detail": "تم إرسال الرسالة التجريبية بنجاح.",
        }
    return {
        "ok": False,
        "error": result.get("error"),
        "detail": f"فشل إرسال الرسالة التجريبية: {result.get('error') or 'unknown error'}",
    }


@router.post("/telegram/configure")
def configure_telegram(body: TelegramConfig):
    """Persist Telegram bot credentials to runtime settings for later testing."""
    try:
        token = (body.bot_token or "").strip()
        chat = (body.chat_id or "").strip()
        if not token or not chat:
            return {"ok": False, "error": "bot_token and chat_id are required.", "detail": "Bot Token و Chat ID مطلوبان."}

        from backend.app.services.runtime_settings import _upsert_setting
        from backend.app.services.storage import session_scope
        from backend.app.services.telegram_sync import sync_telegram_credentials_from_runtime

        with session_scope() as session:
            _upsert_setting(session, "telegram_bot_token", token, secret=True)
            _upsert_setting(session, "telegram_chat_id", chat)
        sync_telegram_credentials_from_runtime(force_refresh=True)

        return {
            "ok": True,
            "saved": True,
            "configured": True,
            "detail": "تم حفظ بيانات تيليجرام. استخدم زر الرسالة التجريبية للتحقق من وصول البوت.",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "detail": str(exc)}
