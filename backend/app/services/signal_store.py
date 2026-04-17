from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from backend.app.config import (
    DEFAULT_SAMPLE_SYMBOLS,
    DEFAULT_TRACKED_SYMBOL_LIMIT,
    LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
    LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS,
    LIGHTWEIGHT_EXPERIMENT_MODE,
    SIGNAL_CACHE_TTL_SECONDS,
    SIGNAL_REFRESH_MAX_WORKERS,
)
from backend.app.core.date_defaults import recent_end_date_iso, recent_start_date_iso
from backend.app.services import get_cache
from backend.app.services.cached_analysis import get_ranked_analysis_result
from backend.app.services.signal_runtime import extract_signal_view


SIGNAL_STORE_KEY_PREFIX = "signal:latest:"
SIGNAL_STORE_INDEX_KEY = "signal:latest:index"
SUPPORTED_SIGNAL_MODES = ("classic", "ml", "dl", "ensemble")


def _normalized_sample_symbols(symbols: list[str] | None = None) -> list[str]:
    sample_limit = LIGHTWEIGHT_EXPERIMENT_MAX_SYMBOLS if LIGHTWEIGHT_EXPERIMENT_MODE else DEFAULT_TRACKED_SYMBOL_LIMIT
    source = symbols or DEFAULT_SAMPLE_SYMBOLS[:sample_limit]
    prepared: list[str] = []
    seen: set[str] = set()
    for raw in source:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        prepared.append(symbol)
        seen.add(symbol)
    return prepared[:sample_limit]


def _cache_key(symbol: str) -> str:
    return f"{SIGNAL_STORE_KEY_PREFIX}{str(symbol or '').strip().upper()}"


def _build_signal_snapshot(symbol: str, start_date: str, end_date: str) -> dict:
    analysis = get_ranked_analysis_result(
        symbol,
        start_date,
        end_date,
        ttl_seconds=SIGNAL_CACHE_TTL_SECONDS,
        include_ml=True,
        include_dl=LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL,
    )
    if "error" in analysis:
        return {
            "symbol": symbol,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start_date": start_date,
            "end_date": end_date,
            "error": str(analysis.get("error") or "signal_generation_failed"),
        }

    available_modes = ("classic", "ml", "ensemble") + (("dl",) if LIGHTWEIGHT_EXPERIMENT_INCLUDE_DL else tuple())
    views = {mode: extract_signal_view(analysis, mode=mode) for mode in available_modes}
    default_mode = "ensemble" if "ensemble" in views else "classic"
    default_view = views[default_mode]

    return {
        "symbol": symbol,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "default_mode": default_mode,
        "signal": str(default_view.get("signal") or "HOLD").upper(),
        "action": str(default_view.get("signal") or "HOLD").upper(),
        "confidence": float(default_view.get("confidence") or 0.0),
        "reason": str(default_view.get("reasoning") or "").strip() or None,
        "price": default_view.get("price"),
        "views": views,
    }


def refresh_signal_store(symbols: list[str] | None = None) -> dict:
    selected_symbols = _normalized_sample_symbols(symbols)
    if not selected_symbols:
        return {"symbols": [], "updated": 0, "errors": []}

    start_date = recent_start_date_iso()
    end_date = recent_end_date_iso()
    cache = get_cache()
    worker_count = max(1, min(SIGNAL_REFRESH_MAX_WORKERS, len(selected_symbols)))
    errors: list[dict] = []
    snapshots: list[dict] = []

    def worker(symbol: str) -> dict:
        try:
            return _build_signal_snapshot(symbol, start_date, end_date)
        except Exception as exc:
            return {
                "symbol": symbol,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "start_date": start_date,
                "end_date": end_date,
                "error": str(exc),
            }

    if worker_count == 1:
        results = [worker(symbol) for symbol in selected_symbols]
    else:
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="signal-store") as executor:
            results = list(executor.map(worker, selected_symbols))

    for snapshot in results:
        symbol = str(snapshot.get("symbol") or "").strip().upper()
        if snapshot.get("error"):
            errors.append({"symbol": symbol, "error": snapshot.get("error")})
            continue
        cache.set(_cache_key(symbol), snapshot, ttl_seconds=SIGNAL_CACHE_TTL_SECONDS)
        snapshots.append(snapshot)

    cache.set(
        SIGNAL_STORE_INDEX_KEY,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start_date": start_date,
            "end_date": end_date,
            "symbols": selected_symbols,
            "updated": len(snapshots),
            "errors": errors,
        },
        ttl_seconds=SIGNAL_CACHE_TTL_SECONDS,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "symbols": selected_symbols,
        "updated": len(snapshots),
        "errors": errors,
    }


def get_cached_signal_snapshot(symbol: str) -> dict | None:
    return get_cache().get(_cache_key(symbol))


def get_cached_signal_view(symbol: str, mode: str = "ensemble") -> dict | None:
    snapshot = get_cached_signal_snapshot(symbol)
    if not isinstance(snapshot, dict) or snapshot.get("error"):
        return None

    requested_mode = str(mode or snapshot.get("default_mode") or "ensemble").lower().strip()
    views = snapshot.get("views") or {}
    selected_view = views.get(requested_mode) or views.get(snapshot.get("default_mode") or "ensemble") or views.get("classic")
    if not isinstance(selected_view, dict):
        return None

    return {
        "symbol": str(snapshot.get("symbol") or symbol).strip().upper(),
        "mode": requested_mode,
        "generated_at": snapshot.get("generated_at"),
        "start_date": snapshot.get("start_date"),
        "end_date": snapshot.get("end_date"),
        "signal": str(selected_view.get("signal") or "HOLD").upper(),
        "confidence": float(selected_view.get("confidence") or 0.0),
        "price": selected_view.get("price"),
        "reasoning": str(selected_view.get("reasoning") or "").strip() or None,
    }
