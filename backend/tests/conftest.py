"""Shared test fixtures."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TEST_DB_ROOT = Path(tempfile.gettempdir()) / "market_ai_pytest"
_TEST_DB_ROOT.mkdir(parents=True, exist_ok=True)
_TEST_DB_PATH = _TEST_DB_ROOT / "shared_test.db"
for suffix in ("", "-wal", "-shm"):
    try:
        (_TEST_DB_ROOT / f"shared_test.db{suffix}").unlink()
    except FileNotFoundError:
        pass

# Force pytest to use an isolated local database instead of inheriting a
# developer runtime from `.env` or the shell environment.
os.environ["MARKET_AI_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"
os.environ["MARKET_AI_DB_AUTO_MIGRATE"] = "1"
os.environ["MARKET_AI_DB_RUN_MIGRATIONS_ON_STARTUP"] = "1"
os.environ["MARKET_AI_DB_LEGACY_BOOTSTRAP"] = "1"
os.environ["MARKET_AI_ENABLE_SCHEDULER"] = "0"
os.environ["MARKET_AI_ENABLE_CONTINUOUS_LEARNING"] = "0"
os.environ["MARKET_AI_AUTH_ENABLED"] = "0"
