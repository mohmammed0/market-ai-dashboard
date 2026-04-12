from __future__ import annotations

from statistics import mean

from backend.app.config import AUTOMATION_BREADTH_SYMBOL_LIMIT
from backend.app.services.market_data import fetch_quote_snapshots, load_history
from backend.app.services.market_universe import resolve_universe_preset


SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}


def compute_market_breadth(preset: str = "ALL_US_EQUITIES", limit: int = AUTOMATION_BREADTH_SYMBOL_LIMIT) -> dict:
    try:
        universe = resolve_universe_preset(preset, limit=limit)
    except Exception as exc:
        return {
            "preset": preset,
            "sample_size": 0,
            "advancing": 0,
            "declining": 0,
            "unchanged": 0,
            "breadth_ratio": 0.0,
            "advance_decline_delta": 0,
            "average_change_pct": 0.0,
            "new_highs_sample": 0,
            "new_lows_sample": 0,
            "leaders": [],
            "laggards": [],
            "universe": {"error": str(exc), "symbols": []},
            "error": str(exc),
        }
    symbols = universe.get("symbols", [])
    snapshot_payload = fetch_quote_snapshots(symbols, include_profile=False)
    snapshots = snapshot_payload.get("items", [])
    errors = [
        {
            "symbol": item.get("symbol"),
            "stage": "snapshot",
            "error": item.get("error"),
        }
        for item in snapshot_payload.get("errors", [])
        if item.get("error")
    ]
    advancing = [item for item in snapshots if float(item.get("change_pct") or 0.0) > 0]
    declining = [item for item in snapshots if float(item.get("change_pct") or 0.0) < 0]
    unchanged = [item for item in snapshots if float(item.get("change_pct") or 0.0) == 0]

    new_highs = 0
    new_lows = 0
    for item in snapshots[: min(len(snapshots), 25)]:
        history = load_history(item["symbol"], interval="1d", persist=True)
        if history.get("error"):
            errors.append({
                "symbol": item["symbol"],
                "stage": "history",
                "error": history.get("error"),
            })
            continue
        bars = history.get("items", [])
        if len(bars) < 20:
            continue
        closes = [float(bar.get("close") or 0.0) for bar in bars[-60:] if bar.get("close") is not None]
        if not closes:
            continue
        current = closes[-1]
        if current >= max(closes):
            new_highs += 1
        if current <= min(closes):
            new_lows += 1

    avg_change = round(mean([float(item.get("change_pct") or 0.0) for item in snapshots]), 3) if snapshots else 0.0
    breadth_ratio = round((len(advancing) / max(len(declining), 1)), 3)
    failed_symbols = sorted({item.get("symbol") for item in errors if item.get("symbol")})
    return {
        "preset": preset,
        "requested_symbols": len(symbols),
        "sample_size": len(snapshots),
        "advancing": len(advancing),
        "declining": len(declining),
        "unchanged": len(unchanged),
        "breadth_ratio": breadth_ratio,
        "advance_decline_delta": len(advancing) - len(declining),
        "average_change_pct": avg_change,
        "new_highs_sample": new_highs,
        "new_lows_sample": new_lows,
        "leaders": sorted(snapshots, key=lambda item: float(item.get("change_pct") or 0.0), reverse=True)[:8],
        "laggards": sorted(snapshots, key=lambda item: float(item.get("change_pct") or 0.0))[:8],
        "universe": universe,
        "failed_symbols": len(failed_symbols),
        "error_symbols": failed_symbols[:25],
        "errors": errors[:25],
    }


def compute_sector_rotation() -> dict:
    snapshot_payload = fetch_quote_snapshots(list(SECTOR_ETFS.keys()), include_profile=False)
    items = snapshot_payload.get("items", [])
    ranked = []
    for item in items:
        ranked.append({
            "symbol": item["symbol"],
            "sector": SECTOR_ETFS.get(item["symbol"], item["symbol"]),
            "price": item.get("price"),
            "change_pct": item.get("change_pct"),
            "volume": item.get("volume"),
            "market_cap": item.get("market_cap"),
        })
    ranked.sort(key=lambda item: float(item.get("change_pct") or 0.0), reverse=True)
    failed_symbols = sorted({item.get("symbol") for item in snapshot_payload.get("errors", []) if item.get("symbol")})
    return {
        "leaders": ranked[:3],
        "laggards": ranked[-3:],
        "ranking": ranked,
        "failed_symbols": len(failed_symbols),
        "error_symbols": failed_symbols[:25],
        "errors": snapshot_payload.get("errors", [])[:25],
    }
