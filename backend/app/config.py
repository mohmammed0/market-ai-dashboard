import os
import sys
from pathlib import Path

from core.runtime_env import ENV_BOOTSTRAP_INFO
from core.runtime_paths import (
    BACKUPS_DIR,
    DATA_DIR,
    DEFAULT_RUNTIME_CACHE_DIR,
    LOGS_DIR,
    ROOT_DIR,
    default_database_url,
    is_postgresql_url,
    is_sqlite_url,
    normalize_database_url,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
API_TITLE = os.getenv("MARKET_AI_API_TITLE", "Market AI Dashboard API")
API_VERSION = os.getenv("MARKET_AI_API_VERSION", "0.1.0")
APP_ENV = os.getenv("MARKET_AI_ENV", "development").strip().lower()
SERVER_ROLE = os.getenv("MARKET_AI_SERVER_ROLE", "all" if APP_ENV != "production" else "api").strip().lower()
DATABASE_URL = normalize_database_url(os.getenv("MARKET_AI_DATABASE_URL", default_database_url()))
DATABASE_IS_SQLITE = is_sqlite_url(DATABASE_URL)
DATABASE_IS_POSTGRESQL = is_postgresql_url(DATABASE_URL)
DATABASE_AUTO_MIGRATE = os.getenv("MARKET_AI_DB_AUTO_MIGRATE", "1").strip().lower() not in {"0", "false", "no"}
DATABASE_RUN_MIGRATIONS_ON_STARTUP = os.getenv(
    "MARKET_AI_DB_RUN_MIGRATIONS_ON_STARTUP",
    "1" if SERVER_ROLE in {"api", "all"} else "0",
).strip().lower() not in {"0", "false", "no"}
DATABASE_LEGACY_BOOTSTRAP = os.getenv(
    "MARKET_AI_DB_LEGACY_BOOTSTRAP",
    "1" if DATABASE_IS_SQLITE and APP_ENV != "production" else "0",
).strip().lower() not in {"0", "false", "no"}
DATABASE_POOL_SIZE = max(1, int(os.getenv("MARKET_AI_DB_POOL_SIZE", "5")))
DATABASE_MAX_OVERFLOW = max(0, int(os.getenv("MARKET_AI_DB_MAX_OVERFLOW", "10")))
DATABASE_POOL_TIMEOUT_SECONDS = max(1, int(os.getenv("MARKET_AI_DB_POOL_TIMEOUT_SECONDS", "30")))
DATABASE_POOL_RECYCLE_SECONDS = max(30, int(os.getenv("MARKET_AI_DB_POOL_RECYCLE_SECONDS", "1800")))
DATABASE_CONNECT_TIMEOUT_SECONDS = max(1, int(os.getenv("MARKET_AI_DB_CONNECT_TIMEOUT_SECONDS", "10")))
DATABASE_APPLICATION_NAME = os.getenv("MARKET_AI_DB_APPLICATION_NAME", f"market_ai_{SERVER_ROLE or 'api'}").strip() or f"market_ai_{SERVER_ROLE or 'api'}"
DATABASE_STATEMENT_TIMEOUT_MS = max(1000, int(os.getenv("MARKET_AI_DB_STATEMENT_TIMEOUT_MS", "30000")))
DATABASE_LOCK_TIMEOUT_MS = max(1000, int(os.getenv("MARKET_AI_DB_LOCK_TIMEOUT_MS", "10000")))
DATABASE_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS = max(
    1000,
    int(os.getenv("MARKET_AI_DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS", "60000")),
)
API_HOST = os.getenv("MARKET_AI_HOST", "127.0.0.1")
API_PORT = int(os.getenv("MARKET_AI_PORT", "8000"))
LOG_LEVEL = os.getenv("MARKET_AI_LOG_LEVEL", "INFO").strip().upper()
FOCUSED_PRODUCT_MODE = os.getenv("MARKET_AI_FOCUSED_PRODUCT_MODE", "1" if APP_ENV == "production" else "0").strip().lower() not in {"0", "false", "no"}
DEFAULT_ANALYSIS_LOOKBACK_DAYS = max(7, int(os.getenv("MARKET_AI_DEFAULT_ANALYSIS_LOOKBACK_DAYS", "30")))
DEFAULT_TRAINING_LOOKBACK_DAYS = max(90, int(os.getenv("MARKET_AI_DEFAULT_TRAINING_LOOKBACK_DAYS", "365")))
DEFAULT_TRACKED_SYMBOL_LIMIT = max(5, min(int(os.getenv("MARKET_AI_DEFAULT_TRACKED_SYMBOL_LIMIT", "10")), 25))
LIGHTWEIGHT_EXPERIMENT_MODE = os.getenv("MARKET_AI_LIGHTWEIGHT_EXPERIMENT_MODE", "0").strip().lower() not in {"0", "false", "no"}
LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL = LIGHTWEIGHT_EXPERIMENT_MODE and os.getenv("MARKET_AI_LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL", "1").strip().lower() not in {"0", "false", "no"}
LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS = max(
    5,
    min(
        int(os.getenv("MARKET_AI_LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS", str(min(DEFAULT_TRACKED_SYMBOL_LIMIT, 8)))),
        10,
    ),
)
LIGHTWEIGHT_EXPERIMENT_NEWS_LIMIT = max(
    4,
    min(int(os.getenv("MARKET_AI_LIGHTWEIGHT_EXPERIMENT_NEWS_LIMIT", "8")), 12),
)
LOG_FILE_MAX_BYTES = int(os.getenv("MARKET_AI_LOG_FILE_MAX_BYTES", "5242880"))
LOG_FILE_BACKUP_COUNT = int(os.getenv("MARKET_AI_LOG_FILE_BACKUP_COUNT", "5"))
LOG_EVENTS_ENABLED = os.getenv("MARKET_AI_LOG_EVENTS_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
ENABLE_SCHEDULER = os.getenv("MARKET_AI_ENABLE_SCHEDULER", "1").strip().lower() not in {"0", "false", "no"}
SCHEDULER_RUNNER_ROLE = os.getenv("MARKET_AI_SCHEDULER_RUNNER_ROLE", "automation").strip().lower() or "automation"
SCHEDULER_ROLE_ALLOWED = ENABLE_SCHEDULER and SERVER_ROLE == SCHEDULER_RUNNER_ROLE
SCHEDULER_STARTUP_ENABLED = SCHEDULER_ROLE_ALLOWED
EVENT_TRANSPORT = os.getenv("MARKET_AI_EVENT_TRANSPORT", "inmemory").strip().lower() or "inmemory"
EVENT_PERSIST_DEAD_LETTERS = os.getenv("MARKET_AI_EVENT_PERSIST_DEAD_LETTERS", "1").strip().lower() not in {"0", "false", "no"}
NATS_URL = os.getenv("MARKET_AI_NATS_URL", "nats://127.0.0.1:4222").strip() or "nats://127.0.0.1:4222"
NATS_STREAM = os.getenv("MARKET_AI_NATS_STREAM", "MARKET_AI").strip() or "MARKET_AI"
NATS_SUBJECT_PREFIX = os.getenv("MARKET_AI_NATS_SUBJECT_PREFIX", "market_ai").strip().strip(".")
PUBLIC_WEB_ORIGIN = os.getenv("MARKET_AI_PUBLIC_WEB_ORIGIN", "").strip().rstrip("/")
PUBLIC_API_ORIGIN = os.getenv("MARKET_AI_PUBLIC_API_ORIGIN", "").strip().rstrip("/")
SERVER_NAME = os.getenv("MARKET_AI_SERVER_NAME", "").strip()
TRUSTED_HOSTS = [
    value.strip()
    for value in os.getenv("MARKET_AI_TRUSTED_HOSTS", ",".join([item for item in [SERVER_NAME, "localhost", "127.0.0.1", "backend", "testserver"] if item])).split(",")
    if value.strip()
]
PROXY_HEADERS_ENABLED = os.getenv("MARKET_AI_PROXY_HEADERS_ENABLED", "1" if APP_ENV == "production" else "0").strip().lower() not in {"0", "false", "no"}
FORWARDED_ALLOW_IPS = os.getenv("MARKET_AI_FORWARDED_ALLOW_IPS", "*").strip() or "*"
# --- Authentication ---
AUTH_ENABLED = os.getenv("MARKET_AI_AUTH_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
AUTH_SECRET_KEY = os.getenv("MARKET_AI_AUTH_SECRET_KEY", "change-me-in-production-use-openssl-rand-hex-32").strip()
AUTH_SECRET_KEY_IS_DEFAULT = AUTH_SECRET_KEY == "change-me-in-production-use-openssl-rand-hex-32"
AUTH_ALGORITHM = "HS256"
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("MARKET_AI_AUTH_TOKEN_EXPIRE_MINUTES", "1440"))
AUTH_DEFAULT_USERNAME = os.getenv("MARKET_AI_AUTH_DEFAULT_USERNAME", "admin").strip()
AUTH_DEFAULT_PASSWORD = os.getenv("MARKET_AI_AUTH_DEFAULT_PASSWORD", "").strip()
# OpenAI permanently removed — these vars are kept only for backward compatibility
# with code that reads them; OPENAI_ENABLED is hardcoded to False.
OPENAI_API_KEY = ""  # removed
OPENAI_MODEL = "none"  # removed
OPENAI_ENABLED = False  # permanently disabled
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
# --- Ollama (local LLM) ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b").strip() or "gemma2:2b"
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
OLLAMA_CONTEXT_LENGTH = int(os.getenv("OLLAMA_CONTEXT_LENGTH", "4096"))
AI_PROVIDER = os.getenv("MARKET_AI_PROVIDER", "ollama").strip().lower()  # resolved locally; non-ollama values degrade safely
BROKER_PROVIDER = os.getenv("MARKET_AI_BROKER_PROVIDER", "none").strip().lower()
BROKER_ORDER_SUBMISSION_ENABLED = os.getenv("MARKET_AI_BROKER_ORDER_SUBMISSION_ENABLED", "0").strip().lower() not in {"0", "false", "no"}
BROKER_LIVE_EXECUTION_ENABLED = os.getenv("MARKET_AI_BROKER_LIVE_EXECUTION_ENABLED", "0").strip().lower() not in {"0", "false", "no"}
ALPACA_ENABLED = os.getenv("MARKET_AI_ALPACA_ENABLED", "1" if BROKER_PROVIDER == "alpaca" else "0").strip().lower() not in {"0", "false", "no"}
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "").strip()
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "").strip()
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "1").strip().lower() not in {"0", "false", "no"}
ALPACA_URL_OVERRIDE = os.getenv("ALPACA_URL_OVERRIDE", "").strip()
ALPACA_ACCOUNT_REFRESH_SECONDS = int(os.getenv("MARKET_AI_ALPACA_ACCOUNT_REFRESH_SECONDS", "15"))
TRAINING_SUBPROCESS_ENABLED = os.getenv("MARKET_AI_TRAINING_SUBPROCESS_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
TRAINING_RUNNER_PYTHON = os.getenv("MARKET_AI_TRAINING_RUNNER_PYTHON", sys.executable).strip() or sys.executable
# Remote GPU worker mode: when enabled, start_training_job() just enqueues in DB
# (status=queued) without spawning a local subprocess. A remote worker (e.g. laptop
# with CUDA) polls /api/training/worker/next-job and executes the job. Remote
# workers authenticate via MARKET_AI_WORKER_TOKEN (shared secret).
REMOTE_TRAINING_ENABLED = os.getenv("MARKET_AI_REMOTE_TRAINING_ENABLED", "0").strip().lower() in {"1", "true", "yes"}
REMOTE_WORKER_STALE_SECONDS = int(os.getenv("MARKET_AI_REMOTE_WORKER_STALE_SECONDS", "300"))
CONTINUOUS_LEARNING_RUNNER_PYTHON = os.getenv("MARKET_AI_CONTINUOUS_LEARNING_RUNNER_PYTHON", sys.executable).strip() or sys.executable
AUTOMATION_DEFAULT_PRESET = os.getenv("MARKET_AI_AUTOMATION_DEFAULT_PRESET", "ALL_US_EQUITIES").strip().upper()
AUTOMATION_SYMBOL_LIMIT = int(os.getenv("MARKET_AI_AUTOMATION_SYMBOL_LIMIT", str(DEFAULT_TRACKED_SYMBOL_LIMIT)))
MARKET_CYCLE_MINUTES = int(os.getenv("MARKET_AI_MARKET_CYCLE_MINUTES", "30"))
ALERT_CYCLE_MINUTES = int(os.getenv("MARKET_AI_ALERT_CYCLE_MINUTES", "15"))
BREADTH_CYCLE_MINUTES = int(os.getenv("MARKET_AI_BREADTH_CYCLE_MINUTES", "20"))
NEWS_REFRESH_MINUTES = max(1, int(os.getenv("MARKET_AI_NEWS_REFRESH_MINUTES", "10")))
NEWS_REFRESH_PER_SYMBOL_LIMIT = max(1, min(int(os.getenv("MARKET_AI_NEWS_REFRESH_PER_SYMBOL_LIMIT", "5")), 10))
SIGNAL_REFRESH_MINUTES = max(1, min(int(os.getenv("MARKET_AI_SIGNAL_REFRESH_MINUTES", "5")), 15))
SIGNAL_CACHE_TTL_SECONDS = max(60, min(int(os.getenv("MARKET_AI_SIGNAL_CACHE_TTL_SECONDS", "300")), 1800))
_CPU_WORKER_HINT = max(2, min(int(os.getenv("MARKET_AI_CPU_WORKER_HINT", str(os.cpu_count() or 2))), 8))
SIGNAL_REFRESH_MAX_WORKERS = max(1, min(int(os.getenv("MARKET_AI_SIGNAL_REFRESH_MAX_WORKERS", str(_CPU_WORKER_HINT))), 8))
QUOTE_SNAPSHOT_MAX_WORKERS = max(1, min(int(os.getenv("MARKET_AI_QUOTE_SNAPSHOT_MAX_WORKERS", str(_CPU_WORKER_HINT))), 8))
CONFIDENCE_CALIBRATION_ENABLED = os.getenv("MARKET_AI_CONFIDENCE_CALIBRATION_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
CONFIDENCE_CALIBRATION_LOOKBACK_DAYS = max(30, min(int(os.getenv("MARKET_AI_CONFIDENCE_CALIBRATION_LOOKBACK_DAYS", "120")), 240))
CONFIDENCE_CALIBRATION_HOLD_DAYS = max(2, min(int(os.getenv("MARKET_AI_CONFIDENCE_CALIBRATION_HOLD_DAYS", "5")), 15))
CONFIDENCE_CALIBRATION_MIN_SAMPLES = max(8, min(int(os.getenv("MARKET_AI_CONFIDENCE_CALIBRATION_MIN_SAMPLES", "14")), 120))
CONFIDENCE_CALIBRATION_CACHE_TTL_SECONDS = max(300, min(int(os.getenv("MARKET_AI_CONFIDENCE_CALIBRATION_CACHE_TTL_SECONDS", "3600")), 21600))
TRADER_PROFILE = os.getenv("MARKET_AI_TRADER_PROFILE", "strong").strip().lower()
if TRADER_PROFILE not in {"conservative", "balanced", "strong"}:
    TRADER_PROFILE = "balanced"

_TRADER_PROFILE_DEFAULTS = {
    "conservative": {
        "ensemble_buy_threshold": 0.62,
        "ensemble_sell_threshold": -0.62,
        "directional_min_confidence": 62.0,
        "hold_max_confidence": 75.0,
        "opportunity_min_confidence": 60.0,
        "action_buy_confidence": 82.0,
        "action_add_confidence": 68.0,
        "action_exit_confidence": 80.0,
        "action_trim_confidence": 64.0,
        "action_hold_confidence": 62.0,
        "auto_min_signal_confidence": 70.0,
        "auto_min_ensemble_score": 0.32,
        "auto_min_agreement": 0.42,
    },
    "balanced": {
        "ensemble_buy_threshold": 0.55,
        "ensemble_sell_threshold": -0.55,
        "directional_min_confidence": 58.0,
        "hold_max_confidence": 72.0,
        "opportunity_min_confidence": 52.0,
        "action_buy_confidence": 80.0,
        "action_add_confidence": 64.0,
        "action_exit_confidence": 78.0,
        "action_trim_confidence": 60.0,
        "action_hold_confidence": 60.0,
        "auto_min_signal_confidence": 64.0,
        "auto_min_ensemble_score": 0.24,
        "auto_min_agreement": 0.34,
    },
    "strong": {
        "ensemble_buy_threshold": 0.47,
        "ensemble_sell_threshold": -0.47,
        "directional_min_confidence": 55.0,
        "hold_max_confidence": 67.0,
        "opportunity_min_confidence": 56.0,
        "action_buy_confidence": 75.0,
        "action_add_confidence": 58.0,
        "action_exit_confidence": 73.0,
        "action_trim_confidence": 56.0,
        "action_hold_confidence": 55.0,
        "auto_min_signal_confidence": 59.0,
        "auto_min_ensemble_score": 0.18,
        "auto_min_agreement": 0.25,
    },
}
_PROFILE_DEFAULTS = _TRADER_PROFILE_DEFAULTS[TRADER_PROFILE]

DECISION_ENSEMBLE_BUY_THRESHOLD = float(
    os.getenv(
        "MARKET_AI_DECISION_ENSEMBLE_BUY_THRESHOLD",
        str(_PROFILE_DEFAULTS["ensemble_buy_threshold"]),
    )
)
DECISION_ENSEMBLE_SELL_THRESHOLD = float(
    os.getenv(
        "MARKET_AI_DECISION_ENSEMBLE_SELL_THRESHOLD",
        str(_PROFILE_DEFAULTS["ensemble_sell_threshold"]),
    )
)
DECISION_DIRECTIONAL_MIN_CONFIDENCE = float(
    os.getenv(
        "MARKET_AI_DECISION_DIRECTIONAL_MIN_CONFIDENCE",
        str(_PROFILE_DEFAULTS["directional_min_confidence"]),
    )
)
DECISION_HOLD_MAX_CONFIDENCE = float(
    os.getenv(
        "MARKET_AI_DECISION_HOLD_MAX_CONFIDENCE",
        str(_PROFILE_DEFAULTS["hold_max_confidence"]),
    )
)
DECISION_OPPORTUNITY_MIN_CONFIDENCE = float(
    os.getenv(
        "MARKET_AI_DECISION_OPPORTUNITY_MIN_CONFIDENCE",
        str(_PROFILE_DEFAULTS["opportunity_min_confidence"]),
    )
)
DECISION_ACTION_BUY_CONFIDENCE = float(
    os.getenv(
        "MARKET_AI_DECISION_ACTION_BUY_CONFIDENCE",
        str(_PROFILE_DEFAULTS["action_buy_confidence"]),
    )
)
DECISION_ACTION_ADD_CONFIDENCE = float(
    os.getenv(
        "MARKET_AI_DECISION_ACTION_ADD_CONFIDENCE",
        str(_PROFILE_DEFAULTS["action_add_confidence"]),
    )
)
DECISION_ACTION_EXIT_CONFIDENCE = float(
    os.getenv(
        "MARKET_AI_DECISION_ACTION_EXIT_CONFIDENCE",
        str(_PROFILE_DEFAULTS["action_exit_confidence"]),
    )
)
DECISION_ACTION_TRIM_CONFIDENCE = float(
    os.getenv(
        "MARKET_AI_DECISION_ACTION_TRIM_CONFIDENCE",
        str(_PROFILE_DEFAULTS["action_trim_confidence"]),
    )
)
DECISION_ACTION_HOLD_CONFIDENCE = float(
    os.getenv(
        "MARKET_AI_DECISION_ACTION_HOLD_CONFIDENCE",
        str(_PROFILE_DEFAULTS["action_hold_confidence"]),
    )
)
AUTO_TRADING_MIN_SIGNAL_CONFIDENCE = float(
    os.getenv(
        "MARKET_AI_AUTO_TRADING_MIN_SIGNAL_CONFIDENCE",
        str(_PROFILE_DEFAULTS["auto_min_signal_confidence"]),
    )
)
AUTO_TRADING_MIN_ENSEMBLE_SCORE = float(
    os.getenv(
        "MARKET_AI_AUTO_TRADING_MIN_ENSEMBLE_SCORE",
        str(_PROFILE_DEFAULTS["auto_min_ensemble_score"]),
    )
)
AUTO_TRADING_MIN_AGREEMENT = float(
    os.getenv(
        "MARKET_AI_AUTO_TRADING_MIN_AGREEMENT",
        str(_PROFILE_DEFAULTS["auto_min_agreement"]),
    )
)
RETRAIN_CYCLE_HOURS = int(os.getenv("MARKET_AI_RETRAIN_CYCLE_HOURS", "24"))
ENABLE_AUTO_RETRAIN = os.getenv("MARKET_AI_ENABLE_AUTO_RETRAIN", "0").strip().lower() not in {"0", "false", "no"}
ENABLE_AUTONOMOUS_CYCLE = os.getenv("MARKET_AI_ENABLE_AUTONOMOUS_CYCLE", "0").strip().lower() not in {"0", "false", "no"}
AUTONOMOUS_CYCLE_HOURS = int(os.getenv("MARKET_AI_AUTONOMOUS_CYCLE_HOURS", "12"))
AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT = int(os.getenv("MARKET_AI_AUTONOMOUS_ANALYSIS_SYMBOL_LIMIT", str(DEFAULT_TRACKED_SYMBOL_LIMIT)))
AUTONOMOUS_TRAIN_SYMBOL_LIMIT = int(os.getenv("MARKET_AI_AUTONOMOUS_TRAIN_SYMBOL_LIMIT", "12"))
AUTONOMOUS_HISTORY_LOOKBACK_DAYS = int(os.getenv("MARKET_AI_AUTONOMOUS_HISTORY_LOOKBACK_DAYS", "45"))
AUTONOMOUS_INCLUDE_DL = os.getenv("MARKET_AI_AUTONOMOUS_INCLUDE_DL", "0").strip().lower() not in {"0", "false", "no"}
AUTONOMOUS_REFRESH_UNIVERSE = os.getenv("MARKET_AI_AUTONOMOUS_REFRESH_UNIVERSE", "1").strip().lower() not in {"0", "false", "no"}
ENABLE_CONTINUOUS_LEARNING = os.getenv("MARKET_AI_ENABLE_CONTINUOUS_LEARNING", "0").strip().lower() not in {"0", "false", "no"}
CONTINUOUS_LEARNING_RUNNER_ROLE = os.getenv("MARKET_AI_CONTINUOUS_LEARNING_RUNNER_ROLE", SCHEDULER_RUNNER_ROLE).strip().lower() or SCHEDULER_RUNNER_ROLE
CONTINUOUS_LEARNING_ROLE_ALLOWED = ENABLE_CONTINUOUS_LEARNING and SERVER_ROLE == CONTINUOUS_LEARNING_RUNNER_ROLE
CONTINUOUS_LEARNING_STARTUP_ENABLED = CONTINUOUS_LEARNING_ROLE_ALLOWED
CONTINUOUS_LEARNING_CYCLE_SECONDS = int(os.getenv("MARKET_AI_CONTINUOUS_LEARNING_CYCLE_SECONDS", "1800"))
CONTINUOUS_LEARNING_HEARTBEAT_SECONDS = int(os.getenv("MARKET_AI_CONTINUOUS_LEARNING_HEARTBEAT_SECONDS", "30"))
CONTINUOUS_LEARNING_STALE_SECONDS = int(os.getenv("MARKET_AI_CONTINUOUS_LEARNING_STALE_SECONDS", "180"))
CONTINUOUS_LEARNING_PAUSE_SECONDS = int(os.getenv("MARKET_AI_CONTINUOUS_LEARNING_PAUSE_SECONDS", "20"))
CONTINUOUS_LEARNING_MAX_CANDIDATES = int(os.getenv("MARKET_AI_CONTINUOUS_LEARNING_MAX_CANDIDATES", "6"))
CONTINUOUS_LEARNING_EVALUATION_SYMBOLS = int(os.getenv("MARKET_AI_CONTINUOUS_LEARNING_EVALUATION_SYMBOLS", "6"))
CONTINUOUS_LEARNING_POLICY_LOOKBACK_DAYS = int(os.getenv("MARKET_AI_CONTINUOUS_LEARNING_POLICY_LOOKBACK_DAYS", "60"))
AUTOMATION_DAILY_SUMMARY_HOUR = int(os.getenv("MARKET_AI_DAILY_SUMMARY_HOUR_UTC", "21"))
RISK_DEFAULT_PORTFOLIO_VALUE = float(os.getenv("MARKET_AI_RISK_DEFAULT_PORTFOLIO_VALUE", "100000"))
RISK_MAX_TRADE_PCT = float(os.getenv("MARKET_AI_RISK_MAX_TRADE_PCT", "10.0"))
RISK_MAX_DAILY_LOSS_PCT = float(os.getenv("MARKET_AI_RISK_MAX_DAILY_LOSS_PCT", "15.0"))
RISK_DEFAULT_STOP_PCT = float(os.getenv("MARKET_AI_RISK_DEFAULT_STOP_PCT", "3.0"))
RISK_DEFAULT_TARGET_PCT = float(os.getenv("MARKET_AI_RISK_DEFAULT_TARGET_PCT", "6.0"))
# Paper trading realism model
PAPER_SLIPPAGE_BPS = float(os.getenv("MARKET_AI_PAPER_SLIPPAGE_BPS", "5"))          # 5 bps = 0.05% directional slippage for market orders
PAPER_SPREAD_BPS = float(os.getenv("MARKET_AI_PAPER_SPREAD_BPS", "10"))              # 10 bps full spread; half applied per side when no live bid/ask
PAPER_FEE_PER_SHARE = float(os.getenv("MARKET_AI_PAPER_FEE_PER_SHARE", "0.005"))    # $0.005/share commission (typical US equity rate)
PAPER_PARTIAL_FILL_THRESHOLD = float(os.getenv("MARKET_AI_PAPER_PARTIAL_FILL_THRESHOLD", "500"))  # orders > N shares get partial fill
PAPER_PARTIAL_FILL_RATIO = float(os.getenv("MARKET_AI_PAPER_PARTIAL_FILL_RATIO", "0.9"))          # fill 90% of large orders
ALERT_BREAKOUT_PCT = float(os.getenv("MARKET_AI_ALERT_BREAKOUT_PCT", "3.5"))
ALERT_UNUSUAL_MOVE_PCT = float(os.getenv("MARKET_AI_ALERT_UNUSUAL_MOVE_PCT", "5.0"))
ALERT_VOLUME_SPIKE_MULTIPLIER = float(os.getenv("MARKET_AI_ALERT_VOLUME_SPIKE_MULTIPLIER", "2.0"))
ALERT_CONFIDENCE_JUMP = float(os.getenv("MARKET_AI_ALERT_CONFIDENCE_JUMP", "15"))
AUTOMATION_ALERT_SYMBOL_LIMIT = int(os.getenv("MARKET_AI_ALERT_SYMBOL_LIMIT", "10"))
AUTOMATION_BREADTH_SYMBOL_LIMIT = int(os.getenv("MARKET_AI_BREADTH_SYMBOL_LIMIT", "12"))
AUTOMATION_WATCHLIST_SYMBOL_LIMIT = int(os.getenv("MARKET_AI_WATCHLIST_SYMBOL_LIMIT", "12"))
MODEL_PROMOTION_MIN_F1 = float(os.getenv("MARKET_AI_MODEL_PROMOTION_MIN_F1", "0.33"))
MODEL_PROMOTION_MIN_TEST_ACCURACY = float(os.getenv("MARKET_AI_MODEL_PROMOTION_MIN_TEST_ACCURACY", "0.42"))
MODEL_PROMOTION_MAX_DRAWDOWN_PCT = float(os.getenv("MARKET_AI_MODEL_PROMOTION_MAX_DRAWDOWN_PCT", "35"))
DEFAULT_SAMPLE_SYMBOLS = [
    symbol.strip().upper()
    for symbol in os.getenv("MARKET_AI_SAMPLE_SYMBOLS", "AAPL,MSFT,NVDA,AMZN,GOOGL,META").split(",")
    if symbol.strip()
]
DEFAULT_INDEX_SYMBOLS = [
    symbol.strip().upper()
    for symbol in os.getenv("MARKET_AI_INDEX_SYMBOLS", "^GSPC,^DJI,^IXIC,^RUT,^VIX").split(",")
    if symbol.strip()
]
MARKET_UNIVERSE_TTL_HOURS = int(os.getenv("MARKET_AI_UNIVERSE_TTL_HOURS", "24"))
# --- Redis ---
REDIS_URL = os.getenv("MARKET_AI_REDIS_URL", "").strip()
REDIS_ENABLED = os.getenv("MARKET_AI_REDIS_ENABLED", "1" if REDIS_URL else "0").strip().lower() not in {"0", "false", "no"}
REDIS_CACHE_TTL_DEFAULT = int(os.getenv("MARKET_AI_REDIS_CACHE_TTL_DEFAULT", "300"))
REDIS_CONNECT_TIMEOUT = int(os.getenv("MARKET_AI_REDIS_CONNECT_TIMEOUT", "5"))
REDIS_SOCKET_TIMEOUT = int(os.getenv("MARKET_AI_REDIS_SOCKET_TIMEOUT", "5"))
SQLITE_BUSY_TIMEOUT_MS = max(1000, int(os.getenv("MARKET_AI_SQLITE_BUSY_TIMEOUT_MS", "5000")))
SQLITE_CACHE_SIZE_KB = max(1024, int(os.getenv("MARKET_AI_SQLITE_CACHE_SIZE_KB", "20000")))
# --- MLflow ---
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "").strip()
MLFLOW_EXPERIMENT_PREFIX = os.getenv("MARKET_AI_MLFLOW_EXPERIMENT_PREFIX", "market_ai").strip()
# --- Prefect ---
PREFECT_API_URL = os.getenv("PREFECT_API_URL", "").strip()
# --- Celery ---
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "").strip()
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "").strip()

RUNTIME_CACHE_DIR = Path(os.getenv("MARKET_AI_RUNTIME_CACHE_DIR", str(DEFAULT_RUNTIME_CACHE_DIR)))


def _default_allowed_origins() -> list[str]:
    origins = []
    if PUBLIC_WEB_ORIGIN:
        origins.append(PUBLIC_WEB_ORIGIN)
    if APP_ENV != "production":
        origins.extend([
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ])
    seen = []
    for origin in origins:
        normalized = str(origin or "").strip().rstrip("/")
        if normalized and normalized not in seen:
            seen.append(normalized)
    return seen


def _parse_allowed_origins() -> list[str]:
    raw_value = os.getenv("MARKET_AI_ALLOWED_ORIGINS")
    if raw_value is None or not str(raw_value).strip():
        return _default_allowed_origins()
    items = [origin.strip().rstrip("/") for origin in str(raw_value).split(",") if origin.strip()]
    return items


ALLOWED_ORIGINS = _parse_allowed_origins()
BACKGROUND_JOB_MAX_ACTIVE_TOTAL = max(1, int(os.getenv("MARKET_AI_BACKGROUND_JOB_MAX_ACTIVE_TOTAL", "4")))
BACKGROUND_JOB_MAX_ACTIVE_PER_TYPE = max(1, int(os.getenv("MARKET_AI_BACKGROUND_JOB_MAX_ACTIVE_PER_TYPE", "2")))
BACKGROUND_JOB_STALE_PENDING_SECONDS = max(30, int(os.getenv("MARKET_AI_BACKGROUND_JOB_STALE_PENDING_SECONDS", "300")))
TRAINING_JOB_MAX_ACTIVE = max(1, int(os.getenv("MARKET_AI_TRAINING_JOB_MAX_ACTIVE", "1")))
TRAINING_JOB_STALE_PENDING_SECONDS = max(30, int(os.getenv("MARKET_AI_TRAINING_JOB_STALE_PENDING_SECONDS", "300")))

OPS_LOGS_DIR = LOGS_DIR
OPS_BACKUPS_DIR = BACKUPS_DIR

# --- Auto Trading ---
AUTO_TRADING_ENABLED = os.getenv("MARKET_AI_AUTO_TRADING_ENABLED", "0").strip().lower() not in {"0", "false", "no"}
AUTO_TRADING_CYCLE_MINUTES = int(os.getenv("MARKET_AI_AUTO_TRADING_CYCLE_MINUTES", "30"))
AUTO_TRADING_QUANTITY = float(os.getenv("MARKET_AI_AUTO_TRADING_QUANTITY", "1"))
AUTO_TRADING_UNIVERSE_PRESET = os.getenv(
    "MARKET_AI_AUTO_TRADING_UNIVERSE_PRESET",
    "FOCUSED_SAMPLE" if FOCUSED_PRODUCT_MODE else "TOP_500_MARKET_CAP",
).strip().upper()
