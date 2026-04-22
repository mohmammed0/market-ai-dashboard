from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.config import (
    CONTINUOUS_LEARNING_RUNNER_ROLE,
    CONTINUOUS_LEARNING_STARTUP_ENABLED,
    DATABASE_RUN_MIGRATIONS_ON_STARTUP,
    FOCUSED_PRODUCT_MODE,
    PUBLIC_API_ORIGIN,
    PUBLIC_WEB_ORIGIN,
    SCHEDULER_RUNNER_ROLE,
    SCHEDULER_STARTUP_ENABLED,
    SERVER_ROLE,
    TRUSTED_HOSTS,
    ALLOWED_ORIGINS,
    PROXY_HEADERS_ENABLED,
)
from backend.app.core.logging_utils import log_event
from backend.app.db.session import init_db
from backend.app.services import start_scheduler, stop_scheduler
from backend.app.services.auth import validate_auth_configuration
from backend.app.services.continuous_learning import start_continuous_learning
from backend.app.services.open_telemetry import bootstrap_open_telemetry
from backend.app.services.stack_validator import log_stack_status
from backend.app.services.workspace_store import initialize_workspace_defaults


def _sync_runtime_credentials(logger: logging.Logger) -> None:
    try:
        from backend.app.services.market_data import sync_alpaca_credentials_from_runtime

        sync_alpaca_credentials_from_runtime()
    except Exception:
        logger.exception("Failed to sync Alpaca credentials from runtime settings.")
    if not FOCUSED_PRODUCT_MODE:
        try:
            from backend.app.services.telegram_sync import sync_telegram_credentials_from_runtime

            sync_telegram_credentials_from_runtime()
        except Exception:
            logger.exception("Failed to sync Telegram credentials from runtime settings.")


def _warm_runtime_caches(logger: logging.Logger) -> None:
    try:
        from backend.app.application.broker.service import get_broker_summary
        from backend.app.api.routes.health import _health_context, _stack_summary
        from backend.app.services.dashboard_hub import (
            get_dashboard_lite,
            get_dashboard_market_widget,
            get_dashboard_ops_widget,
            get_dashboard_portfolio_widget,
        )

        get_broker_summary(refresh=False)
        _health_context()
        _stack_summary()
        get_dashboard_lite()
        get_dashboard_market_widget()
        get_dashboard_portfolio_widget()
        get_dashboard_ops_widget()
        log_event(logger, logging.INFO, "app.runtime_cache_warmup", target="broker_summary,health,dashboard", status="completed")
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "app.runtime_cache_warmup",
            target="broker_summary,health,dashboard",
            status="failed",
            detail=str(exc)[:200],
        )


def startup_application_services(app: FastAPI | None, logger: logging.Logger) -> None:
    validate_auth_configuration()
    _sync_runtime_credentials(logger)
    init_db(run_migrations=DATABASE_RUN_MIGRATIONS_ON_STARTUP)
    otel_status = bootstrap_open_telemetry(app=app)
    try:
        initialize_workspace_defaults()
    except Exception:
        logger.exception("Workspace defaults initialization failed during startup.")

    log_event(
        logger,
        logging.INFO,
        "app.startup",
        role=SERVER_ROLE,
        database_run_migrations_on_startup=DATABASE_RUN_MIGRATIONS_ON_STARTUP,
        scheduler_runner_role=SCHEDULER_RUNNER_ROLE,
        scheduler_startup_enabled=SCHEDULER_STARTUP_ENABLED,
        continuous_learning_runner_role=CONTINUOUS_LEARNING_RUNNER_ROLE,
        continuous_learning_startup_enabled=CONTINUOUS_LEARNING_STARTUP_ENABLED,
        otel_runtime=otel_status.get("runtime"),
        otel_active=otel_status.get("active"),
        public_web_origin=PUBLIC_WEB_ORIGIN or None,
        public_api_origin=PUBLIC_API_ORIGIN or None,
        allowed_origins=ALLOWED_ORIGINS,
        trusted_hosts=TRUSTED_HOSTS,
        proxy_headers_enabled=PROXY_HEADERS_ENABLED,
    )

    try:
        log_stack_status()
    except Exception:
        logger.exception("Stack validation failed (non-fatal).")

    if SCHEDULER_STARTUP_ENABLED:
        try:
            start_scheduler()
        except Exception:
            logger.exception("Scheduler startup failed.")
    elif CONTINUOUS_LEARNING_STARTUP_ENABLED:
        try:
            start_continuous_learning(requested_by="app_startup")
        except Exception:
            logger.exception("Continuous learning startup failed.")

    try:
        threading.Thread(target=_warm_runtime_caches, args=(logger,), name="runtime-cache-warmup", daemon=True).start()
    except Exception:
        logger.exception("Runtime cache warmup thread failed to start.")


def build_lifespan(logger: logging.Logger):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        startup_application_services(app=app, logger=logger)
        try:
            yield
        finally:
            stop_scheduler()

    return lifespan
