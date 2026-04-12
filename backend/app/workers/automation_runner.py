from __future__ import annotations

import time

from backend.app.config import LOG_LEVEL
from backend.app.core.logging_utils import configure_logging
from backend.app.db.session import init_db
from backend.app.services.continuous_learning import start_continuous_learning
from backend.app.services.scheduler_runtime import start_scheduler


def main() -> int:
    configure_logging(LOG_LEVEL)
    init_db(run_migrations=False)
    # Sync Alpaca market-data credentials from DB -> os.environ
    # so the scheduler's quote-snapshot jobs use Alpaca instead of yfinance.
    try:
        from backend.app.services.market_data import sync_alpaca_credentials_from_runtime
        sync_alpaca_credentials_from_runtime()
    except Exception:
        pass
    # Sync Telegram credentials from DB -> os.environ
    # so the alert notification jobs can send messages without restart.
    try:
        from backend.app.services.telegram_sync import sync_telegram_credentials_from_runtime
        sync_telegram_credentials_from_runtime()
    except Exception:
        pass
    scheduler_status = start_scheduler()
    learning_status = {"enabled": False, "accepted": False, "state": {}}
    if not scheduler_status.get("running"):
        learning_status = start_continuous_learning(requested_by="automation_runner")
    scheduler_ok = bool(scheduler_status.get("running"))
    learning_ok = bool(
        learning_status.get("accepted")
        or learning_status.get("already_running")
        or learning_status.get("state", {}).get("runtime_status") in {"running", "starting", "paused"}
    )
    if not scheduler_ok and not learning_ok:
        return 1
    while True:
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
