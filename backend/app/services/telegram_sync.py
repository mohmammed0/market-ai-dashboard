"""Sync Telegram credentials from DB runtime_settings to os.environ.

Follows the exact same pattern as sync_alpaca_credentials_from_runtime()
in backend/app/services/market_data.py.

Runtime settings keys:
    telegram_bot_token  -> TELEGRAM_BOT_TOKEN env var
    telegram_chat_id    -> TELEGRAM_CHAT_ID env var
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def sync_telegram_credentials_from_runtime(*, force_refresh: bool = False) -> None:
    """Read TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from DB runtime_settings
    and set them in os.environ if not already present.

    This is idempotent: if the env vars are already set (e.g. from a Docker
    environment variable), the DB values are not applied.

    Called at startup from backend/app/main.py and
    backend/app/workers/automation_runner.py.
    """
    if force_refresh:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)
    elif os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        return  # already supplied via environment; nothing to do

    try:
        from sqlalchemy import select
        from backend.app.models.runtime_settings import RuntimeSetting
        from backend.app.services.storage import session_scope

        with session_scope() as session:
            rows = session.execute(
                select(RuntimeSetting.key, RuntimeSetting.value_text, RuntimeSetting.is_secret)
                .where(RuntimeSetting.key.in_(["telegram_bot_token", "telegram_chat_id"]))
            ).all()
            db_values: dict[str, str] = {}
            for row in rows:
                raw = (row.value_text or "").strip()
                if not raw:
                    continue
                if row.is_secret:
                    try:
                        from backend.app.services.runtime_settings import _decrypt_secret
                        raw = _decrypt_secret(raw)
                    except Exception:
                        pass
                db_values[row.key] = raw

        bot_token = db_values.get("telegram_bot_token", "").strip()
        chat_id = db_values.get("telegram_chat_id", "").strip()

        if bot_token and (force_refresh or not os.getenv("TELEGRAM_BOT_TOKEN")):
            os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
        if chat_id and (force_refresh or not os.getenv("TELEGRAM_CHAT_ID")):
            os.environ["TELEGRAM_CHAT_ID"] = chat_id

        if bot_token and chat_id:
            logger.info("telegram_sync.credentials_synced_from_runtime source=db")
        elif bot_token or chat_id:
            logger.warning(
                "telegram_sync.partial_credentials bot_token_set=%s chat_id_set=%s",
                bool(bot_token),
                bool(chat_id),
            )
    except Exception as exc:
        logger.warning("telegram_sync.sync_failed error=%s", exc)
