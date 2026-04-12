from __future__ import annotations

from datetime import datetime

from backend.app.services.market_data import DEFAULT_SYMBOLS

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency
    yf = None


def fetch_market_events(symbols: list[str] | None = None, limit: int = 20) -> dict:
    symbols = [str(symbol).strip().upper() for symbol in (symbols or DEFAULT_SYMBOLS) if str(symbol).strip()]
    items = []
    provider_status = "yfinance" if yf is not None else "unavailable"

    if yf is None:
        return {
            "provider_status": provider_status,
            "items": [],
            "note": "No clean event provider is available in the current environment.",
        }

    for symbol in symbols[: max(1, limit)]:
        try:
            ticker = yf.Ticker(symbol.replace(".", "-"))
            info = getattr(ticker, "info", None) or {}
            event_candidates = [
                ("earnings", info.get("earningsTimestamp")),
                ("earnings_window_start", info.get("earningsTimestampStart")),
                ("earnings_window_end", info.get("earningsTimestampEnd")),
                ("ex_dividend", info.get("exDividendDate")),
                ("dividend", info.get("dividendDate")),
            ]
            for event_type, raw_value in event_candidates:
                if not raw_value:
                    continue
                try:
                    event_at = datetime.utcfromtimestamp(int(raw_value)).isoformat()
                except Exception:
                    continue
                items.append({
                    "symbol": symbol,
                    "event_type": event_type,
                    "event_at": event_at,
                    "source": "yfinance_info",
                })
        except Exception:
            continue

    items.sort(key=lambda item: item["event_at"])
    return {
        "provider_status": provider_status,
        "items": items[:limit],
        "note": None if items else "Event data is not currently available from the active provider.",
    }
