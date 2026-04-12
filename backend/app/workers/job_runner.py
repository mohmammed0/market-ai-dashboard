from __future__ import annotations

import sys

from backend.app.core.logging_utils import configure_logging
from backend.app.db.session import init_db
from backend.app.services.background_jobs import run_background_job


def main(job_id: str) -> int:
    configure_logging("INFO")
    init_db(run_migrations=False)
    return run_background_job(job_id)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("job_runner requires a job_id")
    raise SystemExit(main(sys.argv[1]))
