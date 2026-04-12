"""FRED (Federal Reserve Economic Data) macro indicator fetcher.

Free API — no authentication required for most series.
Base URL: https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES_ID
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

FRED_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# Key macro series: {series_id: (label, category, description)}
FRED_SERIES = {
    "FEDFUNDS": ("Fed Funds Rate", "rates", "Federal Funds Effective Rate (%)"),
    "T10Y2Y": ("10Y-2Y Spread", "rates", "10-Year minus 2-Year Treasury Yield Spread (%)"),
    "T10YIE": ("10Y Breakeven Inflation", "inflation", "10-Year Breakeven Inflation Rate (%)"),
    "CPIAUCSL": ("CPI YoY", "inflation", "Consumer Price Index, All Urban Consumers"),
    "UNRATE": ("Unemployment Rate", "labor", "Unemployment Rate (%)"),
    "VIXCLS": ("VIX", "volatility", "CBOE Volatility Index (VIX)"),
    "SP500": ("S&P 500", "equity", "S&P 500 Index"),
    "DTWEXBGS": ("USD Index", "fx", "Trade-Weighted US Dollar Index"),
    "DCOILWTICO": ("WTI Crude Oil", "commodities", "Crude Oil Prices: West Texas Intermediate"),
    "BAMLH0A0HYM2": ("HY Spread", "credit", "ICE BofA US High Yield Index OAS (%)"),
}


def _fetch_series(series_id: str, limit: int = 12) -> list[dict]:
    """Fetch last N observations for a FRED series."""
    url = f"{FRED_BASE}?id={series_id}"
    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "MarketAIDashboard/1.0 research@example.com",
                "Accept": "text/csv,*/*",
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=httpx.Timeout(connect=8.0, read=20.0, write=8.0, pool=8.0),
            follow_redirects=True,
        )
        resp.raise_for_status()
        content = resp.text
        reader = csv.DictReader(io.StringIO(content))
        # FRED CSV header: "observation_date,{SERIES_ID}" — not "VALUE"
        all_rows = list(reader)
        if not all_rows:
            return []
        # Get the value column (second column = series_id)
        val_col = [c for c in all_rows[0].keys() if c != "observation_date"]
        if not val_col:
            return []
        val_key = val_col[0]
        # Filter out missing values (FRED uses "." for N/A)
        rows = [
            {"DATE": r["observation_date"], "VALUE": r[val_key]}
            for r in all_rows
            if r.get(val_key, ".") not in (".", "", None)
        ]
        return rows[-limit:] if len(rows) > limit else rows
    except Exception as exc:
        logger.warning("fred.fetch_failed series=%s error=%s", series_id, exc)
        return []


def get_macro_snapshot() -> dict:
    """Return latest value + 1M change for each key macro indicator."""
    results = []
    for series_id, (label, category, description) in FRED_SERIES.items():
        rows = _fetch_series(series_id, limit=2)
        if not rows:
            continue
        try:
            latest = rows[-1]
            prev = rows[-2] if len(rows) > 1 else None
            value = float(latest["VALUE"])
            prev_value = float(prev["VALUE"]) if prev else None
            change = round(value - prev_value, 4) if prev_value is not None else None
            results.append({
                "series_id": series_id,
                "label": label,
                "category": category,
                "description": description,
                "value": round(value, 4),
                "prev_value": round(prev_value, 4) if prev_value is not None else None,
                "change": change,
                "date": latest["DATE"],
                "prev_date": prev["DATE"] if prev else None,
            })
        except (ValueError, KeyError):
            continue
    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "source": "FRED (Federal Reserve Economic Data)",
        "indicators": results,
    }


def get_macro_calendar() -> dict:
    """Return VIX regime + yield curve signal for current macro environment."""
    snapshot = get_macro_snapshot()
    indicators = {item["series_id"]: item for item in snapshot["indicators"]}

    vix_item = indicators.get("VIXCLS", {})
    spread_item = indicators.get("T10Y2Y", {})
    ff_item = indicators.get("FEDFUNDS", {})
    hy_item = indicators.get("BAMLH0A0HYM2", {})

    vix = vix_item.get("value")
    spread = spread_item.get("value")
    ff_rate = ff_item.get("value")
    hy_spread = hy_item.get("value")

    # Regime signals
    vix_regime = "low_vol" if vix and vix < 15 else ("elevated_vol" if vix and vix < 25 else "high_vol") if vix else "unknown"
    curve_signal = "normal" if spread and spread > 0 else ("flat" if spread and spread > -0.25 else "inverted") if spread is not None else "unknown"
    credit_signal = "tight" if hy_spread and hy_spread < 350 else ("normal" if hy_spread and hy_spread < 550 else "wide") if hy_spread else "unknown"

    macro_score = 50  # neutral baseline
    if vix and vix < 20: macro_score += 10
    if vix and vix > 30: macro_score -= 20
    if spread and spread > 0: macro_score += 10
    if spread and spread < -0.5: macro_score -= 15
    if hy_spread and hy_spread < 400: macro_score += 10
    if hy_spread and hy_spread > 600: macro_score -= 15
    macro_score = max(0, min(100, macro_score))

    return {
        "updated_at": snapshot["updated_at"],
        "macro_score": macro_score,
        "macro_regime": "risk_on" if macro_score >= 60 else ("neutral" if macro_score >= 40 else "risk_off"),
        "vix_regime": vix_regime,
        "yield_curve": curve_signal,
        "credit_conditions": credit_signal,
        "vix": vix,
        "yield_spread_10y2y": spread,
        "fed_funds_rate": ff_rate,
        "hy_spread": hy_spread,
        "indicators": snapshot["indicators"],
    }
