import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from backend.app.api.routes import (
    ai_router,
    analyze_router,
    alerts_router,
    metrics_router,
    automation_router,
    backtest_router,
    broker_router,
    breadth_router,
    continuous_learning_router,
    dashboard_router,
    execution_router,
    health_router,
    intelligence_router,
    journal_router,
    jobs_router,
    live_router,
    market_router,
    market_data_router,
    market_terminal_router,
    model_lifecycle_router,
    models_promotion_router,
    optimizer_router,
    operations_router,
    paper_router,
    portfolio_router,
    ranking_router,
    risk_router,
    scheduler_router,
    settings_router,
    scan_router,
    readiness_router,
    smart_automation_router,
    stack_status_router,
    strategy_lab_router,
    training_router,
    watchlists_router,
    workspace_router,
    events_router,
    auth_router,
)
from backend.app.config import (
    ALLOWED_ORIGINS,
    API_TITLE,
    API_VERSION,
    APP_ENV,
    AUTH_ENABLED,
    DATABASE_RUN_MIGRATIONS_ON_STARTUP,
    CONTINUOUS_LEARNING_RUNNER_ROLE,
    CONTINUOUS_LEARNING_STARTUP_ENABLED,
    LOG_LEVEL,
    PROXY_HEADERS_ENABLED,
    PUBLIC_API_ORIGIN,
    PUBLIC_WEB_ORIGIN,
    SCHEDULER_RUNNER_ROLE,
    SCHEDULER_STARTUP_ENABLED,
    SERVER_ROLE,
    TRUSTED_HOSTS,
    FORWARDED_ALLOW_IPS,
)
from backend.app.core.logging_utils import configure_logging, log_event
from backend.app.db.session import init_db
from backend.app.services.continuous_learning import start_continuous_learning
from backend.app.services.stack_validator import log_stack_status
from backend.app.services.workspace_store import initialize_workspace_defaults
from backend.app.services import start_scheduler, stop_scheduler


configure_logging(LOG_LEVEL)
app = FastAPI(title=API_TITLE, version=API_VERSION)
logger = logging.getLogger(__name__)

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


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Global auth guard — skip for auth, health, and docs endpoints."""
    if not AUTH_ENABLED:
        return await call_next(request)

    path = request.url.path
    # Public paths that don't need auth
    public_prefixes = ("/auth", "/health", "/docs", "/openapi.json", "/redoc")
    if any(path.startswith(p) for p in public_prefixes):
        return await call_next(request)

    # OPTIONS requests for CORS
    if request.method == "OPTIONS":
        return await call_next(request)

    # Check Authorization header
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


@app.on_event("startup")
def on_startup():
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
    # Validate live stack components (non-blocking, informational)
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


@app.on_event("shutdown")
def on_shutdown():
    stop_scheduler()


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(dashboard_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
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
app.include_router(training_router, prefix="/api")
app.include_router(watchlists_router, prefix="/api")
app.include_router(workspace_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")
