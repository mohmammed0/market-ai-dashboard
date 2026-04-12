"""SEC EDGAR fundamentals data fetcher.

Free API -- no authentication required.
Base URLs:
  https://data.sec.gov/submissions/{CIK}.json         -- company facts
  https://data.sec.gov/api/xbrl/companyfacts/{CIK}.json -- financials
  https://www.sec.gov/files/company_tickers.json       -- ticker -> CIK map
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EDGAR_HEADERS = {"User-Agent": "MarketAIDashboard research@example.com"}
EDGAR_BASE = "https://data.sec.gov"
SEC_BASE = "https://www.sec.gov"

# Module-level cache: populated once per process lifetime
_ticker_cik_map: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# CIK lookup
# ---------------------------------------------------------------------------

def _load_ticker_cik_map() -> dict[str, str]:
    """Fetch the static company_tickers.json from SEC (cached for process lifetime)."""
    global _ticker_cik_map
    if _ticker_cik_map is not None:
        return _ticker_cik_map
    url = f"{SEC_BASE}/files/company_tickers.json"
    try:
        resp = httpx.get(url, headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        # Structure: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ...}
        mapping: dict[str, str] = {}
        for entry in data.values():
            ticker = str(entry.get("ticker", "")).upper()
            cik = str(entry.get("cik_str", ""))
            if ticker and cik:
                mapping[ticker] = cik
        _ticker_cik_map = mapping
        logger.info("edgar.cik_map.loaded count=%d", len(mapping))
        return mapping
    except Exception as exc:
        logger.warning("edgar.cik_map.load_failed error=%s", exc)
        _ticker_cik_map = {}
        return {}


def get_cik_for_ticker(ticker: str) -> str | None:
    """Return the CIK (zero-padded to 10 digits) for a ticker symbol, or None."""
    mapping = _load_ticker_cik_map()
    cik = mapping.get(ticker.upper())
    if cik is None:
        logger.warning("edgar.cik_not_found ticker=%s", ticker)
        return None
    # Pad to 10 digits as required by EDGAR API
    return cik.zfill(10)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_json(url: str) -> dict | None:
    """Fetch JSON from EDGAR; return None on any error."""
    try:
        resp = httpx.get(url, headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("edgar.fetch_failed url=%s error=%s", url, exc)
        return None


def _extract_concept_values(
    facts: dict,
    namespace: str,
    concept: str,
    unit: str = "USD",
) -> list[dict]:
    """Extract filing values for a given XBRL concept from companyfacts JSON.

    Returns a list of dicts sorted by end date (most recent last).
    Only includes 10-K and 10-Q forms.
    """
    try:
        entries = (
            facts.get("facts", {})
            .get(namespace, {})
            .get(concept, {})
            .get("units", {})
            .get(unit, [])
        )
    except (AttributeError, TypeError):
        return []

    results = []
    for entry in entries:
        if entry.get("form") not in ("10-K", "10-Q"):
            continue
        if not entry.get("end"):
            continue
        results.append(entry)

    # Sort by end date ascending
    results.sort(key=lambda x: x.get("end", ""))
    return results


def _has_recent_data(entries: list[dict], years: int = 3) -> bool:
    """Return True if entries contain data within the last N years."""
    if not entries:
        return False
    from datetime import date
    cutoff = str(date.today().year - years)
    return any(e.get("end", "") >= cutoff for e in entries)


def _latest_annual_values(entries: list[dict], n: int = 4) -> list[dict]:
    """Return the last N annual (10-K) entries -- deduplicated by end date."""
    seen: set[str] = set()
    annual = []
    for e in reversed(entries):
        if e.get("form") != "10-K":
            continue
        end = e.get("end", "")
        if end in seen:
            continue
        seen.add(end)
        annual.append(e)
        if len(annual) >= n:
            break
    return list(reversed(annual))  # oldest first


def _latest_quarterly_values(entries: list[dict], n: int = 4) -> list[dict]:
    """Return the last N period entries (10-Q preferred, 10-K as fallback) deduplicated by end date."""
    seen: set[str] = set()
    quarterly = []
    for e in reversed(entries):
        if e.get("form") not in ("10-Q", "10-K"):
            continue
        end = e.get("end", "")
        if end in seen:
            continue
        seen.add(end)
        quarterly.append(e)
        if len(quarterly) >= n:
            break
    return list(reversed(quarterly))  # oldest first


def _pick_best_revenue_entries(facts: dict) -> list[dict]:
    """Pick the best revenue concept for the company, preferring most recent data.

    Tries EDGAR revenue tags in order and returns the first set that has
    recent data (within last 3 years).
    """
    candidates = [
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
        ("us-gaap", "Revenues", "USD"),
        ("us-gaap", "SalesRevenueNet", "USD"),
        ("us-gaap", "SalesRevenueGoodsNet", "USD"),
        ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax", "USD"),
    ]
    best: list[dict] = []
    for ns, concept, unit in candidates:
        entries = _extract_concept_values(facts, ns, concept, unit)
        if entries and _has_recent_data(entries):
            if len(entries) > len(best):
                best = entries
    # If nothing recent, fall back to any non-empty set
    if not best:
        for ns, concept, unit in candidates:
            entries = _extract_concept_values(facts, ns, concept, unit)
            if entries:
                return entries
    return best


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_company_facts(ticker: str) -> dict:
    """Return key financial facts for a ticker from SEC EDGAR.

    Fetches XBRL company facts and extracts:
      - NetIncomeLoss, Revenues, EarningsPerShareBasic, Assets, Liabilities

    Returns a structured dict with last 4 quarters + last 4 annual totals for
    each concept. Returns empty dict on error.
    """
    cik = get_cik_for_ticker(ticker)
    if cik is None:
        return {}

    url = f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
    facts = _get_json(url)
    if facts is None:
        return {}

    entity_name = facts.get("entityName", ticker)

    def _concept(namespace: str, concept: str, unit: str = "USD") -> list[dict]:
        return _extract_concept_values(facts, namespace, concept, unit)

    def _fmt_entries(entries: list[dict]) -> list[dict]:
        return [
            {
                "end": e.get("end"),
                "value": e.get("val"),
                "form": e.get("form"),
                "filed": e.get("filed"),
            }
            for e in entries
        ]

    revenue_entries = _pick_best_revenue_entries(facts)
    net_income_entries = _concept("us-gaap", "NetIncomeLoss")
    eps_entries = _concept("us-gaap", "EarningsPerShareBasic", unit="USD/shares")
    assets_entries = _concept("us-gaap", "Assets")
    liabilities_entries = _concept("us-gaap", "Liabilities")

    return {
        "ticker": ticker.upper(),
        "entity_name": entity_name,
        "cik": cik,
        "revenue": {
            "quarterly": _fmt_entries(_latest_quarterly_values(revenue_entries, 4)),
            "annual": _fmt_entries(_latest_annual_values(revenue_entries, 4)),
        },
        "net_income": {
            "quarterly": _fmt_entries(_latest_quarterly_values(net_income_entries, 4)),
            "annual": _fmt_entries(_latest_annual_values(net_income_entries, 4)),
        },
        "eps_basic": {
            "quarterly": _fmt_entries(_latest_quarterly_values(eps_entries, 4)),
            "annual": _fmt_entries(_latest_annual_values(eps_entries, 4)),
        },
        "assets": {
            "annual": _fmt_entries(_latest_annual_values(assets_entries, 4)),
        },
        "liabilities": {
            "annual": _fmt_entries(_latest_annual_values(liabilities_entries, 4)),
        },
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": "SEC EDGAR",
    }


def get_fundamentals_snapshot(ticker: str) -> dict:
    """Return a compact fundamentals summary for dashboard display.

    Computes trailing-twelve-month (TTM) aggregates from the last 4 quarters of
    EDGAR data. Returns a minimal dict suitable for embedding in dashboard cards.

    Keys returned:
      ticker, entity_name, revenue_ttm, net_income_ttm, eps_ttm,
      debt_to_equity (when data available), data_date, source, fetched_at

    All monetary values are in USD (whole dollars). Returns a minimal error dict
    on failure -- never raises.
    """
    try:
        facts = get_company_facts(ticker)
    except Exception as exc:
        logger.warning("edgar.snapshot.facts_error ticker=%s error=%s", ticker, exc)
        facts = {}

    if not facts:
        return {
            "ticker": ticker.upper(),
            "error": "CIK not found or EDGAR data unavailable",
            "source": "SEC EDGAR",
        }

    def _sum_quarterly(key: str) -> float | None:
        """Sum last-4-quarter values for TTM."""
        entries = facts.get(key, {}).get("quarterly", [])
        if not entries:
            return None
        vals = [e["value"] for e in entries if e.get("value") is not None]
        if not vals:
            return None
        return sum(vals)

    def _latest_annual(key: str) -> float | None:
        entries = facts.get(key, {}).get("annual", [])
        for e in reversed(entries):
            if e.get("value") is not None:
                return e["value"]
        return None

    def _latest_date(key: str) -> str | None:
        entries = facts.get(key, {}).get("quarterly", [])
        if not entries:
            entries = facts.get(key, {}).get("annual", [])
        for e in reversed(entries):
            if e.get("end"):
                return e["end"]
        return None

    revenue_ttm = _sum_quarterly("revenue")
    net_income_ttm = _sum_quarterly("net_income")
    eps_ttm = _sum_quarterly("eps_basic")

    # Debt-to-equity: liabilities / (assets - liabilities)
    debt_to_equity: float | None = None
    try:
        assets = _latest_annual("assets")
        liabilities = _latest_annual("liabilities")
        if assets is not None and liabilities is not None:
            equity = assets - liabilities
            if equity > 0:
                debt_to_equity = round(liabilities / equity, 3)
    except Exception:
        pass

    data_date = (
        _latest_date("revenue")
        or _latest_date("net_income")
        or _latest_date("eps_basic")
    )

    result: dict[str, Any] = {
        "ticker": ticker.upper(),
        "entity_name": facts.get("entity_name", ticker.upper()),
        "revenue_ttm": revenue_ttm,
        "net_income_ttm": net_income_ttm,
        "eps_ttm": eps_ttm,
        "debt_to_equity": debt_to_equity,
        "data_date": data_date,
        "source": "SEC EDGAR",
        "fetched_at": datetime.now(UTC).isoformat(),
    }

    logger.info(
        "edgar.snapshot ticker=%s revenue_ttm=%s net_income_ttm=%s eps_ttm=%s",
        ticker.upper(),
        revenue_ttm,
        net_income_ttm,
        eps_ttm,
    )
    return result
