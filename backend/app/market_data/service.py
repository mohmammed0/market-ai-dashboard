"""Market-data domain service facade.

This boundary owns market facts, historical bars, quote snapshots, and
universe-facing market data operations. Current implementations delegate to
the existing services so callers can migrate incrementally.
"""

from backend.app.events.publisher import publish_event
from backend.app.repositories.platform_events import PlatformEventRepository
from backend.app.services.market_data import (
    fetch_quote_snapshots,
    incremental_update,
    load_history,
)
from backend.app.services.storage import session_scope
from backend.app.services.market_universe import (
    get_market_overview,
    get_market_symbol_snapshot,
    get_market_universe_facets,
    list_currency_references,
    refresh_market_universe,
    resolve_universe_preset,
    search_market_universe,
)
from core.market_data_providers import get_market_data_provider_status
from packages.contracts.events.topics import (
    MARKET_NORMALIZED_CANDLE_UPDATED,
    MARKET_NORMALIZED_QUOTE_UPDATED,
)


def _record_market_provider_health(provider_status: dict) -> None:
    providers = provider_status.get("providers", []) if isinstance(provider_status, dict) else []
    if not providers:
        return
    with session_scope() as session:
        repo = PlatformEventRepository(session)
        for provider in providers:
            provider_name = str(provider.get("provider") or provider.get("name") or "unknown")
            healthy = str(provider.get("status") or "").strip().lower() in {"ok", "ready", "healthy"}
            detail = str(provider.get("detail") or provider.get("message") or "")
            repo.record_provider_health(
                provider_type="market_data",
                provider_name=provider_name,
                healthy=healthy,
                detail=detail or None,
                payload=provider,
            )


def fetch_and_publish_quote_snapshots(symbols: list[str]) -> dict:
    snapshot = fetch_quote_snapshots(symbols)
    for item in snapshot.get("items", []):
        publish_event(
            event_type=MARKET_NORMALIZED_QUOTE_UPDATED,
            producer="market_data_service",
            payload=item,
            correlation_id=f"market-quote-{str(item.get('symbol') or '').strip().upper()}",
        )
    _record_market_provider_health(get_market_data_provider_status())
    return snapshot


def load_and_publish_history(*, symbol: str, start_date=None, end_date=None, interval: str = "1d", persist: bool = True) -> dict:
    payload = load_history(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        persist=persist,
    )
    publish_event(
        event_type=MARKET_NORMALIZED_CANDLE_UPDATED,
        producer="market_data_service",
        payload={
            "symbol": payload.get("symbol"),
            "interval": payload.get("interval"),
            "rows": payload.get("rows"),
            "provider": payload.get("provider"),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "latest_bar": (payload.get("items") or [{}])[-1] if payload.get("items") else None,
        },
        correlation_id=f"market-history-{str(payload.get('symbol') or symbol).strip().upper()}-{interval}",
    )
    _record_market_provider_health(get_market_data_provider_status())
    return payload


def incremental_update_and_publish(symbol: str) -> dict:
    payload = incremental_update(symbol)
    publish_event(
        event_type=MARKET_NORMALIZED_CANDLE_UPDATED,
        producer="market_data_service",
        payload={
            "symbol": payload.get("symbol"),
            "interval": payload.get("interval"),
            "rows": payload.get("rows"),
            "provider": payload.get("provider"),
            "latest_bar": (payload.get("items") or [{}])[-1] if payload.get("items") else None,
        },
        correlation_id=f"market-update-{str(payload.get('symbol') or symbol).strip().upper()}",
    )
    _record_market_provider_health(get_market_data_provider_status())
    return payload

__all__ = [
    "fetch_quote_snapshots",
    "fetch_and_publish_quote_snapshots",
    "get_market_data_provider_status",
    "get_market_overview",
    "get_market_symbol_snapshot",
    "get_market_universe_facets",
    "list_currency_references",
    "incremental_update_and_publish",
    "incremental_update",
    "load_and_publish_history",
    "load_history",
    "refresh_market_universe",
    "resolve_universe_preset",
    "search_market_universe",
]
