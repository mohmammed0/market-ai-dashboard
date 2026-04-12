from fastapi import APIRouter

from backend.app.schemas.requests import EventCalendarRequest
from backend.app.services.events_calendar import fetch_market_events


router = APIRouter(prefix="/events", tags=["events"])


@router.post("/calendar")
def events_calendar(payload: EventCalendarRequest):
    return fetch_market_events(symbols=payload.symbols, limit=payload.limit)
