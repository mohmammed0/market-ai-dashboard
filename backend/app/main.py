import logging
import threading
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.app.api.routes import (
    ai_chat_router,
    ai_research_router,
    ai_router,
    alerts_router,
    analyze_router,
    auth_router,
    automation_router,
    backtest_router,
    breadth_router,
    broker_router,
    continuous_learning_router,
    dashboard_router,
    events_router,
    execution_router,
    fundamentals_router,
    health_router,
    intelligence_router,
    knowledge_router,
    journal_router,
    jobs_router,
    live_router,
    macro_router,
    market_data_router,
    market_router,
    market_terminal_router,
    metrics_router,
    model_lifecycle_router,
    models_promotion_router,
    notifications_router,
    operations_router,
    optimizer_router,
    paper_router,
    portfolio_risk_router,
    portfolio_router,
    position_sizing_router,
    ranking_router,
    readiness_router,
    risk_router,
    scan_router,
    scheduler_router,
    settings_router,
    smart_automation_router,
    stack_status_router,
    strategy_lab_router,
    training_jobs_worker_router,
    training_router,
    training_worker_router,
    watchlists_router,
    workspace_router,
)
from backend.app.config import (
    ALLOWED_ORIGINS,
    API_TITLE,
    API_VERSION,
    APP_ENV,
    AUTH_ENABLED,
    CONTINUOUS_LEARNING_RUNNER_ROLE,
    CONTINUOUS_LEARNING_STARTUP_ENABLED,
    DATABASE_RUN_MIGRATIONS_ON_STARTUP,
    FOCUSED_PRODUCT_MODE,
    FORWARDED_ALLOW_IPS,
    LOG_LEVEL,
    PROXY_HEADERS_ENABLED,
    PUBLIC_API_ORIGIN,
    PUBLIC_WEB_ORIGIN,
    SCHEDULER_RUNNER_ROLE,
    SCHEDULER_STARTUP_ENABLED,
    SERVER_ROLE,
    TRUSTED_HOSTS,
)
from backend.app.core.logging_utils import configure_logging, log_event
from backend.app.db.session import init_db
from backend.app.services import start_scheduler, stop_scheduler
from backend.app.services.auth import validate_auth_configuration
from backend.app.services.continuous_learning import start_continuous_learning
from backend.app.services.stack_validator import log_stack_status
from backend.app.services.workspace_store import initialize_workspace_defaults

configure_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)

_PUBLIC_PREFIXES = ("/auth", "/health", "/docs", "/openapi.json", "/redoc")


def _is_worker_token_path(path: str) -> bool:
    if path.startswith("/api/training/worker"):
        return True
    if path == "/api/training/jobs/next-queued":
        return True
    return path.startswith("/api/training/jobs/") and (path.endswith("/claim") or path.endswith("/artifact"))


def _sync_runtime_credentials() -> None:
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


def _startup_application_services() -> None:
    validate_auth_configuration()
    _sync_runtime_credentials()
    init_db(run_migrations=DATABASE_RUN_MIGRATIONS_ON_STARTUP)
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
        threading.Thread(target=_warm_runtime_caches, name="runtime-cache-warmup", daemon=True).start()
    except Exception:
        logger.exception("Runtime cache warmup thread failed to start.")


def _warm_runtime_caches() -> None:
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
        log_event(
            logger,
            logging.INFO,
            "app.runtime_cache_warmup",
            target="broker_summary,health,dashboard",
            status="completed",
        )
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "app.runtime_cache_warmup",
            target="broker_summary,health,dashboard",
            status="failed",
            detail=str(exc)[:200],
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    _startup_application_services()
    try:
        yield
    finally:
        stop_scheduler()


def _configure_middlewares(app: FastAPI) -> None:
    if PROXY_HEADERS_ENABLED:
        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=FORWARDED_ALLOW_IPS)

    if TRUSTED_HOSTS and "*" not in TRUSTED_HOSTS:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _register_http_middlewares(app: FastAPI) -> None:
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        """Global auth guard — skip for auth, health, docs, and worker-token endpoints."""
        if not AUTH_ENABLED:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES) or _is_worker_token_path(path):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required. POST /auth/login to get a token."},
            )

        token = auth_header[7:]
        try:
            from backend.app.services.auth import decode_token

            decode_token(token)
        except Exception:
            from starlette.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token."},
            )

        return await call_next(request)

    @app.middleware("http")
    async def request_observer(request: Request, call_next):
        request_id = uuid4().hex[:12]
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "api.request.exception",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                client=None if request.client is None else request.client.host,
                environment=APP_ENV,
                error=str(exc),
            )
            raise

        duration_ms = round((perf_counter() - started) * 1000.0, 2)
        if response.status_code >= 400:
            log_event(
                logger,
                logging.WARNING if response.status_code < 500 else logging.ERROR,
                "api.request.error",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client=None if request.client is None else request.client.host,
            )
        response.headers["X-Request-ID"] = request_id
        return response


def _register_routes(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(ai_router, prefix="/api")
    app.include_router(ai_research_router, prefix="/api")
    app.include_router(analyze_router, prefix="/api")
    app.include_router(alerts_router, prefix="/api")
    app.include_router(automation_router, prefix="/api")
    app.include_router(scan_router, prefix="/api")
    app.include_router(ranking_router, prefix="/api")
    app.include_router(backtest_router, prefix="/api")
    app.include_router(broker_router, prefix="/api")
    app.include_router(breadth_router, prefix="/api")
    app.include_router(continuous_learning_router, prefix="/api")
    app.include_router(execution_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(intelligence_router, prefix="/api")
    app.include_router(knowledge_router, prefix="/api")
    app.include_router(journal_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(market_router, prefix="/api")
    app.include_router(market_data_router, prefix="/api")
    app.include_router(market_terminal_router, prefix="/api")
    app.include_router(model_lifecycle_router, prefix="/api")
    app.include_router(models_promotion_router, prefix="/api")
    app.include_router(optimizer_router, prefix="/api")
    app.include_router(operations_router, prefix="/api")
    app.include_router(paper_router, prefix="/api")
    app.include_router(portfolio_router, prefix="/api")
    app.include_router(risk_router, prefix="/api")
    app.include_router(live_router, prefix="/api")
    app.include_router(scheduler_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(readiness_router, prefix="/api")
    app.include_router(smart_automation_router, prefix="/api")
    app.include_router(stack_status_router, prefix="/api")
    app.include_router(strategy_lab_router, prefix="/api")
    # Worker-alias router must be included BEFORE training_router so that
    # `/api/training/jobs/next-queued` is not shadowed by `/api/training/jobs/{job_id}`.
    app.include_router(training_jobs_worker_router, prefix="/api")
    app.include_router(training_router, prefix="/api")
    app.include_router(training_worker_router, prefix="/api")
    app.include_router(watchlists_router, prefix="/api")
    app.include_router(workspace_router, prefix="/api")
    app.include_router(metrics_router, prefix="/api")
    app.include_router(macro_router, prefix="/api")
    app.include_router(position_sizing_router, prefix="/api")
    app.include_router(portfolio_risk_router, prefix="/api")
    app.include_router(fundamentals_router, prefix="/api")
    app.include_router(notifications_router, prefix="/api")
    app.include_router(ai_chat_router, prefix="/api")


def create_app() -> FastAPI:
    app = FastAPI(title=API_TITLE, version=API_VERSION, lifespan=lifespan)
    _configure_middlewares(app)
    _register_http_middlewares(app)
    _register_routes(app)
    return app


app = create_app()
