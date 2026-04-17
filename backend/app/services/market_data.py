from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import logging
import os

import pandas as pd
from sqlalchemy import desc

from backend.app.config import (
    DEFAULT_SAMPLE_SYMBOLS,
    DEFAULT_TRACKED_SYMBOL_LIMIT,
    LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS,
    LIGHTWEIGHT_EXPERIMENT_MODE,
)
from backend.app.models import FeatureSnapshot, OhlcvBar, QuoteSnapshot
from backend.app.services import get_cache
from backend.app.services.storage import dumps_json, loads_json, session_scope
from core.market_data_providers import fetch_snapshot_from_providers, get_market_data_provider_status
from core.source_data import load_symbol_source_data, normalize_symbol
from core.runtime_paths import SOURCE_CACHE_DIR


def sync_alpaca_credentials_from_runtime() -> None:
    """Pull Alpaca credentials from the broker runtime config (DB) into os.environ
    if the market-data env vars are not already set.  Called once at backend startup
    so that AlpacaMarketDataProvider.configured() returns True when keys were entered
    via the Settings UI rather than hard-coded in environment variables."""
    if os.getenv("ALPACA_MARKET_DATA_API_KEY") or os.getenv("ALPACA_API_KEY"):
        return  # already supplied via environment; nothing to do
    try:
        from backend.app.services.runtime_settings import get_alpaca_runtime_config
        config = get_alpaca_runtime_config()
        api_key = (config.get("api_key") or "").strip()
        secret_key = (config.get("secret_key") or "").strip()
        if api_key and secret_key:
            # Set both the specific market-data keys and the generic broker keys
            # so that _alpaca_api_key() finds them regardless of which env var is checked.
            os.environ["ALPACA_MARKET_DATA_API_KEY"] = api_key
            os.environ["ALPACA_MARKET_DATA_SECRET_KEY"] = secret_key
            os.environ["ALPACA_API_KEY"] = api_key
            os.environ["ALPACA_SECRET_KEY"] = secret_key
            logger.info(
                "market_data.alpaca_credentials_synced_from_runtime "
                "source=%s", config.get("api_key_source", "db")
            )
    except Exception as exc:
        logger.warning("market_data.alpaca_credentials_sync_failed error=%s", exc)

_DEFAULT_SYMBOL_LIMIT = LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS if LIGHTWEIGHT_EXPERIMENT_MODE else DEFAULT_TRACKED_SYMBOL_LIMIT
DEFAULT_SYMBOLS = DEFAULT_SAMPLE_SYMBOLS[:_DEFAULT_SYMBOL_LIMIT] or ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "SPY", "QQQ"]
SOURCE_DIR = SOURCE_CACHE_DIR
logger = logging.getLogger(__name__)


def _cache():
    return get_cache()


def _history_cache_ttl(interval: str) -> int:
    normalized = str(interval or "1d").strip().lower()
    if normalized in {"1s", "5s", "15s", "30s", "1m", "2m", "5m"}:
        return 15
    if normalized in {"15m", "30m", "60m", "90m", "1h", "4h"}:
        return 45
    return 300


def _snapshot_cache_ttl(include_profile: bool) -> int:
    return 8 if include_profile else 5


def _history_cache_key(symbol: str, start_date=None, end_date=None, interval="1d") -> str:
    return f"market:history:{normalize_symbol(symbol)}:{start_date or '*'}:{end_date or '*'}:{interval}"


def _snapshot_cache_key(symbols: list[str], include_profile: bool) -> str:
    joined = ",".join(sorted(normalize_symbol(symbol) for symbol in symbols))
    return f"market:snapshot:{int(bool(include_profile))}:{joined}"


def _recent_snapshot(symbol: str, max_age_seconds: int = 12) -> dict | None:
    cutoff = datetime.utcnow() - timedelta(seconds=max(int(max_age_seconds), 1))
    with session_scope() as session:
        row = (
            session.query(QuoteSnapshot)
            .filter(QuoteSnapshot.symbol == symbol, QuoteSnapshot.captured_at >= cutoff)
            .order_by(desc(QuoteSnapshot.captured_at))
            .first()
        )
        if row is None:
            return None
        payload = loads_json(row.payload_json, default={})
        if not payload:
            return None
        return payload


def _load_local_csv(symbol: str, start_date=None, end_date=None):
    try:
        result = load_symbol_source_data(symbol, start_date=start_date, end_date=end_date, allow_network=False, persist_on_fetch=False)
        if result.frame is None or result.frame.empty:
            return pd.DataFrame()
        return result.frame.rename(columns={"date": "datetime"})
    except Exception as exc:
        detail = " ".join(str(exc).split()) or exc.__class__.__name__
        logger.warning("market_data.local_snapshot_load_failed symbol=%s detail=%s", symbol, detail)
        return pd.DataFrame()


def _build_local_snapshot(symbol: str) -> dict | None:
    df = _load_local_csv(symbol)
    if df.empty:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    change = float(last["close"]) - float(prev["close"])
    return {
        "symbol": symbol,
        "price": round(float(last["close"]), 4),
        "prev_close": round(float(prev["close"]), 4),
        "change": round(change, 4),
        "change_pct": round((change / float(prev["close"])) * 100.0, 4) if float(prev["close"]) else None,
        "volume": None if pd.isna(last.get("volume")) else float(last["volume"]),
        "market_cap": None,
        "short_name": None,
        "exchange_name": None,
        "quote_type": None,
        "source": "local_csv_latest",
    }


def _fetch_provider_snapshot(symbol: str, include_profile: bool) -> dict:
    snapshot = _recent_snapshot(symbol)
    if snapshot is not None:
        return {"symbol": symbol, "snapshot": snapshot, "error": None, "provider": "recent_cache", "attempted_providers": []}

    provider_result = fetch_snapshot_from_providers(symbol, include_profile=include_profile)
    if provider_result.snapshot is not None:
        return {
            "symbol": symbol,
            "snapshot": provider_result.snapshot,
            "error": None,
            "provider": provider_result.provider,
            "attempted_providers": provider_result.attempted_providers,
        }

    fallback = _build_local_snapshot(symbol)
    if fallback is not None:
        return {
            "symbol": symbol,
            "snapshot": fallback,
            "error": None,
            "provider": "local_csv",
            "attempted_providers": provider_result.attempted_providers,
        }

    remote_error = provider_result.error or f"No snapshot available for {symbol}"
    logger.warning("market_data.snapshot_fetch_failed symbol=%s detail=%s", symbol, remote_error)
    return {
        "symbol": symbol,
        "snapshot": None,
        "error": remote_error,
        "provider": provider_result.provider,
        "attempted_providers": provider_result.attempted_providers,
    }


def persist_ohlcv(symbol: str, items: list[dict], timeframe="1d", source="local_csv"):
    if not items:
        return 0
    with session_scope() as session:
        inserted = 0
        for item in items[-500:]:
            bar_time = pd.to_datetime(item.get("datetime"), errors="coerce")
            if pd.isna(bar_time):
                continue
            exists = session.query(OhlcvBar).filter(
                OhlcvBar.symbol == symbol,
                OhlcvBar.timeframe == timeframe,
                OhlcvBar.bar_time == bar_time.to_pydatetime(),
            ).first()
            if exists:
                continue
            session.add(OhlcvBar(
                symbol=symbol,
                timeframe=timeframe,
                bar_time=bar_time.to_pydatetime(),
                open=item.get("open"),
                high=item.get("high"),
                low=item.get("low"),
                close=item.get("close"),
                volume=item.get("volume"),
                source=source,
            ))
            inserted += 1
        return inserted


def load_history(symbol: str, start_date=None, end_date=None, interval="1d", persist=True):
    symbol = normalize_symbol(symbol)
    cache_key = _history_cache_key(symbol, start_date=start_date, end_date=end_date, interval=interval)

    def factory():
        try:
            result = load_symbol_source_data(symbol, start_date=start_date, end_date=end_date, interval=interval, persist_on_fetch=persist)
            source = result.source
            df = pd.DataFrame() if result.frame is None else result.frame.rename(columns={"date": "datetime"})

            if df.empty:
                return {
                    "symbol": symbol,
                    "source": source,
                    "rows": 0,
                    "items": [],
                    "error": result.error or f"No history for {symbol}",
                    "resolved_start_date": result.resolved_start_date,
                    "resolved_end_date": result.resolved_end_date,
                    "fallback_used": result.fallback_used,
                    "session_status": result.session_status,
                    "attempted_providers": result.attempted_providers,
                }

            normalized = pd.DataFrame({
                "datetime": pd.to_datetime(df["datetime"], errors="coerce"),
                "open": pd.to_numeric(df.get("open"), errors="coerce"),
                "high": pd.to_numeric(df.get("high"), errors="coerce"),
                "low": pd.to_numeric(df.get("low"), errors="coerce"),
                "close": pd.to_numeric(df.get("close"), errors="coerce"),
                "volume": pd.to_numeric(df.get("volume"), errors="coerce"),
            }).dropna(subset=["datetime", "close"])
            normalized = normalized.sort_values("datetime").reset_index(drop=True)

            items = [
                {
                    "datetime": str(row.datetime)[:19],
                    "open": None if pd.isna(row.open) else round(float(row.open), 4),
                    "high": None if pd.isna(row.high) else round(float(row.high), 4),
                    "low": None if pd.isna(row.low) else round(float(row.low), 4),
                    "close": None if pd.isna(row.close) else round(float(row.close), 4),
                    "volume": None if pd.isna(row.volume) else round(float(row.volume), 4),
                }
                for row in normalized.itertuples()
            ]

            if persist:
                persist_ohlcv(symbol, items, timeframe=interval, source=source)

            return {
                "symbol": symbol,
                "source": source,
                "rows": len(items),
                "items": items,
                "error": None,
                "resolved_start_date": result.resolved_start_date,
                "resolved_end_date": result.resolved_end_date,
                "fallback_used": result.fallback_used,
                "session_status": result.session_status,
                "attempted_providers": result.attempted_providers,
            }
        except Exception as exc:
            detail = " ".join(str(exc).split()) or exc.__class__.__name__
            logger.warning("market_data.load_history_failed symbol=%s interval=%s detail=%s", symbol, interval, detail)
            return {"symbol": symbol, "source": "error", "rows": 0, "items": [], "error": f"Failed to load history for {symbol}: {detail}"}

    return _cache().get_or_set(cache_key, factory, ttl_seconds=_history_cache_ttl(interval))


def incremental_update(symbol: str, interval="1d", lookback_days=30):
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=max(int(lookback_days), 5))
    return load_history(symbol, str(start_date), str(end_date), interval=interval, persist=True)


def fetch_quote_snapshots(symbols: list[str] | None = None, include_profile: bool = False):
    symbols = [normalize_symbol(symbol) for symbol in (symbols or DEFAULT_SYMBOLS) if str(symbol).strip()]
    cache_key = _snapshot_cache_key(symbols, include_profile)

    def factory():
        max_workers = max(1, min(len(symbols), 4))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            resolved = list(executor.map(lambda symbol: _fetch_provider_snapshot(symbol, include_profile), symbols))
        snapshots = [item["snapshot"] for item in resolved if item.get("snapshot") is not None]
        errors = [
            {"symbol": item["symbol"], "error": item.get("error")}
            for item in resolved
            if item.get("snapshot") is None and item.get("error")
        ]

        if snapshots:
            with session_scope() as session:
                for snapshot in snapshots:
                    session.add(QuoteSnapshot(
                        symbol=snapshot["symbol"],
                        price=snapshot.get("price"),
                        prev_close=snapshot.get("prev_close"),
                        change=snapshot.get("change"),
                        change_pct=snapshot.get("change_pct"),
                        volume=snapshot.get("volume"),
                        source=snapshot.get("source"),
                        payload_json=dumps_json(snapshot),
                    ))

        sources = {snapshot.get("source") for snapshot in snapshots if snapshot.get("source")}
        resolved_providers = {item.get("provider") for item in resolved if item.get("provider")}
        if errors and snapshots:
            provider_status = "partial"
        elif errors and not snapshots:
            provider_status = "error"
        elif sources == {"local_csv_latest"}:
            provider_status = "local_csv_fallback"
        elif len(resolved_providers) == 1 and resolved_providers:
            provider_status = next(iter(resolved_providers))
        else:
            provider_status = "mixed" if sources else "provider_chain"

        return {
            "items": snapshots,
            "count": len(snapshots),
            "requested_symbols": len(symbols),
            "failed_symbols": len(errors),
            "errors": errors[:25],
            "provider_status": provider_status,
            "provider_chain": get_market_data_provider_status(),
        }

    payload = _cache().get_or_set(cache_key, factory, ttl_seconds=_snapshot_cache_ttl(include_profile))
    items = payload.get("items", [])
    if len(symbols) <= 1 or len(items) <= 1:
        return payload

    ordered = {item.get("symbol"): item for item in items if item.get("symbol")}
    payload["items"] = [ordered[symbol] for symbol in symbols if symbol in ordered]
    payload["count"] = len(payload["items"])
    return payload


def get_recent_quote_series(symbol: str, bucket_seconds: int = 5, lookback_minutes: int = 120):
    normalized_symbol = normalize_symbol(symbol)
    cache_key = f"market:quote-series:{normalized_symbol}:{int(bucket_seconds)}:{int(lookback_minutes)}"

    def factory():
        cutoff = datetime.utcnow() - timedelta(minutes=max(int(lookback_minutes), 5))
        with session_scope() as session:
            rows = (
                session.query(QuoteSnapshot)
                .filter(QuoteSnapshot.symbol == normalized_symbol, QuoteSnapshot.captured_at >= cutoff)
                .order_by(QuoteSnapshot.captured_at.asc())
                .all()
            )

        buckets = {}
        step = max(int(bucket_seconds), 1)
        for row in rows:
            if row.price is None or row.captured_at is None:
                continue
            epoch = int(row.captured_at.timestamp())
            bucket_epoch = epoch - (epoch % step)
            bucket_key = datetime.utcfromtimestamp(bucket_epoch)
            buckets[bucket_key] = {
                "datetime": bucket_key.isoformat(timespec="seconds"),
                "price": round(float(row.price), 4),
                "change_pct": None if row.change_pct is None else round(float(row.change_pct), 4),
                "volume": None if row.volume is None else float(row.volume),
            }

        items = [value for _, value in sorted(buckets.items(), key=lambda pair: pair[0])]
        return {
            "symbol": normalized_symbol,
            "bucket_seconds": step,
            "rows": len(items),
            "items": items,
            "source": "quote_snapshots",
        }

    return _cache().get_or_set(cache_key, factory, ttl_seconds=5)


def persist_feature_snapshot(symbol: str, feature_payload: dict, feature_set="advanced_v1"):
    with session_scope() as session:
        session.add(FeatureSnapshot(
            symbol=normalize_symbol(symbol),
            feature_set=feature_set,
            payload_json=dumps_json(feature_payload),
        ))
