from __future__ import annotations

from backend.app.application.broker.service import get_broker_summary
from backend.app.application.model_lifecycle.service import get_promotion_status, list_model_runs
from backend.app.application.portfolio.service import get_portfolio_exposure
from backend.app.config import DEFAULT_SAMPLE_SYMBOLS
from backend.app.services import get_cache, get_scheduler_status
from backend.app.services.automation_hub import get_automation_status
from backend.app.services.breadth_engine import compute_market_breadth, compute_sector_rotation
from backend.app.services.cache import get_cache_status
from backend.app.services.dashboard_summary_helpers import build_sample_scan_snapshot, safe_service_call
from backend.app.services.continuous_learning import get_continuous_learning_status
from backend.app.services.events_calendar import fetch_market_events
from backend.app.services.market_data import fetch_quote_snapshots
from backend.app.services.risk_engine import get_risk_dashboard
from backend.app.services.smart_watchlists import build_dynamic_watchlists
from core.market_data_providers import get_market_data_provider_status
from core.ranking_service import summarize_long_short


def get_dashboard_summary():
    cache = get_cache()

    def build_payload():
        sample_symbols = DEFAULT_SAMPLE_SYMBOLS
        ranked_rows, sample_analyze, signal_counts = build_sample_scan_snapshot(sample_symbols)

        return {
            "backend_health": {"status": "ok"},
            "sample_analyze": sample_analyze,
            "market_data": fetch_quote_snapshots(sample_symbols),
            "market_data_status": safe_service_call(get_market_data_provider_status, {"primary_provider": "unavailable", "provider_chain": [], "providers": []}),
            "breadth": safe_service_call(lambda: compute_market_breadth(preset="ALL_US_EQUITIES", limit=25), {"sample_size": 0, "leaders": [], "laggards": []}),
            "sector_rotation": safe_service_call(compute_sector_rotation, {"leaders": [], "laggards": [], "ranking": []}),
            "watchlists": safe_service_call(lambda: build_dynamic_watchlists(preset="ALL_US_EQUITIES", limit=20), {"momentum_leaders": [], "unusual_volume": [], "signal_focus": []}),
            "portfolio": safe_service_call(get_portfolio_exposure, {"summary": {"open_positions": 0, "total_market_value": 0.0}, "positions": [], "warnings": []}),
            "risk": safe_service_call(get_risk_dashboard, {"portfolio_warnings": [], "gross_exposure_pct": 0.0}),
            "broker": safe_service_call(get_broker_summary, {"provider": "none", "enabled": False, "positions": [], "orders": [], "detail": "Broker integration unavailable."}),
            "automation": safe_service_call(lambda: get_automation_status(limit=10), {"recent_runs": [], "latest_artifacts": []}),
            "continuous_learning": safe_service_call(lambda: get_continuous_learning_status(limit=5), {"state": {}, "recent_runs": [], "recent_artifacts": []}),
            "events": safe_service_call(lambda: fetch_market_events(symbols=sample_symbols, limit=10), {"items": [], "note": "Event provider unavailable."}),
            "models": {
                "ml_active": any(row.get("is_active") for row in list_model_runs("ml")),
                "dl_active": any(row.get("is_active") for row in list_model_runs("dl")),
                "promotion": safe_service_call(get_promotion_status, {"items": [], "recommended": [], "active_candidates": []}),
            },
            "scheduler": get_scheduler_status(),
            "scan_ranking": {
                "total_ranked": len(ranked_rows),
                "top_pick": ranked_rows[0].get("instrument") if ranked_rows else None,
                "signal_counts": signal_counts,
                "summary": summarize_long_short(ranked_rows, limit=3),
            },
            "cache": get_cache_status(),
        }

    return cache.get_or_set("dashboard:summary", build_payload, ttl_seconds=30)
