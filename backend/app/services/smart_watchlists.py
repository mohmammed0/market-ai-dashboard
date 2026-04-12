from __future__ import annotations

from backend.app.config import AUTOMATION_WATCHLIST_SYMBOL_LIMIT
from backend.app.models import SignalHistory
from backend.app.services.breadth_engine import compute_sector_rotation
from backend.app.services.market_data import fetch_quote_snapshots, load_history
from backend.app.services.market_universe import resolve_universe_preset
from backend.app.services.storage import session_scope


def _volume_ratio(symbol: str) -> float | None:
    history = load_history(symbol, interval="1d", persist=True)
    if history.get("error"):
        return None
    items = history.get("items", [])
    if len(items) < 10:
        return None
    latest = items[-1]
    volume = float(latest.get("volume") or 0.0)
    previous = [float(item.get("volume") or 0.0) for item in items[-21:-1] if item.get("volume") is not None]
    if not previous:
        return None
    avg = sum(previous) / len(previous)
    if avg <= 0:
        return None
    return round(volume / avg, 3)


def build_dynamic_watchlists(preset: str = "ALL_US_EQUITIES", limit: int = AUTOMATION_WATCHLIST_SYMBOL_LIMIT) -> dict:
    try:
        universe = resolve_universe_preset(preset, limit=limit)
    except Exception as exc:
        return {
            "preset": preset,
            "momentum_leaders": [],
            "unusual_volume": [],
            "signal_focus": [],
            "sector_leaders": [],
            "error": str(exc),
        }
    symbols = universe.get("symbols", [])
    snapshots = fetch_quote_snapshots(symbols, include_profile=False).get("items", [])
    top_momentum = sorted(snapshots, key=lambda item: float(item.get("change_pct") or 0.0), reverse=True)[:10]

    unusual_volume = []
    for item in snapshots[: min(len(snapshots), 20)]:
        ratio = _volume_ratio(item["symbol"])
        if ratio and ratio >= 1.8:
            unusual_volume.append({**item, "volume_ratio": ratio})
    unusual_volume.sort(key=lambda item: item.get("volume_ratio", 0.0), reverse=True)

    with session_scope() as session:
        rows = (
            session.query(SignalHistory)
            .order_by(SignalHistory.created_at.desc())
            .limit(150)
            .all()
        )
        latest_by_symbol = {}
        for row in rows:
            latest_by_symbol.setdefault(
                row.symbol,
                {
                    "symbol": row.symbol,
                    "strategy_mode": row.strategy_mode,
                    "signal": row.signal,
                    "confidence": row.confidence,
                    "price": row.price,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                },
            )

    signal_focus = [
        row
        for row in latest_by_symbol.values()
        if str(row.get("signal")).upper() in {"BUY", "SELL"}
    ]
    signal_focus.sort(key=lambda item: float(item.get("confidence") or 0.0), reverse=True)

    sector_rotation = compute_sector_rotation()
    return {
        "preset": preset,
        "momentum_leaders": top_momentum,
        "unusual_volume": unusual_volume[:10],
        "signal_focus": signal_focus[:10],
        "sector_leaders": sector_rotation.get("leaders", []),
    }
