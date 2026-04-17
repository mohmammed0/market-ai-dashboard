from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
import logging
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import os

import pandas as pd

from core.market_data_settings import (
    ALPACA_MARKET_DATA_BASE_URL,
    ALPACA_MARKET_DATA_FEED,
    MARKET_DATA_PRIMARY_PROVIDER,
    MARKET_DATA_PROVIDER_CHAIN,
    MARKET_DATA_SESSION_CLOSE_BUFFER_MINUTES,
    MARKET_DATA_SESSION_CLOSE_HOUR,
    MARKET_DATA_SESSION_CLOSE_MINUTE,
    MARKET_DATA_TIMEZONE_NAME,
    POLYGON_MARKET_DATA_API_KEY,
    POLYGON_MARKET_DATA_BASE_URL,
    SUPPORTED_MARKET_DATA_PROVIDERS,
    TIINGO_MARKET_DATA_API_KEY,
    TIINGO_MARKET_DATA_BASE_URL,
    TWELVEDATA_MARKET_DATA_API_KEY,
    TWELVEDATA_MARKET_DATA_BASE_URL,
)


def _alpaca_api_key() -> str:
    """Dynamic lookup so credentials injected into os.environ after startup are picked up.
    Uses `or` chaining so empty-string env vars (set by docker-compose as empty) fall through."""
    return (os.getenv("ALPACA_MARKET_DATA_API_KEY") or os.getenv("ALPACA_API_KEY") or "").strip()


def _alpaca_secret_key() -> str:
    """Dynamic lookup so credentials injected into os.environ after startup are picked up.
    Uses `or` chaining so empty-string env vars (set by docker-compose as empty) fall through."""
    return (os.getenv("ALPACA_MARKET_DATA_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY") or "").strip()

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency
    yf = None


logger = logging.getLogger(__name__)


@dataclass
class ProviderHistoryResult:
    frame: pd.DataFrame | None
    provider: str
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    attempted_providers: list[dict] = field(default_factory=list)


@dataclass
class ProviderSnapshotResult:
    snapshot: dict | None
    provider: str
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    attempted_providers: list[dict] = field(default_factory=list)


def normalize_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return ""
    if normalized.endswith("^") and not normalized.startswith("^"):
        normalized = f"^{normalized[:-1]}"
    if normalized.startswith("^") and normalized.count("^") > 1:
        normalized = f"^{normalized.replace('^', '')}"
    return normalized


def provider_symbol(symbol: str) -> str:
    return normalize_symbol(symbol).replace(".", "-")


def provider_symbol_candidates(symbol: str) -> list[str]:
    normalized = normalize_symbol(symbol)
    candidates = [
        provider_symbol(normalized),
        normalized,
        normalized.replace("-", "."),
    ]
    prepared: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = str(candidate or "").strip().upper()
        if not cleaned or cleaned in seen:
            continue
        prepared.append(cleaned)
        seen.add(cleaned)
    return prepared


def _safe_float(value, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value, default: int | None = None) -> int | None:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def _parsed_timestamp(value) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if parsed is None or pd.isna(parsed) else parsed


def _utc_boundary(value, *, end: bool = False) -> str | None:
    parsed = _parsed_timestamp(value)
    if parsed is None:
        return None
    timestamp = parsed
    if end and len(str(value)) <= 10:
        timestamp = timestamp + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    elif not end and len(str(value)) <= 10:
        timestamp = timestamp.floor("D")
    return timestamp.tz_convert(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _request_json(url: str, *, headers: dict | None = None, timeout: int = 25) -> dict | list:
    request = Request(url, headers={"User-Agent": "MarketAIDashboard/1.0", **(headers or {})})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _normalize_frame(rows: list[dict], instrument: str, *, date_key: str, open_key: str, high_key: str, low_key: str, close_key: str, volume_key: str, reverse: bool = False) -> pd.DataFrame:
    if reverse:
        rows = list(reversed(rows))
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    date_series = pd.to_datetime(frame.get(date_key), errors="coerce", utc=True)
    normalized = pd.DataFrame({
        "date": date_series.dt.tz_localize(None),
        "open": pd.to_numeric(frame.get(open_key), errors="coerce"),
        "high": pd.to_numeric(frame.get(high_key), errors="coerce"),
        "low": pd.to_numeric(frame.get(low_key), errors="coerce"),
        "close": pd.to_numeric(frame.get(close_key), errors="coerce"),
        "volume": pd.to_numeric(frame.get(volume_key), errors="coerce"),
    }).dropna(subset=["date", "close"])
    normalized = normalized.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    normalized["instrument"] = instrument
    return normalized


def _session_settings_payload() -> dict:
    return {
        "timezone": MARKET_DATA_TIMEZONE_NAME,
        "close_hour": MARKET_DATA_SESSION_CLOSE_HOUR,
        "close_minute": MARKET_DATA_SESSION_CLOSE_MINUTE,
        "close_buffer_minutes": MARKET_DATA_SESSION_CLOSE_BUFFER_MINUTES,
    }


class MarketDataProvider:
    name = "base"

    def configured(self) -> bool:
        return True

    def supports_history(self, interval: str) -> bool:
        return True

    def supports_snapshot(self) -> bool:
        return True

    def configuration_detail(self) -> str:
        return "ready"

    def fetch_history(self, symbol: str, start_date=None, end_date=None, interval: str = "1d") -> ProviderHistoryResult:
        raise NotImplementedError

    def fetch_snapshot(self, symbol: str, include_profile: bool = False) -> ProviderSnapshotResult:
        raise NotImplementedError

    def status(self) -> dict:
        return {
            "name": self.name,
            "configured": self.configured(),
            "supports_history": True,
            "supports_snapshot": self.supports_snapshot(),
            "detail": self.configuration_detail(),
            "is_primary": self.name == MARKET_DATA_PRIMARY_PROVIDER,
            "in_chain": self.name in MARKET_DATA_PROVIDER_CHAIN,
        }


class AlpacaMarketDataProvider(MarketDataProvider):
    name = "alpaca"
    _interval_map = {
        "1d": "1Day",
        "1h": "1Hour",
        "60m": "1Hour",
        "30m": "30Min",
        "15m": "15Min",
        "5m": "5Min",
        "1m": "1Min",
    }

    def configured(self) -> bool:
        return bool(_alpaca_api_key() and _alpaca_secret_key())

    def supports_history(self, interval: str) -> bool:
        return str(interval or "1d").strip().lower() in self._interval_map

    def configuration_detail(self) -> str:
        return "configured" if self.configured() else "missing ALPACA_MARKET_DATA_API_KEY / ALPACA_API_KEY credentials"

    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": _alpaca_api_key(),
            "APCA-API-SECRET-KEY": _alpaca_secret_key(),
        }

    def fetch_history(self, symbol: str, start_date=None, end_date=None, interval: str = "1d") -> ProviderHistoryResult:
        normalized_interval = str(interval or "1d").strip().lower()
        if not self.supports_history(normalized_interval):
            return ProviderHistoryResult(frame=None, provider=self.name, error=f"Unsupported interval for Alpaca: {interval}")

        params = {
            "symbols": provider_symbol(symbol),
            "timeframe": self._interval_map[normalized_interval],
            "limit": 10000,
            "adjustment": "raw",
            "sort": "asc",
            "feed": ALPACA_MARKET_DATA_FEED,
        }
        if start_date:
            params["start"] = _utc_boundary(start_date)
        if end_date:
            params["end"] = _utc_boundary(end_date, end=True)
        url = f"{ALPACA_MARKET_DATA_BASE_URL}/v2/stocks/bars?{urlencode(params)}"
        try:
            payload = _request_json(url, headers=self._headers())
            bars = (payload.get("bars") or {}).get(provider_symbol(symbol)) or (payload.get("bars") or {}).get(normalize_symbol(symbol)) or []
            frame = _normalize_frame(
                bars,
                normalize_symbol(symbol),
                date_key="t",
                open_key="o",
                high_key="h",
                low_key="l",
                close_key="c",
                volume_key="v",
            )
            if frame.empty:
                return ProviderHistoryResult(frame=None, provider=self.name, error=f"No Alpaca bars returned for {normalize_symbol(symbol)}.")
            return ProviderHistoryResult(frame=frame, provider=self.name, metadata={"feed": ALPACA_MARKET_DATA_FEED})
        except Exception as exc:
            detail = " ".join(str(exc).split()) or exc.__class__.__name__
            return ProviderHistoryResult(frame=None, provider=self.name, error=f"Alpaca market-data request failed: {detail}")

    def fetch_snapshot(self, symbol: str, include_profile: bool = False) -> ProviderSnapshotResult:
        params = {"symbols": provider_symbol(symbol), "feed": ALPACA_MARKET_DATA_FEED}
        url = f"{ALPACA_MARKET_DATA_BASE_URL}/v2/stocks/snapshots?{urlencode(params)}"
        try:
            payload = _request_json(url, headers=self._headers())
            snapshot = (payload.get("snapshots") or {}).get(provider_symbol(symbol)) or (payload.get("snapshots") or {}).get(normalize_symbol(symbol)) or {}
            latest_trade = snapshot.get("latestTrade") or {}
            daily_bar = snapshot.get("dailyBar") or {}
            prev_daily_bar = snapshot.get("prevDailyBar") or {}
            price = _safe_float(latest_trade.get("p"), _safe_float(daily_bar.get("c")))
            prev_close = _safe_float(prev_daily_bar.get("c"))
            if price is None and prev_close is None:
                return ProviderSnapshotResult(snapshot=None, provider=self.name, error=f"No Alpaca snapshot returned for {normalize_symbol(symbol)}.")
            change = None if price is None or prev_close in (None, 0) else price - prev_close
            change_pct = None if change is None or prev_close in (None, 0) else (change / prev_close) * 100.0
            return ProviderSnapshotResult(
                snapshot={
                    "symbol": normalize_symbol(symbol),
                    "price": None if price is None else round(float(price), 4),
                    "prev_close": None if prev_close is None else round(float(prev_close), 4),
                    "change": None if change is None else round(float(change), 4),
                    "change_pct": None if change_pct is None else round(float(change_pct), 4),
                    "volume": _safe_float(daily_bar.get("v")),
                    "market_cap": None,
                    "short_name": None,
                    "exchange_name": "Alpaca",
                    "quote_type": "equity",
                    "source": "alpaca_market_data",
                },
                provider=self.name,
                metadata={"feed": ALPACA_MARKET_DATA_FEED},
            )
        except Exception as exc:
            detail = " ".join(str(exc).split()) or exc.__class__.__name__
            return ProviderSnapshotResult(snapshot=None, provider=self.name, error=f"Alpaca snapshot request failed: {detail}")


class PolygonMarketDataProvider(MarketDataProvider):
    name = "polygon"
    _interval_map = {
        "1d": (1, "day"),
        "1h": (1, "hour"),
        "60m": (1, "hour"),
        "30m": (30, "minute"),
        "15m": (15, "minute"),
        "5m": (5, "minute"),
        "1m": (1, "minute"),
    }

    def configured(self) -> bool:
        return bool(POLYGON_MARKET_DATA_API_KEY)

    def supports_history(self, interval: str) -> bool:
        return str(interval or "1d").strip().lower() in self._interval_map

    def configuration_detail(self) -> str:
        return "configured" if self.configured() else "missing Polygon API key"

    def fetch_history(self, symbol: str, start_date=None, end_date=None, interval: str = "1d") -> ProviderHistoryResult:
        normalized_interval = str(interval or "1d").strip().lower()
        if not self.supports_history(normalized_interval):
            return ProviderHistoryResult(frame=None, provider=self.name, error=f"Unsupported interval for Polygon: {interval}")
        multiplier, timespan = self._interval_map[normalized_interval]
        start_value = pd.to_datetime(start_date or datetime.now(UTC).date(), errors="coerce")
        end_value = pd.to_datetime(end_date or datetime.now(UTC).date(), errors="coerce")
        if pd.isna(start_value) or pd.isna(end_value):
            return ProviderHistoryResult(frame=None, provider=self.name, error="Invalid request window for Polygon history.")
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
            "apiKey": POLYGON_MARKET_DATA_API_KEY,
        }
        url = (
            f"{POLYGON_MARKET_DATA_BASE_URL}/v2/aggs/ticker/{quote(provider_symbol(symbol))}/range/"
            f"{multiplier}/{timespan}/{start_value.strftime('%Y-%m-%d')}/{end_value.strftime('%Y-%m-%d')}?{urlencode(params)}"
        )
        try:
            payload = _request_json(url)
            rows = []
            for item in payload.get("results") or []:
                rows.append({
                    "t": datetime.fromtimestamp(float(item.get("t", 0)) / 1000.0, tz=UTC).isoformat(),
                    "o": item.get("o"),
                    "h": item.get("h"),
                    "l": item.get("l"),
                    "c": item.get("c"),
                    "v": item.get("v"),
                })
            frame = _normalize_frame(
                rows,
                normalize_symbol(symbol),
                date_key="t",
                open_key="o",
                high_key="h",
                low_key="l",
                close_key="c",
                volume_key="v",
            )
            if frame.empty:
                return ProviderHistoryResult(frame=None, provider=self.name, error=f"No Polygon bars returned for {normalize_symbol(symbol)}.")
            return ProviderHistoryResult(frame=frame, provider=self.name)
        except Exception as exc:
            detail = " ".join(str(exc).split()) or exc.__class__.__name__
            return ProviderHistoryResult(frame=None, provider=self.name, error=f"Polygon market-data request failed: {detail}")

    def fetch_snapshot(self, symbol: str, include_profile: bool = False) -> ProviderSnapshotResult:
        url = f"{POLYGON_MARKET_DATA_BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{quote(provider_symbol(symbol))}?apiKey={quote(POLYGON_MARKET_DATA_API_KEY)}"
        try:
            payload = _request_json(url)
            ticker = payload.get("ticker") or {}
            last_trade = ticker.get("lastTrade") or {}
            day = ticker.get("day") or {}
            prev_day = ticker.get("prevDay") or {}
            price = _safe_float(last_trade.get("p"), _safe_float(day.get("c")))
            prev_close = _safe_float(prev_day.get("c"))
            if price is None and prev_close is None:
                return ProviderSnapshotResult(snapshot=None, provider=self.name, error=f"No Polygon snapshot returned for {normalize_symbol(symbol)}.")
            change = None if price is None or prev_close in (None, 0) else price - prev_close
            change_pct = None if change is None or prev_close in (None, 0) else (change / prev_close) * 100.0
            return ProviderSnapshotResult(
                snapshot={
                    "symbol": normalize_symbol(symbol),
                    "price": None if price is None else round(float(price), 4),
                    "prev_close": None if prev_close is None else round(float(prev_close), 4),
                    "change": None if change is None else round(float(change), 4),
                    "change_pct": None if change_pct is None else round(float(change_pct), 4),
                    "volume": _safe_float(day.get("v")),
                    "market_cap": None,
                    "short_name": None,
                    "exchange_name": "Polygon",
                    "quote_type": "equity",
                    "source": "polygon_market_data",
                },
                provider=self.name,
            )
        except Exception as exc:
            detail = " ".join(str(exc).split()) or exc.__class__.__name__
            return ProviderSnapshotResult(snapshot=None, provider=self.name, error=f"Polygon snapshot request failed: {detail}")


class TiingoMarketDataProvider(MarketDataProvider):
    name = "tiingo"

    def configured(self) -> bool:
        return bool(TIINGO_MARKET_DATA_API_KEY)

    def supports_history(self, interval: str) -> bool:
        return str(interval or "1d").strip().lower() == "1d"

    def configuration_detail(self) -> str:
        return "configured" if self.configured() else "missing Tiingo API key"

    def _headers(self) -> dict:
        return {"Authorization": f"Token {TIINGO_MARKET_DATA_API_KEY}"}

    def fetch_history(self, symbol: str, start_date=None, end_date=None, interval: str = "1d") -> ProviderHistoryResult:
        if not self.supports_history(interval):
            return ProviderHistoryResult(frame=None, provider=self.name, error=f"Unsupported interval for Tiingo: {interval}")
        params = {"format": "json", "resampleFreq": "daily"}
        if start_date:
            params["startDate"] = str(start_date)
        if end_date:
            params["endDate"] = str(end_date)
        url = f"{TIINGO_MARKET_DATA_BASE_URL}/tiingo/daily/{quote(provider_symbol(symbol))}/prices?{urlencode(params)}"
        try:
            payload = _request_json(url, headers=self._headers())
            frame = _normalize_frame(
                payload if isinstance(payload, list) else [],
                normalize_symbol(symbol),
                date_key="date",
                open_key="open",
                high_key="high",
                low_key="low",
                close_key="close",
                volume_key="volume",
            )
            if frame.empty:
                return ProviderHistoryResult(frame=None, provider=self.name, error=f"No Tiingo bars returned for {normalize_symbol(symbol)}.")
            return ProviderHistoryResult(frame=frame, provider=self.name)
        except Exception as exc:
            detail = " ".join(str(exc).split()) or exc.__class__.__name__
            return ProviderHistoryResult(frame=None, provider=self.name, error=f"Tiingo market-data request failed: {detail}")

    def fetch_snapshot(self, symbol: str, include_profile: bool = False) -> ProviderSnapshotResult:
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=7)
        history = self.fetch_history(symbol, start_date=start_date.isoformat(), end_date=end_date.isoformat(), interval="1d")
        if history.frame is None or history.frame.empty:
            return ProviderSnapshotResult(snapshot=None, provider=self.name, error=history.error)
        frame = history.frame.sort_values("date").reset_index(drop=True)
        last = frame.iloc[-1]
        prev = frame.iloc[-2] if len(frame) > 1 else last
        change = float(last["close"]) - float(prev["close"])
        return ProviderSnapshotResult(
            snapshot={
                "symbol": normalize_symbol(symbol),
                "price": round(float(last["close"]), 4),
                "prev_close": round(float(prev["close"]), 4),
                "change": round(change, 4),
                "change_pct": round((change / float(prev["close"])) * 100.0, 4) if float(prev["close"]) else None,
                "volume": None if pd.isna(last.get("volume")) else float(last["volume"]),
                "market_cap": None,
                "short_name": None,
                "exchange_name": "Tiingo",
                "quote_type": "equity",
                "source": "tiingo_market_data",
            },
            provider=self.name,
        )


class TwelveDataMarketDataProvider(MarketDataProvider):
    name = "twelvedata"
    _interval_map = {
        "1d": "1day",
        "1h": "1h",
        "60m": "1h",
        "30m": "30min",
        "15m": "15min",
        "5m": "5min",
        "1m": "1min",
    }

    def configured(self) -> bool:
        return bool(TWELVEDATA_MARKET_DATA_API_KEY)

    def supports_history(self, interval: str) -> bool:
        return str(interval or "1d").strip().lower() in self._interval_map

    def configuration_detail(self) -> str:
        return "configured" if self.configured() else "missing Twelve Data API key"

    def fetch_history(self, symbol: str, start_date=None, end_date=None, interval: str = "1d") -> ProviderHistoryResult:
        normalized_interval = str(interval or "1d").strip().lower()
        if not self.supports_history(normalized_interval):
            return ProviderHistoryResult(frame=None, provider=self.name, error=f"Unsupported interval for Twelve Data: {interval}")
        params = {
            "symbol": provider_symbol(symbol),
            "interval": self._interval_map[normalized_interval],
            "format": "JSON",
            "apikey": TWELVEDATA_MARKET_DATA_API_KEY,
            "outputsize": 5000,
            "order": "ASC",
            "timezone": MARKET_DATA_TIMEZONE_NAME,
        }
        if start_date:
            params["start_date"] = str(start_date)
        if end_date:
            params["end_date"] = str(end_date)
        url = f"{TWELVEDATA_MARKET_DATA_BASE_URL}/time_series?{urlencode(params)}"
        try:
            payload = _request_json(url)
            frame = _normalize_frame(
                payload.get("values") or [],
                normalize_symbol(symbol),
                date_key="datetime",
                open_key="open",
                high_key="high",
                low_key="low",
                close_key="close",
                volume_key="volume",
                reverse=True,
            )
            if frame.empty:
                message = payload.get("message") if isinstance(payload, dict) else None
                return ProviderHistoryResult(frame=None, provider=self.name, error=message or f"No Twelve Data bars returned for {normalize_symbol(symbol)}.")
            return ProviderHistoryResult(frame=frame, provider=self.name)
        except Exception as exc:
            detail = " ".join(str(exc).split()) or exc.__class__.__name__
            return ProviderHistoryResult(frame=None, provider=self.name, error=f"Twelve Data request failed: {detail}")

    def fetch_snapshot(self, symbol: str, include_profile: bool = False) -> ProviderSnapshotResult:
        url = f"{TWELVEDATA_MARKET_DATA_BASE_URL}/quote?{urlencode({'symbol': provider_symbol(symbol), 'apikey': TWELVEDATA_MARKET_DATA_API_KEY})}"
        try:
            payload = _request_json(url)
            price = _safe_float(payload.get("close"), _safe_float(payload.get("price")))
            prev_close = _safe_float(payload.get("previous_close"))
            if price is None and prev_close is None:
                message = payload.get("message") if isinstance(payload, dict) else None
                return ProviderSnapshotResult(snapshot=None, provider=self.name, error=message or f"No Twelve Data quote returned for {normalize_symbol(symbol)}.")
            change = None if price is None or prev_close in (None, 0) else price - prev_close
            change_pct = None if change is None or prev_close in (None, 0) else (change / prev_close) * 100.0
            return ProviderSnapshotResult(
                snapshot={
                    "symbol": normalize_symbol(symbol),
                    "price": None if price is None else round(float(price), 4),
                    "prev_close": None if prev_close is None else round(float(prev_close), 4),
                    "change": None if change is None else round(float(change), 4),
                    "change_pct": None if change_pct is None else round(float(change_pct), 4),
                    "volume": _safe_float(payload.get("volume")),
                    "market_cap": None,
                    "short_name": payload.get("name"),
                    "exchange_name": payload.get("exchange"),
                    "quote_type": payload.get("type"),
                    "source": "twelvedata_market_data",
                },
                provider=self.name,
            )
        except Exception as exc:
            detail = " ".join(str(exc).split()) or exc.__class__.__name__
            return ProviderSnapshotResult(snapshot=None, provider=self.name, error=f"Twelve Data quote request failed: {detail}")


class YahooMarketDataProvider(MarketDataProvider):
    name = "yahoo"

    def configured(self) -> bool:
        return yf is not None

    def configuration_detail(self) -> str:
        return "configured" if self.configured() else "yfinance unavailable"

    def fetch_history(self, symbol: str, start_date=None, end_date=None, interval: str = "1d") -> ProviderHistoryResult:
        if yf is None:
            return ProviderHistoryResult(frame=None, provider=self.name, error="yfinance unavailable")
        start_dt = pd.to_datetime(start_date, errors="coerce") if start_date else None
        end_dt = pd.to_datetime(end_date, errors="coerce") if end_date else None
        request_start = None if start_dt is None or pd.isna(start_dt) else start_dt.strftime("%Y-%m-%d")
        request_end = None if end_dt is None or pd.isna(end_dt) else (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        fetched = None
        attempts: list[str] = []
        last_error = None
        for candidate in provider_symbol_candidates(symbol):
            attempts.append(candidate)
            try:
                candidate_frame = yf.download(
                    candidate,
                    start=request_start,
                    end=request_end,
                    interval=interval,
                    progress=False,
                    auto_adjust=False,
                )
            except Exception as exc:
                last_error = " ".join(str(exc).split()) or exc.__class__.__name__
                continue
            if candidate_frame is not None and not candidate_frame.empty:
                fetched = candidate_frame
                break
        if fetched is None or fetched.empty:
            attempted = ",".join(attempts)
            if last_error:
                return ProviderHistoryResult(
                    frame=None,
                    provider=self.name,
                    error=f"No Yahoo bars returned for {normalize_symbol(symbol)} (attempted={attempted}; last_error={last_error}).",
                )
            return ProviderHistoryResult(
                frame=None,
                provider=self.name,
                error=f"No Yahoo bars returned for {normalize_symbol(symbol)} (attempted={attempted}).",
            )
        fetched = fetched.reset_index()
        if getattr(fetched.columns, "nlevels", 1) > 1:
            fetched.columns = [
                str(column[0] if isinstance(column, tuple) else column).lower().replace(" ", "_")
                for column in fetched.columns
            ]
        else:
            fetched.columns = [str(column).lower().replace(" ", "_") for column in fetched.columns]
        date_col = "date" if "date" in fetched.columns else fetched.columns[0]
        fetched = fetched.rename(columns={date_col: "date"})
        frame = _normalize_frame(
            fetched.to_dict("records"),
            normalize_symbol(symbol),
            date_key="date",
            open_key="open",
            high_key="high",
            low_key="low",
            close_key="close",
            volume_key="volume",
        )
        if frame.empty:
            return ProviderHistoryResult(frame=None, provider=self.name, error=f"No Yahoo bars returned for {normalize_symbol(symbol)}.")
        return ProviderHistoryResult(frame=frame, provider=self.name)

    def fetch_snapshot(self, symbol: str, include_profile: bool = False) -> ProviderSnapshotResult:
        if yf is None:
            return ProviderSnapshotResult(snapshot=None, provider=self.name, error="yfinance unavailable")
        attempts: list[str] = []
        last_error = None
        for candidate in provider_symbol_candidates(symbol):
            attempts.append(candidate)
            try:
                ticker = yf.Ticker(candidate)
                info = getattr(ticker, "fast_info", None) or {}
                price = info.get("lastPrice") or info.get("last_price")
                prev_close = info.get("previousClose") or info.get("previous_close")
                volume = info.get("lastVolume") or info.get("last_volume")
                market_cap = info.get("marketCap") or info.get("market_cap")
                profile = {}
                if include_profile:
                    raw_info = getattr(ticker, "info", None) or {}
                    profile = {
                        "short_name": raw_info.get("shortName") or raw_info.get("longName"),
                        "exchange": raw_info.get("exchange"),
                        "quote_type": raw_info.get("quoteType"),
                        "market_cap": raw_info.get("marketCap") or market_cap,
                    }
                if price is None and prev_close is None:
                    continue
                change = None if prev_close in (None, 0) or price is None else float(price) - float(prev_close)
                change_pct = None if prev_close in (None, 0) or change is None else (change / float(prev_close)) * 100.0
                return ProviderSnapshotResult(
                    snapshot={
                        "symbol": normalize_symbol(symbol),
                        "price": None if price is None else round(float(price), 4),
                        "prev_close": None if prev_close is None else round(float(prev_close), 4),
                        "change": None if change is None else round(float(change), 4),
                        "change_pct": None if change_pct is None else round(float(change_pct), 4),
                        "volume": None if volume is None else float(volume),
                        "market_cap": None if (profile.get("market_cap") if include_profile else market_cap) is None else float(profile.get("market_cap") if include_profile else market_cap),
                        "short_name": profile.get("short_name") if include_profile else None,
                        "exchange_name": profile.get("exchange") if include_profile else None,
                        "quote_type": profile.get("quote_type") if include_profile else None,
                        "source": "yahoo_market_data",
                    },
                    provider=self.name,
                )
            except Exception as exc:
                last_error = " ".join(str(exc).split()) or exc.__class__.__name__
                continue
        attempted = ",".join(attempts)
        if last_error:
            return ProviderSnapshotResult(
                snapshot=None,
                provider=self.name,
                error=f"No Yahoo snapshot returned for {normalize_symbol(symbol)} (attempted={attempted}; last_error={last_error}).",
            )
        return ProviderSnapshotResult(
            snapshot=None,
            provider=self.name,
            error=f"No Yahoo snapshot returned for {normalize_symbol(symbol)} (attempted={attempted}).",
        )


PROVIDER_REGISTRY = {
    "alpaca": AlpacaMarketDataProvider,
    "polygon": PolygonMarketDataProvider,
    "tiingo": TiingoMarketDataProvider,
    "twelvedata": TwelveDataMarketDataProvider,
    "yahoo": YahooMarketDataProvider,
}


def _provider_instances() -> list[MarketDataProvider]:
    instances: list[MarketDataProvider] = []
    for provider_name in MARKET_DATA_PROVIDER_CHAIN:
        provider_cls = PROVIDER_REGISTRY.get(provider_name)
        if provider_cls is None:
            continue
        instances.append(provider_cls())
    return instances


def get_market_data_provider_status() -> dict:
    providers = []
    for name in SUPPORTED_MARKET_DATA_PROVIDERS:
        provider_cls = PROVIDER_REGISTRY.get(name)
        if provider_cls is None:
            continue
        providers.append(provider_cls().status())
    return {
        "primary_provider": MARKET_DATA_PRIMARY_PROVIDER,
        "provider_chain": MARKET_DATA_PROVIDER_CHAIN,
        "session": _session_settings_payload(),
        "providers": providers,
    }


def fetch_history_from_providers(symbol: str, start_date=None, end_date=None, interval: str = "1d") -> ProviderHistoryResult:
    attempts: list[dict] = []
    normalized_symbol = normalize_symbol(symbol)
    for provider in _provider_instances():
        if not provider.configured():
            attempts.append({"provider": provider.name, "status": "skipped", "detail": provider.configuration_detail()})
            continue
        if not provider.supports_history(interval):
            attempts.append({"provider": provider.name, "status": "skipped", "detail": f"unsupported interval {interval}"})
            continue
        result = provider.fetch_history(normalized_symbol, start_date=start_date, end_date=end_date, interval=interval)
        attempts.append({
            "provider": provider.name,
            "status": "ok" if result.frame is not None and not result.frame.empty else "error",
            "detail": result.error or "success",
        })
        if result.frame is not None and not result.frame.empty:
            result.attempted_providers = attempts
            result.metadata = {**result.metadata, "provider_chain": MARKET_DATA_PROVIDER_CHAIN}
            return result
    error = next((item["detail"] for item in reversed(attempts) if item["status"] == "error"), "No configured market-data provider returned data.")
    return ProviderHistoryResult(
        frame=None,
        provider="unavailable",
        error=error,
        attempted_providers=attempts,
        metadata={"provider_chain": MARKET_DATA_PROVIDER_CHAIN},
    )


def fetch_snapshot_from_providers(symbol: str, include_profile: bool = False) -> ProviderSnapshotResult:
    attempts: list[dict] = []
    normalized_symbol = normalize_symbol(symbol)
    for provider in _provider_instances():
        if not provider.configured():
            attempts.append({"provider": provider.name, "status": "skipped", "detail": provider.configuration_detail()})
            continue
        if not provider.supports_snapshot():
            attempts.append({"provider": provider.name, "status": "skipped", "detail": "snapshots not supported"})
            continue
        result = provider.fetch_snapshot(normalized_symbol, include_profile=include_profile)
        attempts.append({
            "provider": provider.name,
            "status": "ok" if result.snapshot is not None else "error",
            "detail": result.error or "success",
        })
        if result.snapshot is not None:
            result.attempted_providers = attempts
            result.metadata = {**result.metadata, "provider_chain": MARKET_DATA_PROVIDER_CHAIN}
            return result
    error = next((item["detail"] for item in reversed(attempts) if item["status"] == "error"), "No configured market-data provider returned a snapshot.")
    return ProviderSnapshotResult(
        snapshot=None,
        provider="unavailable",
        error=error,
        attempted_providers=attempts,
        metadata={"provider_chain": MARKET_DATA_PROVIDER_CHAIN},
    )
