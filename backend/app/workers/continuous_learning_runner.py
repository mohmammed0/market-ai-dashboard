from __future__ import annotations

from backend.app.config import LOG_LEVEL
from backend.app.core.logging_utils import configure_logging
from backend.app.db.session import init_db
from backend.app.services.continuous_learning import run_continuous_learning_loop


def main() -> int:
    configure_logging(LOG_LEVEL)
    init_db(run_migrations=False)
    return run_continuous_learning_loop()


if __name__ == "__main__":
    raise SystemExit(main())
