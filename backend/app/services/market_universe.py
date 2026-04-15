from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from sqlalchemy import func, or_

from backend.app.config import DEFAULT_INDEX_SYMBOLS, DEFAULT_SAMPLE_SYMBOLS, MARKET_UNIVERSE_TTL_HOURS, RUNTIME_CACHE_DIR
from backend.app.models import MarketUniverseSymbol
from backend.app.services import get_cache
from backend.app.services.market_data import fetch_quote_snapshots, load_history
from backend.app.services.storage import session_scope


UNIVERSE_CACHE_DIR = RUNTIME_CACHE_DIR / "market_universe"
UNIVERSE_META_PATH = UNIVERSE_CACHE_DIR / "universe_meta.json"
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

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
            row.active = bool(item.get("active", True))
            row.updated_at = now

        deactivated = 0
        for symbol, row in existing.items():
            if symbol not in seen_symbols and row.active:
                row.active = False
                row.updated_at = now
                deactivated += 1
        return {"inserted": inserted, "updated": updated, "deactivated": deactivated}


def refresh_market_universe(force: bool = False) -> dict:
    meta = _read_meta()
    source_status = {}
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
            meta.update({
                "last_refresh_status": "stale_db_fallback",
                "last_refresh_error": "; ".join(errors) if errors else "Universe refresh unavailable",
                "last_refresh_at": meta.get("last_refresh_at"),
                "source_status": source_status,
            })
            _write_meta(meta)
            return {
                "status": "stale_db_fallback",
                "count": db_status["total_symbols"],
                "source_status": source_status,
                "error": meta["last_refresh_error"],
                "db_status": db_status,
            }
        raise RuntimeError("; ".join(errors) if errors else "Unable to refresh market universe.")

    parsed_items.sort(key=lambda item: item["symbol"])
    persist_status = _persist_universe(parsed_items)
    refreshed_at = _utc_now().isoformat()
    meta.update({
        "last_refresh_status": "ok",
        "last_refresh_error": None,
        "last_refresh_at": refreshed_at,
        "source_status": source_status,
        "count": len(parsed_items),
    })
    _write_meta(meta)
    return {
        "status": "ok",
        "count": len(parsed_items),
        "source_status": source_status,
        "persist": persist_status,
        "refreshed_at": refreshed_at,
    }


def get_universe_status() -> dict:
    meta = _read_meta()
    cache_files = {
        name: {
            "exists": _cache_file(name).exists(),
            "age_hours": _cache_age_hours(_cache_file(name)),
        }
        for name in ("nasdaqlisted.txt", "otherlisted.txt")
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
    return {
        "total_symbols": int(total_symbols),
        "nasdaq_count": int(nasdaq_count),
        "nyse_count": int(nyse_count),
        "etf_count": int(etf_count),
        "ttl_hours": MARKET_UNIVERSE_TTL_HOURS,
        "cache_files": cache_files,
        "last_refresh_at": meta.get("last_refresh_at"),
        "last_refresh_status": meta.get("last_refresh_status"),
        "last_refresh_error": meta.get("last_refresh_error"),
        "cache_dir": str(UNIVERSE_CACHE_DIR),
    }


def ensure_market_universe() -> dict:
    status = get_universe_status()
    if status["total_symbols"] > 0 and any(details["exists"] for details in status["cache_files"].values()):
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
        "listing_category": listing_category,
        "listing_category_label": CATEGORY_LABELS.get(listing_category, "Other"),
        "asset_group": "etf" if bool(row.is_etf) else "stock",
        "is_etf": bool(row.is_etf),
        "is_test_issue": bool(row.is_test_issue),
        "round_lot": row.round_lot,
        "source": row.source,
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
    }
    return aliases.get(value, value)


def _apply_universe_preset(query, preset: str):
    if preset == "NASDAQ":
        return query.filter(MarketUniverseSymbol.exchange == "NASDAQ")
    if preset == "NYSE":
        return query.filter(MarketUniverseSymbol.exchange.in_(["NYSE", "NYSE American", "NYSE Arca"]))
    if preset == "ETF_ONLY":
        return query.filter(MarketUniverseSymbol.is_etf.is_(True))
    return query


def resolve_universe_preset(preset: str, limit: int = 100) -> dict:
    status = ensure_market_universe()
    normalized_preset = _normalize_preset(preset)
    if normalized_preset not in UNIVERSE_PRESET_LABELS or normalized_preset == "CUSTOM":
        raise ValueError("Unsupported universe preset.")

    limit = max(1, min(int(limit or 100), 250))
    with session_scope() as session:
        query = session.query(MarketUniverseSymbol).filter(
            MarketUniverseSymbol.active.is_(True),
            MarketUniverseSymbol.is_test_issue.is_(False),
        )
        query = _apply_universe_preset(query, normalized_preset)
        matched_count = query.count()
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
            "is_etf": bool(row.is_etf),
            "round_lot": row.round_lot,
            "source": row.source,
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
