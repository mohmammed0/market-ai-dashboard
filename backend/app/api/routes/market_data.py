from fastapi import APIRouter

from backend.app.schemas.requests import HistoryRequest, QuoteRequest
from backend.app.services.market_data import fetch_quote_snapshots, incremental_update, load_history


router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.post("/history")
def get_history(payload: HistoryRequest):
    return load_history(
        symbol=payload.symbol,
        start_date=payload.start_date,
        end_date=payload.end_date,
        interval=payload.interval,
        persist=True,
    )


@router.post("/update")
def update_history(payload: QuoteRequest):
    items = []
    for symbol in payload.symbols:
        try:
            items.append(incremental_update(symbol))
        except Exception as exc:
            items.append({"symbol": symbol, "error": str(exc)})
    return {"items": items}


@router.post("/live-snapshot")
def live_snapshot(payload: QuoteRequest):
    return fetch_quote_snapshots(payload.symbols)
