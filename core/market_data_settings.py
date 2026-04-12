from __future__ import annotations

import os
from zoneinfo import ZoneInfo


SUPPORTED_MARKET_DATA_PROVIDERS = ("alpaca", "polygon", "tiingo", "twelvedata", "yahoo")


def _clean_provider_name(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in SUPPORTED_MARKET_DATA_PROVIDERS else ""


def _provider_chain(primary: str | None, fallback_csv: str | None) -> list[str]:
    ordered: list[str] = []
    for item in [_clean_provider_name(primary), *[_clean_provider_name(value) for value in str(fallback_csv or "").split(",")]]:
        if not item or item in ordered:
            continue
        ordered.append(item)
    if "yahoo" not in ordered:
        ordered.append("yahoo")
    return ordered


MARKET_DATA_PRIMARY_PROVIDER = _clean_provider_name(os.getenv("MARKET_AI_PRIMARY_MARKET_DATA_PROVIDER", "alpaca")) or "alpaca"
MARKET_DATA_FALLBACK_PROVIDERS = _provider_chain(
    MARKET_DATA_PRIMARY_PROVIDER,
    os.getenv("MARKET_AI_FALLBACK_MARKET_DATA_PROVIDERS", "polygon,tiingo,twelvedata,yahoo"),
)[1:]
MARKET_DATA_PROVIDER_CHAIN = _provider_chain(MARKET_DATA_PRIMARY_PROVIDER, ",".join(MARKET_DATA_FALLBACK_PROVIDERS))

MARKET_DATA_TIMEZONE_NAME = os.getenv("MARKET_AI_MARKET_TIMEZONE", "America/New_York").strip() or "America/New_York"
MARKET_DATA_TIMEZONE = ZoneInfo(MARKET_DATA_TIMEZONE_NAME)
MARKET_DATA_SESSION_CLOSE_HOUR = int(os.getenv("MARKET_AI_MARKET_SESSION_CLOSE_HOUR", "16"))
MARKET_DATA_SESSION_CLOSE_MINUTE = int(os.getenv("MARKET_AI_MARKET_SESSION_CLOSE_MINUTE", "0"))
MARKET_DATA_SESSION_CLOSE_BUFFER_MINUTES = int(os.getenv("MARKET_AI_MARKET_SESSION_CLOSE_BUFFER_MINUTES", "20"))

ALPACA_MARKET_DATA_API_KEY = os.getenv("ALPACA_MARKET_DATA_API_KEY", os.getenv("ALPACA_API_KEY", "")).strip()
ALPACA_MARKET_DATA_SECRET_KEY = os.getenv("ALPACA_MARKET_DATA_SECRET_KEY", os.getenv("ALPACA_SECRET_KEY", "")).strip()
ALPACA_MARKET_DATA_BASE_URL = os.getenv("MARKET_AI_ALPACA_MARKET_DATA_BASE_URL", "https://data.alpaca.markets").strip().rstrip("/")
ALPACA_MARKET_DATA_FEED = os.getenv("MARKET_AI_ALPACA_MARKET_DATA_FEED", "iex").strip().lower() or "iex"

POLYGON_MARKET_DATA_API_KEY = os.getenv("POLYGON_API_KEY", "").strip()
POLYGON_MARKET_DATA_BASE_URL = os.getenv("MARKET_AI_POLYGON_MARKET_DATA_BASE_URL", "https://api.polygon.io").strip().rstrip("/")

TIINGO_MARKET_DATA_API_KEY = os.getenv("TIINGO_API_KEY", "").strip()
TIINGO_MARKET_DATA_BASE_URL = os.getenv("MARKET_AI_TIINGO_MARKET_DATA_BASE_URL", "https://api.tiingo.com").strip().rstrip("/")

TWELVEDATA_MARKET_DATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
TWELVEDATA_MARKET_DATA_BASE_URL = os.getenv("MARKET_AI_TWELVEDATA_MARKET_DATA_BASE_URL", "https://api.twelvedata.com").strip().rstrip("/")
