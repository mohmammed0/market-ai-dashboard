"""Central route registration map for FastAPI routers.

This keeps route ownership explicit and separates canonical operator routes from
legacy/compatibility surfaces while preserving existing paths.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, FastAPI

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
    journal_router,
    jobs_router,
    knowledge_router,
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

API_PREFIX = "/api"


@dataclass(frozen=True)
class RouteRegistration:
    key: str
    router: APIRouter
    group: str
    canonical: bool
    prefix: str | None = API_PREFIX


PUBLIC_ROUTES: tuple[RouteRegistration, ...] = (
    RouteRegistration("health", health_router, group="platform", canonical=True, prefix=None),
    RouteRegistration("auth", auth_router, group="platform", canonical=True, prefix=None),
)

CANONICAL_API_ROUTES: tuple[RouteRegistration, ...] = (
    RouteRegistration("dashboard", dashboard_router, group="operator", canonical=True),
    RouteRegistration("ai", ai_router, group="ai", canonical=True),
    RouteRegistration("ai_research", ai_research_router, group="ai", canonical=True),
    RouteRegistration("ai_chat", ai_chat_router, group="ai", canonical=True),
    RouteRegistration("intelligence", intelligence_router, group="ai", canonical=True),
    RouteRegistration("live", live_router, group="market_data", canonical=True),
    RouteRegistration("market", market_router, group="market_data", canonical=True),
    RouteRegistration("market_data", market_data_router, group="market_data", canonical=True),
    RouteRegistration("market_terminal", market_terminal_router, group="market_data", canonical=True),
    RouteRegistration("ranking", ranking_router, group="strategy", canonical=True),
    RouteRegistration("execution", execution_router, group="execution", canonical=True),
    RouteRegistration("broker", broker_router, group="broker", canonical=True),
    RouteRegistration("portfolio", portfolio_router, group="portfolio", canonical=True),
    RouteRegistration("settings", settings_router, group="platform", canonical=True),
    RouteRegistration("metrics", metrics_router, group="platform", canonical=True),
    RouteRegistration("stack_status", stack_status_router, group="platform", canonical=True),
    RouteRegistration("workspace", workspace_router, group="platform", canonical=True),
)

COMPATIBILITY_API_ROUTES: tuple[RouteRegistration, ...] = (
    RouteRegistration("analyze", analyze_router, group="compat", canonical=False),
    RouteRegistration("alerts", alerts_router, group="compat", canonical=False),
    RouteRegistration("automation", automation_router, group="automation", canonical=False),
    RouteRegistration("scan", scan_router, group="compat", canonical=False),
    RouteRegistration("backtest", backtest_router, group="compat", canonical=False),
    RouteRegistration("breadth", breadth_router, group="compat", canonical=False),
    RouteRegistration("continuous_learning", continuous_learning_router, group="research", canonical=False),
    RouteRegistration("events", events_router, group="research", canonical=False),
    RouteRegistration("knowledge", knowledge_router, group="research", canonical=False),
    RouteRegistration("journal", journal_router, group="compat", canonical=False),
    RouteRegistration("jobs", jobs_router, group="platform", canonical=False),
    RouteRegistration("model_lifecycle", model_lifecycle_router, group="research", canonical=False),
    RouteRegistration("models_promotion", models_promotion_router, group="research", canonical=False),
    RouteRegistration("optimizer", optimizer_router, group="strategy", canonical=False),
    RouteRegistration("operations", operations_router, group="platform", canonical=False),
    RouteRegistration("paper", paper_router, group="compat", canonical=False),
    RouteRegistration("risk", risk_router, group="risk", canonical=False),
    RouteRegistration("scheduler", scheduler_router, group="automation", canonical=False),
    RouteRegistration("readiness", readiness_router, group="platform", canonical=False),
    RouteRegistration("smart_automation", smart_automation_router, group="automation", canonical=False),
    RouteRegistration("strategy_lab", strategy_lab_router, group="strategy", canonical=False),
    # Worker alias must be mounted before training routes.
    RouteRegistration("training_jobs_worker", training_jobs_worker_router, group="training", canonical=False),
    RouteRegistration("training", training_router, group="training", canonical=False),
    RouteRegistration("training_worker", training_worker_router, group="training", canonical=False),
    RouteRegistration("watchlists", watchlists_router, group="compat", canonical=False),
    RouteRegistration("macro", macro_router, group="compat", canonical=False),
    RouteRegistration("position_sizing", position_sizing_router, group="risk", canonical=False),
    RouteRegistration("portfolio_risk", portfolio_risk_router, group="risk", canonical=False),
    RouteRegistration("fundamentals", fundamentals_router, group="research", canonical=False),
    RouteRegistration("notifications", notifications_router, group="platform", canonical=False),
)

ALL_ROUTE_REGISTRATIONS: tuple[RouteRegistration, ...] = (
    *PUBLIC_ROUTES,
    *CANONICAL_API_ROUTES,
    *COMPATIBILITY_API_ROUTES,
)


def register_all_routes(app: FastAPI) -> None:
    for registration in ALL_ROUTE_REGISTRATIONS:
        if registration.prefix:
            app.include_router(registration.router, prefix=registration.prefix)
        else:
            app.include_router(registration.router)


def route_registry_snapshot() -> list[dict]:
    """Expose route metadata for diagnostics/docs/tests."""
    return [
        {
            "key": row.key,
            "group": row.group,
            "canonical": row.canonical,
            "prefix": row.prefix,
        }
        for row in ALL_ROUTE_REGISTRATIONS
    ]
