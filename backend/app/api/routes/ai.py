from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.schemas import AINewsAnalyzeRequest, AIStatus
from backend.app.services.ai_news_analyst import analyze_news
from backend.app.services.llm_gateway import get_llm_status, LLMUnavailableError
from backend.app.services.news_feed import refresh_news_feed
from backend.app.models.market import NewsRecord
from backend.app.db import get_db


router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status", response_model=AIStatus)
def ai_status():
    return get_llm_status()


@router.get("/news/feed")
def get_news_feed(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to today"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    instrument: Optional[str] = Query(None, description="Filter by instrument/symbol"),
    db: Session = Depends(get_db),
):
    """Return news records for a given date, newest first."""
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        target_date = datetime.now(timezone.utc).date()

    day_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
    day_end = day_start + timedelta(days=1)

    base_filters = [
        NewsRecord.captured_at >= day_start,
        NewsRecord.captured_at < day_end,
    ]
    if instrument:
        base_filters.append(NewsRecord.instrument == instrument.upper())

    total = db.query(func.count(NewsRecord.id)).filter(*base_filters).scalar()
    records = (
        db.query(NewsRecord)
        .filter(*base_filters)
        .order_by(NewsRecord.captured_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    def record_to_dict(r):
        captured_str = r.captured_at.isoformat() if r.captured_at else None
        published_str = r.published.isoformat() if isinstance(r.published, datetime) else r.published
        return {
            "id": r.id,
            "instrument": r.instrument,
            "title": r.title,
            "source": r.source,
            "published": published_str,
            "captured_at": captured_str,
            "sentiment": r.sentiment,
            "score": r.score,
            "url": r.url,
        }

    return {
        "date": str(target_date),
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [record_to_dict(r) for r in records],
    }


@router.post("/news/refresh")
def refresh_news_feed_endpoint(
    symbols: Optional[str] = Query(None, description="Comma-separated symbols; defaults to the sample market symbols."),
    per_symbol_limit: int = Query(5, ge=1, le=10),
):
    normalized_symbols = [value.strip().upper() for value in str(symbols or "").split(",") if value.strip()]
    return refresh_news_feed(normalized_symbols or None, per_symbol_limit=per_symbol_limit)


@router.post("/news/analyze")
def analyze_news_endpoint(payload: AINewsAnalyzeRequest):
    result = analyze_news(payload)
    if not result.get("success", False):
        raise HTTPException(status_code=502, detail=result.get("error", "LLM analysis failed")) from None
    return result
