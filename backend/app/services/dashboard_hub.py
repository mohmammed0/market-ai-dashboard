from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.application.broker.service import get_broker_summary
from backend.app.application.execution.service import get_signal_history
from backend.app.application.model_lifecycle.service import get_promotion_status, list_model_runs
from backend.app.application.portfolio.service import build_portfolio_snapshot_payload, get_portfolio_exposure
from backend.app.config import (
    DEFAULT_ANALYSIS_LOOKBACK_DAYS,
    DEFAULT_SAMPLE_SYMBOLS,
    DEFAULT_TRACKED_SYMBOL_LIMIT,
    FOCUSED_PRODUCT_MODE,
    LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
    LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS,
    LIGHTWEIGHT_EXPERIMENT_MODE,
    LIGHTWEIGHT_EXPERIMENT_NEWS_LIMIT,
)
from backend.app.domain.portfolio.contracts import PortfolioSnapshot, PortfolioSnapshotV1, PortfolioViewSummary
from backend.app.models.market import NewsRecord
from backend.app.schemas import DashboardLiteResponse, DashboardWidgetResponse
from backend.app.services import get_cache, get_scheduler_status
from backend.app.services.automation_hub import get_automation_status
from backend.app.services.breadth_engine import compute_market_breadth, compute_sector_rotation
from backend.app.services.cache import get_cache_status
from backend.app.services.dashboard_summary_helpers import (
    build_focused_opportunity_snapshot,
    build_sample_scan_snapshot,
    safe_service_call,
)
from backend.app.services.continuous_learning import get_continuous_learning_status
from backend.app.services.events_calendar import fetch_market_events
from backend.app.services.llm_gateway import get_llm_status
from backend.app.services.market_data import fetch_quote_snapshots
from backend.app.services.market_universe import get_market_overview
from backend.app.services.news_feed import serialize_news_record
from backend.app.services.risk_engine import get_risk_dashboard
from backend.app.services.runtime_settings import get_auto_trading_config
from backend.app.services.storage import session_scope
from backend.app.services.smart_watchlists import build_dynamic_watchlists
from backend.app.services.telegram_sync import sync_telegram_credentials_from_runtime
from core.market_data_providers import get_market_data_provider_status
from core.telegram_notifier import get_telegram_status
from core.ranking_service import summarize_long_short


def _build_opportunities_from_signal_history(signal_items: list[dict], sample_symbols: list[str]) -> list[dict]:
    sample_lookup = {str(symbol or "").strip().upper() for symbol in sample_symbols if str(symbol or "").strip()}
    selected: list[dict] = []
    seen: set[str] = set()

    for item in signal_items:
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol or (sample_lookup and symbol not in sample_lookup) or symbol in seen:
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        analysis = payload.get("analysis") if isinstance(payload, dict) else {}
        signal_view = payload.get("signal_view") if isinstance(payload, dict) else {}
        signal = str(item.get("signal") or signal_view.get("signal") or "HOLD").upper()
        selected.append({
            "symbol": symbol,
            "signal": signal,
            "confidence": float(item.get("confidence") or signal_view.get("confidence") or 0.0),
            "score": analysis.get("enhanced_combined_score", analysis.get("combined_score")),
            "reason": item.get("reasoning") or signal_view.get("reasoning") or analysis.get("ai_summary") or analysis.get("best_setup") or analysis.get("setup_type"),
            "setup_type": analysis.get("setup_type"),
            "best_setup": analysis.get("best_setup"),
            "risk_label": analysis.get("trend_mode") or analysis.get("market_regime") or "RANGE",
            "action": signal,
        })
        seen.add(symbol)
        if len(selected) >= 6:
            break

    priority = {"BUY": 0, "HOLD": 1, "SELL": 2}
    return sorted(
        selected,
        key=lambda row: (priority.get(str(row.get("signal") or "HOLD").upper(), 9), -float(row.get("confidence") or 0.0)),
    )[:6]


def get_dashboard_summary():
    cache = get_cache()

    def build_payload():
        sample_limit = LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS if LIGHTWEIGHT_EXPERIMENT_MODE else DEFAULT_TRACKED_SYMBOL_LIMIT
        sample_symbols = DEFAULT_SAMPLE_SYMBOLS[:min(sample_limit, 4 if FOCUSED_PRODUCT_MODE else sample_limit)]
        ranked_rows, sample_analyze, signal_counts = build_sample_scan_snapshot(sample_symbols)
        focused_payload = {
            "backend_health": {"status": "ok", "focused_product_mode": True},
            "sample_analyze": sample_analyze,
            "market_data": fetch_quote_snapshots(sample_symbols),
            "market_data_status": safe_service_call(get_market_data_provider_status, {"primary_provider": "unavailable", "provider_chain": [], "providers": []}),
            "portfolio": safe_service_call(get_portfolio_exposure, {"summary": {"open_positions": 0, "total_market_value": 0.0}, "positions": [], "warnings": []}),
            "risk": safe_service_call(get_risk_dashboard, {"portfolio_warnings": [], "gross_exposure_pct": 0.0}),
            "broker": safe_service_call(get_broker_summary, {"provider": "none", "enabled": False, "positions": [], "orders": [], "detail": "Broker integration unavailable."}),
            "scheduler": get_scheduler_status(),
            "scan_ranking": {
                "total_ranked": len(ranked_rows),
                "top_pick": ranked_rows[0].get("instrument") if ranked_rows else None,
                "signal_counts": signal_counts,
                "summary": summarize_long_short(ranked_rows, limit=3),
            },
            "cache": get_cache_status(),
            "product_scope": {
                "tracked_symbols_limit": sample_limit,
                "analysis_lookback_days": DEFAULT_ANALYSIS_LOOKBACK_DAYS,
                "news_enabled": True,
                "lightweight_ml": True,
                "lightweight_llm": True,
                "lightweight_experiment_mode": bool(LIGHTWEIGHT_EXPERIMENT_MODE),
                "dl_enabled": bool(LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL),
                "sample_symbols": sample_symbols,
            },
        }
        if FOCUSED_PRODUCT_MODE:
            return focused_payload

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

    return cache.get_or_set("dashboard:summary", build_payload, ttl_seconds=300)


def _empty_portfolio_snapshot(detail: str = "Portfolio snapshot unavailable.") -> PortfolioSnapshotV1:
    generated_at = datetime.now(timezone.utc)
    return PortfolioSnapshotV1(
        generated_at=generated_at,
        active_source="internal_paper",
        source_type="internal",
        source_label="Internal Simulated Paper",
        broker_connected=False,
        summary=PortfolioViewSummary(),
        positions=[],
        items=[],
        orders=[],
        open_orders=[],
        trades=[],
        broker_status={
            "provider": "none",
            "enabled": False,
            "configured": False,
            "sdk_installed": False,
            "connected": False,
            "mode": "paper",
            "paper": True,
            "live_execution_enabled": False,
            "order_submission_enabled": False,
            "detail": detail,
        },
        broker_account=None,
        source_summaries=[],
        canonical_snapshot=PortfolioSnapshot(
            generated_at=generated_at,
            positions=[],
            sources=[],
            total_market_value=0.0,
            total_unrealized_pnl=0.0,
        ),
    )


def _today_news_payload(limit: int = 8) -> dict:
    target_date = datetime.now(timezone.utc).date()
    day_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
    day_end = day_start + timedelta(days=1)
    with session_scope() as session:
        rows = (
            session.query(NewsRecord)
            .filter(NewsRecord.captured_at >= day_start, NewsRecord.captured_at < day_end)
            .order_by(NewsRecord.captured_at.desc())
            .limit(limit)
            .all()
        )
    return {
        "date": str(target_date),
        "limit": limit,
        "items": [serialize_news_record(row) for row in rows],
    }


def _telegram_status_payload() -> dict:
    sync_telegram_credentials_from_runtime(force_refresh=False)
    return get_telegram_status()


def get_dashboard_lite() -> DashboardLiteResponse:
    cache = get_cache()

    def build_payload() -> dict:
        sample_limit = LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS if LIGHTWEIGHT_EXPERIMENT_MODE else DEFAULT_TRACKED_SYMBOL_LIMIT
        sample_symbols = [symbol for symbol in DEFAULT_SAMPLE_SYMBOLS[:sample_limit] if str(symbol).strip()]
        recent_signals_full = safe_service_call(lambda: get_signal_history(limit=max(len(sample_symbols) * 3, 24), compact=False), {"items": []})
        recent_signals_compact = safe_service_call(lambda: get_signal_history(limit=8, compact=True), {"items": []})
        recent_signal_items = recent_signals_full.get("items", []) if isinstance(recent_signals_full, dict) else []
        if LIGHTWEIGHT_EXPERIMENT_MODE:
            top_opportunities = safe_service_call(lambda: build_focused_opportunity_snapshot(sample_symbols), [])
        else:
            top_opportunities = _build_opportunities_from_signal_history(recent_signal_items, sample_symbols)

        if not top_opportunities:
            ranked_rows, _, _signal_counts = build_sample_scan_snapshot(sample_symbols)
            for row in ranked_rows[:6]:
                symbol = row.get("instrument") or row.get("symbol")
                signal = str(row.get("enhanced_signal") or row.get("smart_signal") or row.get("signal") or "HOLD").upper()
                top_opportunities.append({
                    "symbol": symbol,
                    "signal": signal,
                    "confidence": float(row.get("confidence") or row.get("smart_confidence") or 0.0),
                    "score": row.get("enhanced_combined_score", row.get("combined_score")),
                    "reason": row.get("ai_summary") or row.get("best_setup") or row.get("setup_type") or row.get("reasons"),
                    "setup_type": row.get("setup_type"),
                    "best_setup": row.get("best_setup"),
                    "risk_label": row.get("trend_mode") or row.get("market_regime") or "RANGE",
                    "action": signal,
                })
        portfolio_snapshot = safe_service_call(
            build_portfolio_snapshot_payload,
            _empty_portfolio_snapshot(),
        )
        if not isinstance(portfolio_snapshot, PortfolioSnapshotV1):
            portfolio_snapshot = _empty_portfolio_snapshot("Portfolio snapshot returned an unexpected payload.")
        return DashboardLiteResponse(
            generated_at=datetime.now(timezone.utc),
            ai_status=safe_service_call(
                get_llm_status,
                {"active_provider": "ollama", "effective_status": "unavailable", "effective_provider": None},
            ),
            portfolio_snapshot=portfolio_snapshot,
            market_overview=safe_service_call(get_market_overview, {"indices": [], "watchlists": [], "movers": []}),
            news=safe_service_call(
                lambda: _today_news_payload(limit=LIGHTWEIGHT_EXPERIMENT_NEWS_LIMIT if LIGHTWEIGHT_EXPERIMENT_MODE else 8),
                {"date": None, "items": []},
            ),
            signals=recent_signals_compact if isinstance(recent_signals_compact, dict) else {"items": []},
            opportunities={
                "tracked_symbols": sample_symbols,
                "items": top_opportunities,
                "count": len(top_opportunities),
            },
            product_scope={
                "focused_product_mode": bool(FOCUSED_PRODUCT_MODE),
                "lightweight_experiment_mode": bool(LIGHTWEIGHT_EXPERIMENT_MODE),
                "ml_enabled": True,
                "dl_enabled": bool(LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL),
                "news_pipeline_enabled": True,
                "lightweight_llm_enabled": True,
                "tracked_symbols_limit": sample_limit,
                "analysis_lookback_days": DEFAULT_ANALYSIS_LOOKBACK_DAYS,
                "sample_symbols": sample_symbols,
            },
            auto_trading=safe_service_call(get_auto_trading_config, {"auto_trading_enabled": False, "ready": False}),
            automation={},
            telegram={},
        ).model_dump(mode="json")

    lite_ttl_seconds = 900 if LIGHTWEIGHT_EXPERIMENT_MODE else 120
    cached_payload = cache.get_or_set("dashboard:lite", build_payload, ttl_seconds=lite_ttl_seconds)
    return DashboardLiteResponse.model_validate(cached_payload)


def get_dashboard_market_widget() -> DashboardWidgetResponse:
    cache = get_cache()

    def build_payload() -> DashboardWidgetResponse:
        return DashboardWidgetResponse(
            widget="market",
            generated_at=datetime.now(timezone.utc),
            data={
                "market_overview": safe_service_call(get_market_overview, {"indices": [], "watchlists": [], "movers": []}),
                "news": safe_service_call(
                    lambda: _today_news_payload(limit=LIGHTWEIGHT_EXPERIMENT_NEWS_LIMIT if LIGHTWEIGHT_EXPERIMENT_MODE else 8),
                    {"date": None, "items": []},
                ),
            },
        )

    return build_payload()


def get_dashboard_portfolio_widget() -> DashboardWidgetResponse:
    cache = get_cache()

    def build_payload() -> DashboardWidgetResponse:
        return DashboardWidgetResponse(
            widget="portfolio",
            generated_at=datetime.now(timezone.utc),
            data={
                "portfolio_snapshot": safe_service_call(build_portfolio_snapshot_payload, _empty_portfolio_snapshot()),
                "signals": safe_service_call(lambda: get_signal_history(limit=8), {"items": []}),
            },
        )

    return build_payload()


def get_dashboard_ops_widget() -> DashboardWidgetResponse:
    cache = get_cache()

    def build_payload() -> DashboardWidgetResponse:
        if FOCUSED_PRODUCT_MODE:
            return DashboardWidgetResponse(
                widget="ops",
                generated_at=datetime.now(timezone.utc),
                data={
                    "ai_status": safe_service_call(
                        get_llm_status,
                        {"active_provider": "ollama", "effective_status": "unavailable", "effective_provider": None},
                    ),
                    "auto_trading": safe_service_call(get_auto_trading_config, {"auto_trading_enabled": False, "ready": False}),
                    "scheduler": get_scheduler_status(),
                    "focused_product_mode": True,
                },
            )
        return DashboardWidgetResponse(
            widget="ops",
            generated_at=datetime.now(timezone.utc),
            data={
                "ai_status": safe_service_call(
                    get_llm_status,
                    {"active_provider": "ollama", "effective_status": "unavailable", "effective_provider": None},
                ),
                "auto_trading": safe_service_call(get_auto_trading_config, {"auto_trading_enabled": False, "ready": False}),
                "automation": safe_service_call(lambda: get_automation_status(limit=6), {"recent_jobs": [], "jobs": []}),
                "telegram": safe_service_call(_telegram_status_payload, {"configured": False, "bot_token_set": False, "chat_id_set": False}),
            },
        )

    return build_payload()
