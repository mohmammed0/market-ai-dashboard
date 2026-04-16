from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from sqlalchemy import func, or_

from backend.app.config import DEFAULT_INDEX_SYMBOLS, DEFAULT_SAMPLE_SYMBOLS, MARKET_UNIVERSE_TTL_HOURS, RUNTIME_CACHE_DIR
from backend.app.models import CurrencyReference, MarketUniverseSymbol
from backend.app.services import get_cache
from backend.app.services.market_data import fetch_quote_snapshots, load_history
from backend.app.services.storage import session_scope


UNIVERSE_CACHE_DIR = RUNTIME_CACHE_DIR / "market_universe"
UNIVERSE_META_PATH = UNIVERSE_CACHE_DIR / "universe_meta.json"
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
TOP_MARKET_CAP_URL = "https://companiesmarketcap.org/"
TOP_MARKET_CAP_SOURCE = "companiesmarketcap.org"
TOP_MARKET_CAP_COUNTRY = "US"
TOP_MARKET_CAP_TARGET_COUNT = 500
TOP_MARKET_CAP_MAX_PAGES = 12

INDEX_LABELS = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones Industrial Average",
    "^IXIC": "Nasdaq Composite",
    "^RUT": "Russell 2000",
    "^VIX": "CBOE Volatility Index",
}

MARKET_CATEGORY_MAP = {
    "Q": "NASDAQ Global Select",
    "G": "NASDAQ Global Market",
    "S": "NASDAQ Capital Market",
}

OTHER_EXCHANGE_MAP = {
    "N": "NYSE",
    "A": "NYSE American",
    "P": "NYSE Arca",
    "Z": "Cboe BZX",
    "V": "IEX",
}

TOP_PERFORMER_SYMBOLS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
    "GOOGL",
]

UNIVERSE_PRESET_LABELS = {
    "CUSTOM": "Custom Symbols",
    "NASDAQ": "NASDAQ",
    "NYSE": "NYSE",
    "ALL_US_EQUITIES": "All US Equities",
    "ETF_ONLY": "ETF Only",
    "TOP_500_MARKET_CAP": "Top 500 US Market Cap",
}

CATEGORY_LABELS = {
    "common_stock": "Common Stock",
    "etf": "ETF",
    "adr": "ADR",
    "reit": "REIT",
    "preferred": "Preferred",
    "fund": "Fund",
    "warrant": "Warrant",
    "unit": "Unit",
    "right": "Right",
    "other": "Other",
}

DEFAULT_CURRENCY_REFERENCES = [
    {"code": "USD", "name": "US Dollar", "region": "North America", "country_code": "US", "symbol": "$", "is_major": True, "display_order": 1},
    {"code": "EUR", "name": "Euro", "region": "Europe", "country_code": "EU", "symbol": "€", "is_major": True, "display_order": 2, "quote_symbol": "EURUSD=X"},
    {"code": "GBP", "name": "British Pound Sterling", "region": "Europe", "country_code": "GB", "symbol": "£", "is_major": True, "display_order": 3, "quote_symbol": "GBPUSD=X"},
    {"code": "JPY", "name": "Japanese Yen", "region": "Asia", "country_code": "JP", "symbol": "¥", "is_major": True, "display_order": 4, "quote_symbol": "JPY=X"},
    {"code": "CHF", "name": "Swiss Franc", "region": "Europe", "country_code": "CH", "symbol": "CHF", "is_major": True, "display_order": 5, "quote_symbol": "CHFUSD=X"},
    {"code": "CAD", "name": "Canadian Dollar", "region": "North America", "country_code": "CA", "symbol": "C$", "is_major": True, "display_order": 6, "quote_symbol": "CADUSD=X"},
    {"code": "AUD", "name": "Australian Dollar", "region": "Oceania", "country_code": "AU", "symbol": "A$", "is_major": True, "display_order": 7, "quote_symbol": "AUDUSD=X"},
    {"code": "NZD", "name": "New Zealand Dollar", "region": "Oceania", "country_code": "NZ", "symbol": "NZ$", "is_major": True, "display_order": 8, "quote_symbol": "NZDUSD=X"},
    {"code": "CNY", "name": "Chinese Yuan", "region": "Asia", "country_code": "CN", "symbol": "CN¥", "is_major": True, "display_order": 9},
    {"code": "HKD", "name": "Hong Kong Dollar", "region": "Asia", "country_code": "HK", "symbol": "HK$", "display_order": 10},
    {"code": "SGD", "name": "Singapore Dollar", "region": "Asia", "country_code": "SG", "symbol": "S$", "display_order": 11},
    {"code": "INR", "name": "Indian Rupee", "region": "Asia", "country_code": "IN", "symbol": "₹", "display_order": 12},
    {"code": "KRW", "name": "South Korean Won", "region": "Asia", "country_code": "KR", "symbol": "₩", "display_order": 13},
    {"code": "TWD", "name": "New Taiwan Dollar", "region": "Asia", "country_code": "TW", "symbol": "NT$", "display_order": 14},
    {"code": "SEK", "name": "Swedish Krona", "region": "Europe", "country_code": "SE", "symbol": "kr", "display_order": 15},
    {"code": "NOK", "name": "Norwegian Krone", "region": "Europe", "country_code": "NO", "symbol": "kr", "display_order": 16},
    {"code": "DKK", "name": "Danish Krone", "region": "Europe", "country_code": "DK", "symbol": "kr", "display_order": 17},
    {"code": "PLN", "name": "Polish Zloty", "region": "Europe", "country_code": "PL", "symbol": "zl", "display_order": 18},
    {"code": "CZK", "name": "Czech Koruna", "region": "Europe", "country_code": "CZ", "symbol": "Kc", "display_order": 19},
    {"code": "TRY", "name": "Turkish Lira", "region": "Europe / Middle East", "country_code": "TR", "symbol": "₺", "display_order": 20},
    {"code": "ZAR", "name": "South African Rand", "region": "Africa", "country_code": "ZA", "symbol": "R", "display_order": 21},
    {"code": "MXN", "name": "Mexican Peso", "region": "North America", "country_code": "MX", "symbol": "$", "display_order": 22},
    {"code": "BRL", "name": "Brazilian Real", "region": "South America", "country_code": "BR", "symbol": "R$", "display_order": 23},
    {"code": "AED", "name": "UAE Dirham", "region": "Middle East", "country_code": "AE", "symbol": "AED", "display_order": 24},
    {"code": "SAR", "name": "Saudi Riyal", "region": "Middle East", "country_code": "SA", "symbol": "SAR", "display_order": 25},
    {"code": "QAR", "name": "Qatari Riyal", "region": "Middle East", "country_code": "QA", "symbol": "QAR", "display_order": 26},
    {"code": "KWD", "name": "Kuwaiti Dinar", "region": "Middle East", "country_code": "KW", "symbol": "KWD", "display_order": 27},
    {"code": "BHD", "name": "Bahraini Dinar", "region": "Middle East", "country_code": "BH", "symbol": "BHD", "display_order": 28},
    {"code": "OMR", "name": "Omani Rial", "region": "Middle East", "country_code": "OM", "symbol": "OMR", "display_order": 29},
    {"code": "EGP", "name": "Egyptian Pound", "region": "Middle East / Africa", "country_code": "EG", "symbol": "EGP", "display_order": 30},
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _normalize_security_name(name: str | None) -> str:
    return " ".join(str(name or "").replace('"', "").split()).strip()


def _ensure_cache_dir() -> None:
    UNIVERSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_file(name: str) -> Path:
    return UNIVERSE_CACHE_DIR / name


def _read_meta() -> dict:
    if not UNIVERSE_META_PATH.exists():
        return {}
    try:
        return json.loads(UNIVERSE_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_meta(payload: dict) -> None:
    _ensure_cache_dir()
    UNIVERSE_META_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _cache_age_hours(path: Path) -> float | None:
    if not path.exists():
        return None
    age_seconds = max((_utc_now().timestamp() - path.stat().st_mtime), 0)
    return age_seconds / 3600.0


def _is_cache_fresh(path: Path, ttl_hours: int = MARKET_UNIVERSE_TTL_HOURS) -> bool:
    age = _cache_age_hours(path)
    return age is not None and age <= max(ttl_hours, 1)


def _download_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "MarketAIDashboard/1.0"})
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def _load_or_download(name: str, url: str, force: bool = False) -> tuple[str, str]:
    path = _cache_file(name)
    if not force and _is_cache_fresh(path):
        return path.read_text(encoding="utf-8"), "cache"

    try:
        text = _download_text(url)
        _ensure_cache_dir()
        path.write_text(text, encoding="utf-8")
        return text, "download"
    except Exception:
        if path.exists():
            return path.read_text(encoding="utf-8"), "stale_cache"
        raise


def _iter_rows(text: str) -> list[dict]:
    cleaned_lines = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("File Creation Time"):
            continue
        cleaned_lines.append(line)
    if not cleaned_lines:
        return []
    return list(csv.DictReader(io.StringIO("\n".join(cleaned_lines)), delimiter="|"))


def _normalize_nasdaq_row(row: dict) -> dict | None:
    symbol = _normalize_symbol(row.get("Symbol"))
    if not symbol:
        return None
    is_test_issue = str(row.get("Test Issue", "")).strip().upper() == "Y"
    if is_test_issue:
        return None
    return {
        "symbol": symbol,
        "security_name": _normalize_security_name(row.get("Security Name")),
        "exchange": "NASDAQ",
        "market_type": "ETF" if str(row.get("ETF", "")).strip().upper() == "Y" else MARKET_CATEGORY_MAP.get(str(row.get("Market Category", "")).strip().upper(), "NASDAQ Equity"),
        "is_etf": str(row.get("ETF", "")).strip().upper() == "Y",
        "is_test_issue": is_test_issue,
        "round_lot": _safe_int(row.get("Round Lot Size")),
        "source": "nasdaqlisted.txt",
        "active": True,
    }


def _normalize_other_row(row: dict) -> dict | None:
    symbol = _normalize_symbol(row.get("ACT Symbol"))
    if not symbol:
        return None
    is_test_issue = str(row.get("Test Issue", "")).strip().upper() == "Y"
    if is_test_issue:
        return None
    exchange = OTHER_EXCHANGE_MAP.get(str(row.get("Exchange", "")).strip().upper(), "Other")
    return {
        "symbol": symbol,
        "security_name": _normalize_security_name(row.get("Security Name")),
        "exchange": exchange,
        "market_type": "ETF" if str(row.get("ETF", "")).strip().upper() == "Y" else f"{exchange} Equity",
        "is_etf": str(row.get("ETF", "")).strip().upper() == "Y",
        "is_test_issue": is_test_issue,
        "round_lot": _safe_int(row.get("Round Lot Size")),
        "source": "otherlisted.txt",
        "active": True,
    }


def _safe_int(value) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _extract_json_array(source: str, marker: str) -> list[dict]:
    text = str(source or "")
    marker_index = text.find(marker)
    if marker_index < 0:
        return []
    start = text.find("[", marker_index)
    if start < 0:
        return []
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                raw = text[start:index + 1]
                try:
                    return json.loads(raw)
                except Exception:
                    try:
                        return json.loads(raw.replace('\\"', '"'))
                    except Exception:
                        return []
    return []


def _top_market_cap_page_name(page: int) -> str:
    return f"companiesmarketcap_page_{int(page)}.html"


def _top_market_cap_page_url(page: int) -> str:
    page_number = max(int(page or 1), 1)
    if page_number == 1:
        return TOP_MARKET_CAP_URL
    return f"{TOP_MARKET_CAP_URL}?page={page_number}"


def _load_or_download_top_market_cap_page(page: int, force: bool = False) -> tuple[str, str]:
    return _load_or_download(_top_market_cap_page_name(page), _top_market_cap_page_url(page), force=force)


def _parse_top_market_cap_page(text: str) -> list[dict]:
    items = _extract_json_array(text, "\\\"companies\\\":")
    if not items:
        items = _extract_json_array(text, "\"companies\":")
    normalized: list[dict] = []
    for item in items:
        symbol = _normalize_symbol(item.get("symbol"))
        name = _normalize_security_name(item.get("name"))
        country = str(item.get("country") or "").strip()
        rank = _safe_int(item.get("rank"))
        market_cap = _safe_float(item.get("marketCap"))
        if not symbol or not name or rank is None or market_cap is None:
            continue
        normalized.append(
            {
                "symbol": symbol,
                "security_name": name,
                "country": country or None,
                "market_cap_rank": rank,
                "market_cap": market_cap,
                "market_cap_currency": "USD",
                "market_cap_source": TOP_MARKET_CAP_SOURCE,
            }
        )
    return normalized


def _collect_top_market_cap_companies(*, force: bool = False, target_count: int = TOP_MARKET_CAP_TARGET_COUNT, country_filter: str = TOP_MARKET_CAP_COUNTRY) -> tuple[list[dict], dict]:
    collected: list[dict] = []
    seen_symbols: set[str] = set()
    page_status: dict[str, str] = {}
    normalized_country = str(country_filter or "").strip().upper()
    pages_read = 0
    for page in range(1, TOP_MARKET_CAP_MAX_PAGES + 1):
        text, status = _load_or_download_top_market_cap_page(page, force=force)
        page_status[str(page)] = status
        pages_read = page
        page_items = _parse_top_market_cap_page(text)
        if not page_items:
            break
        for item in page_items:
            item_country = str(item.get("country") or "").strip().upper()
            if normalized_country and item_country != normalized_country:
                continue
            symbol = str(item.get("symbol") or "").upper()
            if symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            collected.append(item)
            if len(collected) >= max(int(target_count or TOP_MARKET_CAP_TARGET_COUNT), 1):
                break
        if len(collected) >= max(int(target_count or TOP_MARKET_CAP_TARGET_COUNT), 1):
            break
    collected.sort(key=lambda item: (int(item.get("market_cap_rank") or 999999), item.get("symbol") or ""))
    for local_rank, item in enumerate(collected, start=1):
        item["market_cap_rank"] = local_rank
    return collected, {
        "pages_read": pages_read,
        "page_status": page_status,
        "country_filter": normalized_country or None,
        "target_count": max(int(target_count or TOP_MARKET_CAP_TARGET_COUNT), 1),
    }


def _categorize_listing(security_name: str | None, is_etf: bool) -> str:
    if is_etf:
        return "etf"
    text = str(security_name or "").strip().lower()
    if not text:
        return "common_stock"
    if "adr" in text or "american depositary" in text:
        return "adr"
    if "reit" in text or "real estate investment trust" in text:
        return "reit"
    if "preferred" in text or "depositary share" in text:
        return "preferred"
    if "warrant" in text or text.endswith(" wt") or " wt " in text:
        return "warrant"
    if "right" in text or text.endswith(" rt") or " rt " in text:
        return "right"
    if "unit" in text or text.endswith(" ut") or text.endswith(" units"):
        return "unit"
    if "fund" in text or "trust" in text or "closed end" in text:
        return "fund"
    return "common_stock"


def _persist_universe(items: list[dict]) -> dict:
    now = _utc_now().replace(tzinfo=None)
    base_sources = {"nasdaqlisted.txt", "otherlisted.txt"}
    with session_scope() as session:
        existing = {
            row.symbol: row
            for row in session.query(MarketUniverseSymbol).all()
        }
        seen_symbols = set()
        inserted = 0
        updated = 0
        for item in items:
            symbol = item["symbol"]
            seen_symbols.add(symbol)
            row = existing.get(symbol)
            if row is None:
                row = MarketUniverseSymbol(symbol=symbol)
                session.add(row)
                inserted += 1
            else:
                updated += 1
            row.security_name = item.get("security_name")
            row.exchange = item.get("exchange")
            row.market_type = item.get("market_type")
            row.is_etf = bool(item.get("is_etf"))
            row.is_test_issue = bool(item.get("is_test_issue"))
            row.round_lot = item.get("round_lot")
            row.source = item.get("source")
            row.country = item.get("country") or row.country
            row.active = bool(item.get("active", True))
            row.updated_at = now

        deactivated = 0
        for symbol, row in existing.items():
            if symbol not in seen_symbols and row.active and str(row.source or "") in base_sources:
                row.active = False
                row.updated_at = now
                deactivated += 1
        return {"inserted": inserted, "updated": updated, "deactivated": deactivated}


def _seed_currency_references() -> dict:
    now = _utc_now().replace(tzinfo=None)
    with session_scope() as session:
        existing = {
            row.code: row
            for row in session.query(CurrencyReference).all()
        }
        inserted = 0
        updated = 0
        seen_codes = set()
        for item in DEFAULT_CURRENCY_REFERENCES:
            code = str(item.get("code") or "").strip().upper()
            if not code:
                continue
            seen_codes.add(code)
            row = existing.get(code)
            if row is None:
                row = CurrencyReference(code=code)
                session.add(row)
                inserted += 1
            else:
                updated += 1
            row.name = str(item.get("name") or code).strip()
            row.kind = str(item.get("kind") or "fiat").strip().lower()
            row.region = item.get("region")
            row.country_code = item.get("country_code")
            row.symbol = item.get("symbol")
            row.is_major = bool(item.get("is_major", False))
            row.active = bool(item.get("active", True))
            row.display_order = item.get("display_order")
            row.quote_symbol = item.get("quote_symbol")
            row.updated_at = now
        disabled = 0
        for code, row in existing.items():
            if code not in seen_codes and row.active:
                row.active = False
                row.updated_at = now
                disabled += 1
        return {
            "inserted": inserted,
            "updated": updated,
            "disabled": disabled,
            "count": len(seen_codes),
        }


def _persist_top_market_cap_rankings(items: list[dict]) -> dict:
    now = _utc_now().replace(tzinfo=None)
    with session_scope() as session:
        existing = {
            row.symbol: row
            for row in session.query(MarketUniverseSymbol).all()
        }
        incoming_symbols = set()
        inserted = 0
        updated = 0
        for item in items:
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            incoming_symbols.add(symbol)
            row = existing.get(symbol)
            if row is None:
                row = MarketUniverseSymbol(
                    symbol=symbol,
                    exchange="US",
                    market_type="US Equity",
                    is_etf=False,
                    is_test_issue=False,
                    source=TOP_MARKET_CAP_SOURCE,
                    active=True,
                )
                session.add(row)
                inserted += 1
            else:
                updated += 1
            row.security_name = item.get("security_name") or row.security_name
            row.country = item.get("country") or row.country
            row.market_cap = item.get("market_cap")
            row.market_cap_rank = item.get("market_cap_rank")
            row.market_cap_currency = item.get("market_cap_currency") or "USD"
            row.market_cap_source = item.get("market_cap_source") or TOP_MARKET_CAP_SOURCE
            row.market_cap_updated_at = now
            row.active = True
            row.updated_at = now

        cleared = 0
        rows = session.query(MarketUniverseSymbol).filter(
            MarketUniverseSymbol.market_cap_rank.is_not(None)
        ).all()
        for row in rows:
            if row.symbol in incoming_symbols:
                continue
            row.market_cap_rank = None
            row.market_cap = None
            row.market_cap_currency = None
            row.market_cap_source = None
            row.market_cap_updated_at = now
            row.updated_at = now
            cleared += 1
        return {
            "inserted": inserted,
            "updated": updated,
            "cleared": cleared,
            "count": len(incoming_symbols),
        }


def refresh_market_universe(force: bool = False) -> dict:
    meta = _read_meta()
    source_status = {}
    top_market_cap_status = {}
    errors = []
    parsed_items: list[dict] = []

    for name, url, normalizer in (
        ("nasdaqlisted.txt", NASDAQ_LISTED_URL, _normalize_nasdaq_row),
        ("otherlisted.txt", OTHER_LISTED_URL, _normalize_other_row),
    ):
        try:
            text, status = _load_or_download(name, url, force=force)
            source_status[name] = status
            for row in _iter_rows(text):
                normalized = normalizer(row)
                if normalized:
                    parsed_items.append(normalized)
        except Exception as exc:
            source_status[name] = "unavailable"
            errors.append(f"{name}: {exc}")

    if not parsed_items:
        db_status = get_universe_status()
        if db_status["total_symbols"] > 0:
            currency_status = _seed_currency_references()
            try:
                top_market_cap_items, top_market_cap_status = _collect_top_market_cap_companies(force=force)
                top_market_cap_persist = _persist_top_market_cap_rankings(top_market_cap_items)
            except Exception as exc:
                top_market_cap_persist = {"status": "error", "error": str(exc)}
                errors.append(f"top_market_cap: {exc}")
            meta.update({
                "last_refresh_status": "stale_db_fallback",
                "last_refresh_error": "; ".join(errors) if errors else "Universe refresh unavailable",
                "last_refresh_at": meta.get("last_refresh_at"),
                "source_status": source_status,
                "currency_status": currency_status,
                "top_market_cap_status": top_market_cap_status,
            })
            _write_meta(meta)
            return {
                "status": "stale_db_fallback",
                "count": db_status["total_symbols"],
                "source_status": source_status,
                "currency_status": currency_status,
                "top_market_cap": top_market_cap_persist,
                "error": meta["last_refresh_error"],
                "db_status": db_status,
            }
        raise RuntimeError("; ".join(errors) if errors else "Unable to refresh market universe.")

    parsed_items.sort(key=lambda item: item["symbol"])
    persist_status = _persist_universe(parsed_items)
    currency_status = _seed_currency_references()
    try:
        top_market_cap_items, top_market_cap_status = _collect_top_market_cap_companies(force=force)
        top_market_cap_persist = _persist_top_market_cap_rankings(top_market_cap_items)
    except Exception as exc:
        top_market_cap_status = {"status": "unavailable", "error": str(exc)}
        top_market_cap_persist = {"status": "unavailable", "error": str(exc)}
        errors.append(f"top_market_cap: {exc}")
    refreshed_at = _utc_now().isoformat()
    meta.update({
        "last_refresh_status": "ok" if not errors else "partial",
        "last_refresh_error": None if not errors else "; ".join(errors),
        "last_refresh_at": refreshed_at,
        "source_status": source_status,
        "currency_status": currency_status,
        "top_market_cap_status": top_market_cap_status,
        "count": len(parsed_items),
    })
    _write_meta(meta)
    return {
        "status": "ok" if not errors else "partial",
        "count": len(parsed_items),
        "source_status": source_status,
        "persist": persist_status,
        "currency_status": currency_status,
        "top_market_cap": top_market_cap_persist,
        "refreshed_at": refreshed_at,
    }


def get_universe_status() -> dict:
    meta = _read_meta()
    cache_files = {
        name: {
            "exists": _cache_file(name).exists(),
            "age_hours": _cache_age_hours(_cache_file(name)),
        }
        for name in ("nasdaqlisted.txt", "otherlisted.txt", *[_top_market_cap_page_name(page) for page in range(1, 4)])
    }
    with session_scope() as session:
        total_symbols = session.query(func.count(MarketUniverseSymbol.id)).filter(
            MarketUniverseSymbol.active.is_(True),
            MarketUniverseSymbol.is_test_issue.is_(False),
        ).scalar() or 0
        nasdaq_count = session.query(func.count(MarketUniverseSymbol.id)).filter(
            MarketUniverseSymbol.active.is_(True),
            MarketUniverseSymbol.exchange == "NASDAQ",
        ).scalar() or 0
        nyse_count = session.query(func.count(MarketUniverseSymbol.id)).filter(
            MarketUniverseSymbol.active.is_(True),
            MarketUniverseSymbol.exchange == "NYSE",
        ).scalar() or 0
        etf_count = session.query(func.count(MarketUniverseSymbol.id)).filter(
            MarketUniverseSymbol.active.is_(True),
            MarketUniverseSymbol.is_etf.is_(True),
        ).scalar() or 0
        top_500_count = session.query(func.count(MarketUniverseSymbol.id)).filter(
            MarketUniverseSymbol.active.is_(True),
            MarketUniverseSymbol.market_cap_rank.is_not(None),
            MarketUniverseSymbol.market_cap_rank <= TOP_MARKET_CAP_TARGET_COUNT,
        ).scalar() or 0
        currency_count = session.query(func.count(CurrencyReference.id)).filter(
            CurrencyReference.active.is_(True),
        ).scalar() or 0
    return {
        "total_symbols": int(total_symbols),
        "nasdaq_count": int(nasdaq_count),
        "nyse_count": int(nyse_count),
        "etf_count": int(etf_count),
        "top_500_market_cap_count": int(top_500_count),
        "currency_count": int(currency_count),
        "ttl_hours": MARKET_UNIVERSE_TTL_HOURS,
        "cache_files": cache_files,
        "last_refresh_at": meta.get("last_refresh_at"),
        "last_refresh_status": meta.get("last_refresh_status"),
        "last_refresh_error": meta.get("last_refresh_error"),
        "cache_dir": str(UNIVERSE_CACHE_DIR),
    }


def ensure_market_universe() -> dict:
    status = get_universe_status()
    if (
        status["total_symbols"] > 0
        and status["currency_count"] > 0
        and any(details["exists"] for details in status["cache_files"].values())
        and (
            status["top_500_market_cap_count"] >= TOP_MARKET_CAP_TARGET_COUNT
            or bool(status.get("last_refresh_at"))
        )
    ):
        return status
    try:
        refresh_market_universe(force=False)
    except Exception:
        pass
    return get_universe_status()


def _serialize_universe_item(row: MarketUniverseSymbol) -> dict:
    listing_category = _categorize_listing(row.security_name, bool(row.is_etf))
    return {
        "symbol": row.symbol,
        "security_name": row.security_name,
        "exchange": row.exchange,
        "market_type": row.market_type,
        "country": row.country,
        "listing_category": listing_category,
        "listing_category_label": CATEGORY_LABELS.get(listing_category, "Other"),
        "asset_group": "etf" if bool(row.is_etf) else "stock",
        "is_etf": bool(row.is_etf),
        "is_test_issue": bool(row.is_test_issue),
        "round_lot": row.round_lot,
        "source": row.source,
        "market_cap": row.market_cap,
        "market_cap_rank": row.market_cap_rank,
        "market_cap_currency": row.market_cap_currency,
        "market_cap_source": row.market_cap_source,
        "active": bool(row.active),
    }


def _search_rank(item: dict, query_text: str) -> tuple[int, str, str]:
    query = str(query_text or "").strip().lower()
    symbol = str(item.get("symbol") or "").lower()
    name = str(item.get("security_name") or "").lower()
    if not query:
        return (10, symbol, name)
    if symbol == query:
        return (0, symbol, name)
    if symbol.startswith(query):
        return (1, symbol, name)
    if name == query:
        return (2, symbol, name)
    if name.startswith(query):
        return (3, symbol, name)
    if query in symbol:
        return (4, symbol, name)
    if query in name:
        return (5, symbol, name)
    return (9, symbol, name)


def _matches_category(item: dict, category_text: str) -> bool:
    normalized = str(category_text or "").strip().lower().replace(" ", "_")
    if normalized in {"", "all", "*"}:
        return True
    if normalized in {"stock", "equity", "common_stock"}:
        return item.get("asset_group") == "stock" and item.get("listing_category") == "common_stock"
    if normalized in {"etf", "fund", "reit", "adr", "preferred", "warrant", "unit", "right", "other"}:
        return item.get("listing_category") == normalized
    return item.get("listing_category") == normalized or item.get("asset_group") == normalized


def get_market_universe_facets() -> dict:
    def factory():
        status = ensure_market_universe()
        with session_scope() as session:
            items = [
                _serialize_universe_item(row)
                for row in session.query(MarketUniverseSymbol).filter(
                    MarketUniverseSymbol.active.is_(True),
                    MarketUniverseSymbol.is_test_issue.is_(False),
                ).all()
            ]

        exchanges = {}
        categories = {}
        for item in items:
            exchange = item.get("exchange") or "Unknown"
            category = item.get("listing_category") or "other"
            exchanges[exchange] = exchanges.get(exchange, 0) + 1
            categories[category] = categories.get(category, 0) + 1

        return {
            "total_symbols": len(items),
            "top_500_market_cap_count": sum(1 for item in items if int(item.get("market_cap_rank") or 0) > 0),
            "currency_count": list_currency_references(limit=500).get("count", 0),
            "exchanges": [
                {"value": key, "label": key, "count": int(value)}
                for key, value in sorted(exchanges.items(), key=lambda item: (-item[1], item[0]))
            ],
            "categories": [
                {"value": key, "label": CATEGORY_LABELS.get(key, "Other"), "count": int(value)}
                for key, value in sorted(categories.items(), key=lambda item: (-item[1], item[0]))
            ],
            "presets": [
                {"value": key, "label": value}
                for key, value in UNIVERSE_PRESET_LABELS.items()
            ],
            "universe_status": status,
        }

    return get_cache().get_or_set("market:universe:facets", factory, ttl_seconds=300)


def _normalize_preset(preset: str | None) -> str:
    value = str(preset or "CUSTOM").strip().upper().replace(" ", "_")
    aliases = {
        "ALL": "ALL_US_EQUITIES",
        "ALL_US": "ALL_US_EQUITIES",
        "ALL_US_STOCKS": "ALL_US_EQUITIES",
        "ALL_US_EQUITY": "ALL_US_EQUITIES",
        "ETF": "ETF_ONLY",
        "ETFS": "ETF_ONLY",
        "TOP500": "TOP_500_MARKET_CAP",
        "TOP_500": "TOP_500_MARKET_CAP",
        "TOP_500_US": "TOP_500_MARKET_CAP",
        "TOP_500_US_MARKET_CAP": "TOP_500_MARKET_CAP",
    }
    return aliases.get(value, value)


def _apply_universe_preset(query, preset: str):
    if preset == "NASDAQ":
        return query.filter(MarketUniverseSymbol.exchange == "NASDAQ")
    if preset == "NYSE":
        return query.filter(MarketUniverseSymbol.exchange.in_(["NYSE", "NYSE American", "NYSE Arca"]))
    if preset == "ETF_ONLY":
        return query.filter(MarketUniverseSymbol.is_etf.is_(True))
    if preset == "TOP_500_MARKET_CAP":
        return query.filter(
            MarketUniverseSymbol.market_cap_rank.is_not(None),
            MarketUniverseSymbol.market_cap_rank <= TOP_MARKET_CAP_TARGET_COUNT,
        )
    return query


def resolve_universe_preset(preset: str, limit: int = 100) -> dict:
    status = ensure_market_universe()
    normalized_preset = _normalize_preset(preset)
    if normalized_preset not in UNIVERSE_PRESET_LABELS or normalized_preset == "CUSTOM":
        raise ValueError("Unsupported universe preset.")

    limit = max(1, min(int(limit or 100), TOP_MARKET_CAP_TARGET_COUNT))
    with session_scope() as session:
        query = session.query(MarketUniverseSymbol).filter(
            MarketUniverseSymbol.active.is_(True),
            MarketUniverseSymbol.is_test_issue.is_(False),
        )
        query = _apply_universe_preset(query, normalized_preset)
        matched_count = query.count()
        if normalized_preset == "TOP_500_MARKET_CAP":
            rows = query.order_by(MarketUniverseSymbol.market_cap_rank.asc(), MarketUniverseSymbol.symbol.asc()).limit(limit).all()
        else:
            rows = query.order_by(MarketUniverseSymbol.symbol.asc()).limit(limit).all()
        symbols = [row.symbol for row in rows]

    return {
        "preset": normalized_preset,
        "label": UNIVERSE_PRESET_LABELS[normalized_preset],
        "symbols": symbols,
        "matched_count": int(matched_count),
        "returned_count": len(symbols),
        "limit": limit,
        "universe_status": status,
    }


def list_currency_references(limit: int = 100, major_only: bool = False) -> dict:
    ensure_market_universe()
    capped_limit = max(1, min(int(limit or 100), 500))
    with session_scope() as session:
        query = session.query(CurrencyReference).filter(CurrencyReference.active.is_(True))
        if major_only:
            query = query.filter(CurrencyReference.is_major.is_(True))
        rows = query.order_by(
            CurrencyReference.display_order.is_(None),
            CurrencyReference.display_order.asc(),
            CurrencyReference.code.asc(),
        ).limit(capped_limit).all()
    items = [
        {
            "code": row.code,
            "name": row.name,
            "kind": row.kind,
            "region": row.region,
            "country_code": row.country_code,
            "symbol": row.symbol,
            "is_major": bool(row.is_major),
            "quote_symbol": row.quote_symbol,
        }
        for row in rows
    ]
    return {
        "count": len(items),
        "items": items,
        "major_only": bool(major_only),
        "limit": capped_limit,
    }


def search_market_universe(
    q: str | None = None,
    exchange: str | None = None,
    security_type: str | None = None,
    category: str | None = None,
    limit: int = 50,
    include_quotes: bool = True,
) -> dict:
    status = ensure_market_universe()
    limit = max(1, min(int(limit or 50), 200))
    query_text = str(q or "").strip()
    exchange_text = str(exchange or "").strip().upper()
    type_text = str(security_type or "").strip().lower()
    category_text = str(category or "").strip().lower()
    cache_key = f"market:universe:search:{query_text}:{exchange_text}:{type_text}:{category_text}:{limit}:{int(bool(include_quotes))}"

    def factory():
        with session_scope() as session:
            query = session.query(MarketUniverseSymbol).filter(
                MarketUniverseSymbol.active.is_(True),
                MarketUniverseSymbol.is_test_issue.is_(False),
            )
            if query_text:
                like = f"%{query_text}%"
                query = query.filter(or_(
                    MarketUniverseSymbol.symbol.ilike(like),
                    MarketUniverseSymbol.security_name.ilike(like),
                ))
            if exchange_text and exchange_text not in {"ALL", "*"}:
                query = query.filter(MarketUniverseSymbol.exchange == exchange_text)
            if type_text == "etf":
                query = query.filter(MarketUniverseSymbol.is_etf.is_(True))
            elif type_text in {"stock", "equity"}:
                query = query.filter(MarketUniverseSymbol.is_etf.is_(False))
            total_matches = query.count()
            row_limit = limit if not query_text else min(max(limit * 8, 80), 600)
            rows = query.order_by(MarketUniverseSymbol.symbol.asc()).limit(row_limit).all()
            items = [_serialize_universe_item(row) for row in rows]

        if category_text and category_text not in {"all", "*"}:
            items = [item for item in items if _matches_category(item, category_text)]
            total_matches = len(items)

        if query_text:
            items.sort(key=lambda item: _search_rank(item, query_text))
        else:
            items.sort(key=lambda item: (str(item.get("symbol") or "").lower(), str(item.get("security_name") or "").lower()))
        items = items[:limit]

        if include_quotes and items:
            snapshots = {
                item["symbol"]: item
                for item in fetch_quote_snapshots([item["symbol"] for item in items], include_profile=False)["items"]
            }
            for item in items:
                item.update(snapshots.get(item["symbol"], {}))

        return {
            "items": items,
            "count": len(items),
            "total_matches": int(total_matches),
            "query": query_text,
            "exchange": exchange_text or "ALL",
            "security_type": type_text or "all",
            "category": category_text or "all",
            "universe_status": status,
        }

    ttl_seconds = 10 if include_quotes else 45
    return get_cache().get_or_set(cache_key, factory, ttl_seconds=ttl_seconds)


def get_market_overview() -> dict:
    status = ensure_market_universe()
    index_items = fetch_quote_snapshots(DEFAULT_INDEX_SYMBOLS, include_profile=False)["items"]
    featured = fetch_quote_snapshots(["AAPL", "MSFT", "NVDA", "SPY", "QQQ", "DIA"], include_profile=False)["items"]
    tracked_leaders = []
    candidate_symbols = []
    for symbol in [*DEFAULT_SAMPLE_SYMBOLS, *TOP_PERFORMER_SYMBOLS]:
        normalized = _normalize_symbol(symbol)
        if normalized and normalized not in candidate_symbols:
            candidate_symbols.append(normalized)
    if candidate_symbols:
        tracked_leaders = fetch_quote_snapshots(candidate_symbols, include_profile=False)["items"]
        tracked_leaders = sorted(
            [item for item in tracked_leaders if item.get("price") is not None],
            key=lambda item: float(item.get("change_pct") or 0.0),
            reverse=True,
        )[:5]
        for index, item in enumerate(tracked_leaders, start=1):
            item["rank"] = index
            item["performance_scope"] = "tracked_leaders"
    for item in index_items:
        item["label"] = INDEX_LABELS.get(item["symbol"], item["symbol"])
        item["exchange"] = "INDEX"
        item["market_type"] = "Index"
    return {
        "generated_at": _utc_now().isoformat(),
        "universe_status": status,
        "indices": index_items,
        "featured": featured,
        "top_performers": tracked_leaders,
    }


def get_market_symbol_snapshot(symbol: str) -> dict:
    status = ensure_market_universe()
    normalized = _normalize_symbol(symbol)
    with session_scope() as session:
        row = session.query(MarketUniverseSymbol).filter(MarketUniverseSymbol.symbol == normalized).first()
        metadata = None if row is None else {
            "symbol": row.symbol,
            "security_name": row.security_name,
            "exchange": row.exchange,
            "market_type": row.market_type,
            "country": row.country,
            "is_etf": bool(row.is_etf),
            "round_lot": row.round_lot,
            "source": row.source,
            "market_cap": row.market_cap,
            "market_cap_rank": row.market_cap_rank,
            "market_cap_currency": row.market_cap_currency,
            "active": bool(row.active),
        }
    quote_items = fetch_quote_snapshots([normalized], include_profile=True)["items"]
    history = load_history(normalized, interval="1d", persist=True)
    return {
        "symbol": normalized,
        "metadata": metadata,
        "quote": quote_items[0] if quote_items else None,
        "history": history,
        "universe_status": status,
    }
