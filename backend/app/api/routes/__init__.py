from .ai import router as ai_router
from .metrics import router as metrics_router
from .analyze import router as analyze_router
from .alerts_center import router as alerts_router
from .automation import router as automation_router
from .backtest import router as backtest_router
from .broker import router as broker_router
from .breadth import router as breadth_router
from .continuous_learning import router as continuous_learning_router
from .dashboard import router as dashboard_router
from .execution import router as execution_router
from .events import router as events_router
from .fundamentals import router as fundamentals_router
from .health import router as health_router
from .intelligence import router as intelligence_router
from .journal import router as journal_router
from .jobs import router as jobs_router
from .live import router as live_router
from .macro import router as macro_router
from .position_sizing import router as position_sizing_router
from .portfolio_risk import router as portfolio_risk_router
from .market import router as market_router
from .market_data import router as market_data_router
from .market_terminal import router as market_terminal_router
from .model_lifecycle import router as model_lifecycle_router
from .models_promotion import router as models_promotion_router
from .optimizer import router as optimizer_router
from .operations import router as operations_router
from .paper import router as paper_router
from .portfolio import router as portfolio_router
from .ranking import router as ranking_router
from .risk import router as risk_router
from .scan import router as scan_router
from .scheduler import router as scheduler_router
from .settings import router as settings_router
from .readiness import router as readiness_router
from .smart_automation import router as smart_automation_router
from .stack_status import router as stack_status_router
from .strategy_lab import router as strategy_lab_router
from .training import router as training_router
from .watchlists import router as watchlists_router
from .workspace import router as workspace_router
from .auth import router as auth_router

__all__ = [
    "analyze_router",
    "ai_router",
    "alerts_router",
    "automation_router",
    "backtest_router",
    "broker_router",
    "breadth_router",
    "continuous_learning_router",
    "dashboard_router",
    "execution_router",
    "events_router",
    "fundamentals_router",
    "health_router",
    "intelligence_router",
    "journal_router",
    "jobs_router",
    "live_router",
    "market_router",
    "market_data_router",
    "market_terminal_router",
    "model_lifecycle_router",
    "models_promotion_router",
    "optimizer_router",
    "operations_router",
    "paper_router",
    "portfolio_router",
    "ranking_router",
    "risk_router",
    "scan_router",
    "scheduler_router",
    "settings_router",
    "readiness_router",
    "smart_automation_router",
    "stack_status_router",
    "strategy_lab_router",
    "training_router",
    "watchlists_router",
    "metrics_router",
    "workspace_router",
    "auth_router",
    "macro_router",
    "position_sizing_router",
    "portfolio_risk_router",
]
