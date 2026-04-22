from fastapi import FastAPI

from backend.app.api.routes import (
    ai_chat_router,
    ai_research_router,
    ai_router,
    alerts_router,
    analysis_engines_router,
    analyze_router,
    auth_router,
    automation_router,
    backtest_router,
    breadth_router,
    broker_router,
    continuous_learning_router,
    dashboard_router,
    diagnostics_router,
    events_router,
    execution_router,
    fundamentals_router,
    health_router,
    intelligence_router,
    jobs_router,
    journal_router,
    knowledge_router,
    kronos_router,
    live_router,
    macro_router,
    market_data_router,
    market_readiness_router,
    market_router,
    market_session_router,
    market_terminal_router,
    metrics_router,
    model_lifecycle_router,
    models_promotion_router,
    notifications_router,
    operations_router,
    optimizer_router,
    portfolio_brain_router,
    portfolio_router,
    portfolio_risk_router,
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
    trading_router,
    training_jobs_worker_router,
    training_router,
    training_worker_router,
    watchlists_router,
    workspace_router,
)


def register_routes(app: FastAPI) -> None:
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(diagnostics_router, prefix="/api")
    app.include_router(portfolio_brain_router, prefix="/api")
    app.include_router(analysis_engines_router, prefix="/api")
    app.include_router(kronos_router, prefix="/api")
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
    app.include_router(market_session_router, prefix="/api")
    app.include_router(market_readiness_router, prefix="/api")
    app.include_router(market_terminal_router, prefix="/api")
    app.include_router(model_lifecycle_router, prefix="/api")
    app.include_router(models_promotion_router, prefix="/api")
    app.include_router(optimizer_router, prefix="/api")
    app.include_router(operations_router, prefix="/api")
    app.include_router(trading_router, prefix="/api")
    app.include_router(portfolio_router, prefix="/api")
    app.include_router(risk_router, prefix="/api")
    app.include_router(live_router, prefix="/api")
    app.include_router(scheduler_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(readiness_router, prefix="/api")
    app.include_router(smart_automation_router, prefix="/api")
    app.include_router(stack_status_router, prefix="/api")
    app.include_router(strategy_lab_router, prefix="/api")
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
