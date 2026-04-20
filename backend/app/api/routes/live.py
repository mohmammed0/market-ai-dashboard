from fastapi import APIRouter, Query

from backend.app.market_data.service import fetch_quote_snapshots
from backend.app.services.pipeline_live import get_pipeline_feed
from backend.app.services.live_stream import get_live_stream_snapshot


router = APIRouter(prefix="/live", tags=["live"])


@router.get("/quotes")
def get_live_quotes(
    symbols: list[str] = Query(default=[]),
    prefer_stream: bool = Query(default=True),
):
    stream_payload = get_live_stream_snapshot(symbols, poll_interval=3)
    if prefer_stream and stream_payload.get("items"):
        return {
            **stream_payload,
            "provider_status": "live_stream",
        }
    snapshot_payload = fetch_quote_snapshots(symbols)
    return {
        **snapshot_payload,
        "stream": stream_payload.get("stream"),
        "stream_count": stream_payload.get("count"),
        "stream_errors": stream_payload.get("errors"),
    }


@router.get("/pipeline")
def get_live_pipeline(
    limit_events: int = Query(default=40, ge=5, le=120),
    limit_cycles: int = Query(default=8, ge=1, le=30),
):
    return get_pipeline_feed(limit_events=limit_events, limit_cycles=limit_cycles)
