from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.app.config import RUNTIME_CACHE_DIR
from backend.app.services.market_data import fetch_quote_snapshots

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency
    yf = None


PROFILE_CACHE_DIR = RUNTIME_CACHE_DIR / "symbol_profiles"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _provider_symbol(symbol: str) -> str:
    return _normalize_symbol(symbol).replace(".", "-")


def _cache_path(symbol: str):
    PROFILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILE_CACHE_DIR / f"{_normalize_symbol(symbol)}.json"


def _read_cached_profile(symbol: str, ttl_hours: int = 72) -> dict | None:
    path = _cache_path(symbol)
    if not path.exists():
        return None
    age_seconds = max(_utc_now().timestamp() - path.stat().st_mtime, 0)
    if age_seconds > max(ttl_hours, 1) * 3600:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cached_profile(symbol: str, payload: dict) -> None:
    path = _cache_path(symbol)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _market_cap_bucket(market_cap) -> str:
    try:
        value = float(market_cap or 0.0)
    except Exception:
        value = 0.0
    if value >= 200_000_000_000:
        return "Mega Cap"
    if value >= 10_000_000_000:
        return "Large Cap"
    if value >= 2_000_000_000:
        return "Mid Cap"
    if value >= 300_000_000:
        return "Small Cap"
    if value > 0:
        return "Micro Cap"
    return "Unknown"


def _fallback_profile(symbol: str, market_cap=None) -> dict:
    return {
        "symbol": symbol,
        "sector": "Unknown",
        "industry": "Unknown",
        "market_cap": market_cap,
        "market_cap_bucket": _market_cap_bucket(market_cap),
        "beta": None,
        "provider_status": "fallback",
    }


def load_symbol_profiles(symbols: list[str], ttl_hours: int = 72) -> dict:
    normalized_symbols = [_normalize_symbol(symbol) for symbol in symbols if str(symbol or "").strip()]
    snapshots = {
        item["symbol"]: item
        for item in fetch_quote_snapshots(normalized_symbols, include_profile=True).get("items", [])
    }
    profiles = {}

    for symbol in normalized_symbols:
        cached = _read_cached_profile(symbol, ttl_hours=ttl_hours)
        if cached:
            cached["provider_status"] = cached.get("provider_status") or "cache"
            profiles[symbol] = cached
            continue

        market_cap = (snapshots.get(symbol) or {}).get("market_cap")
        if yf is None:
            profiles[symbol] = _fallback_profile(symbol, market_cap=market_cap)
            continue

        try:
            ticker = yf.Ticker(_provider_symbol(symbol))
            info = getattr(ticker, "info", None) or {}
            payload = {
                "symbol": symbol,
                "sector": info.get("sector") or "Unknown",
                "industry": info.get("industry") or "Unknown",
                "market_cap": info.get("marketCap") or market_cap,
                "market_cap_bucket": _market_cap_bucket(info.get("marketCap") or market_cap),
                "beta": info.get("beta"),
                "provider_status": "yfinance",
                "updated_at": _utc_now().isoformat(),
            }
            _write_cached_profile(symbol, payload)
            profiles[symbol] = payload
        except Exception:
            profiles[symbol] = _fallback_profile(symbol, market_cap=market_cap)

    return profiles
