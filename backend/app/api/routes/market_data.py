from fastapi import APIRouter

from backend.app.schemas.requests import HistoryRequest, QuoteRequest
from backend.app.market_data.service import (
    fetch_and_publish_quote_snapshots,
    incremental_update_and_publish,
    load_and_publish_history,
)
from backend.app.services.live_stream import get_live_stream_snapshot


router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.post("/history")
def get_history(payload: HistoryRequest):
    return load_and_publish_history(
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
            items.append(incremental_update_and_publish(symbol))
        except Exception as exc:
            items.append({"symbol": symbol, "error": str(exc)})
    return {"items": items}


@router.post("/live-snapshot")
def live_snapshot(payload: QuoteRequest):
    stream_payload = get_live_stream_snapshot(payload.symbols, poll_interval=3)
    snapshot_payload = fetch_and_publish_quote_snapshots(payload.symbols)
    if stream_payload.get("items"):
        return {
            **snapshot_payload,
            "live_items": stream_payload.get("items"),
            "live_stream": stream_payload.get("stream"),
        }
    return {
        **snapshot_payload,
        "live_stream": stream_payload.get("stream"),
    }
