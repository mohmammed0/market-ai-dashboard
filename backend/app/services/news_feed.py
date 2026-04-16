from __future__ import annotations

from collections.abc import Iterable
import logging

from sqlalchemy import and_, or_

from backend.app.config import DEFAULT_SAMPLE_SYMBOLS
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.models.market import NewsRecord
from backend.app.services.storage import session_scope
from news_intelligence import classify_news_item, headline_signature
from news_engine import fetch_news


logger = get_logger(__name__)


def _as_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_symbols(symbols: Iterable[str] | None) -> list[str]:
    if not symbols:
        return [str(symbol).strip().upper() for symbol in DEFAULT_SAMPLE_SYMBOLS[:5] if str(symbol).strip()]

    normalized: list[str] = []
    for symbol in symbols:
        value = str(symbol or "").strip().upper()
        if not value or value in normalized:
            continue
        normalized.append(value)
    return normalized or [str(symbol).strip().upper() for symbol in DEFAULT_SAMPLE_SYMBOLS[:5] if str(symbol).strip()]


def _item_signature(symbol: str, item: dict) -> tuple:
    instrument = str(symbol or "").strip().upper()
    url = _as_text(item.get("url") or item.get("link"))
    if url:
        return ("url", instrument, url.lower())
    title = headline_signature(_as_text(item.get("title")) or "")
    source = (_as_text(item.get("source")) or "").lower()
    published = (_as_text(item.get("published")) or "").lower()
    return ("meta", instrument, title, source, published)


def _existing_signatures_for_symbol(session, symbol: str, items: list[dict]) -> set[tuple]:
    urls = sorted({_as_text(item.get("url") or item.get("link")) for item in items if _as_text(item.get("url") or item.get("link"))})
    titles = sorted({_as_text(item.get("title")) for item in items if _as_text(item.get("title"))})
    published_values = sorted({_as_text(item.get("published")) for item in items if _as_text(item.get("published"))})

    clauses = []
    if urls:
        clauses.append(NewsRecord.url.in_(urls))
    if titles and published_values:
        clauses.append(and_(NewsRecord.title.in_(titles), NewsRecord.published.in_(published_values)))
    elif titles:
        clauses.append(NewsRecord.title.in_(titles))

    if not clauses:
        return set()

    rows = (
        session.query(NewsRecord)
        .filter(NewsRecord.instrument == symbol)
        .filter(or_(*clauses))
        .all()
    )

    signatures: set[tuple] = set()
    for row in rows:
        signatures.add(
            _item_signature(
                symbol,
                {
                    "title": row.title,
                    "source": row.source,
                    "published": row.published,
                    "url": row.url,
                },
            )
        )
    return signatures


def refresh_news_feed(symbols: Iterable[str] | None = None, *, per_symbol_limit: int = 5) -> dict:
    normalized_symbols = _normalize_symbols(symbols)
    inserted = 0
    skipped = 0
    fetched = 0
    errors: list[dict] = []
    per_symbol: list[dict] = []

    with session_scope() as session:
        batch_signatures: set[tuple] = set()
        for symbol in normalized_symbols:
            try:
                payload = fetch_news(symbol, limit=per_symbol_limit)
            except Exception as exc:
                errors.append({"symbol": symbol, "error": " ".join(str(exc).split()) or exc.__class__.__name__})
                continue

            items = list(payload.get("news_items") or [])
            fetched += len(items)
            existing_signatures = _existing_signatures_for_symbol(session, symbol, items)
            symbol_inserted = 0
            symbol_skipped = 0

            for item in items:
                signature = _item_signature(symbol, item)
                if signature in existing_signatures or signature in batch_signatures:
                    skipped += 1
                    symbol_skipped += 1
                    continue

                row = NewsRecord(
                    instrument=symbol,
                    title=_as_text(item.get("title")),
                    source=_as_text(item.get("source")),
                    published=_as_text(item.get("published")),
                    sentiment=_as_text(item.get("sentiment")),
                    score=item.get("score", item.get("news_score")),
                    url=_as_text(item.get("url") or item.get("link")),
                )
                session.add(row)
                inserted += 1
                symbol_inserted += 1
                batch_signatures.add(signature)

            per_symbol.append(
                {
                    "symbol": symbol,
                    "fetched": len(items),
                    "inserted": symbol_inserted,
                    "skipped": symbol_skipped,
                    "overall_sentiment": payload.get("news_sentiment"),
                    "top_events": [
                        {
                            "title": row.get("title"),
                            "event_type": row.get("event_type"),
                            "impact_score": row.get("impact_score"),
                            "sentiment": row.get("sentiment"),
                        }
                        for row in items[:3]
                    ],
                }
            )

    log_event(
        logger,
        logging.INFO,
        "news.refresh",
        symbols=normalized_symbols,
        per_symbol_limit=per_symbol_limit,
        fetched=fetched,
        inserted=inserted,
        skipped=skipped,
        errors=len(errors),
    )
    return {
        "symbols": normalized_symbols,
        "per_symbol_limit": per_symbol_limit,
        "fetched": fetched,
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "items_by_symbol": per_symbol,
    }


def serialize_news_record(row: NewsRecord) -> dict:
    metadata = classify_news_item(row.instrument, row.title, row.source)
    captured_str = row.captured_at.isoformat() if row.captured_at else None
    return {
        "id": row.id,
        "instrument": row.instrument,
        "title": row.title,
        "source": row.source,
        "published": row.published,
        "captured_at": captured_str,
        "sentiment": row.sentiment,
        "score": row.score,
        "url": row.url,
        **metadata,
    }
