from __future__ import annotations

from datetime import datetime

from backend.app.models import PaperTrade, TradeJournalEntry
from backend.app.services.storage import dumps_json, loads_json, session_scope


def _serialize_journal_entry(row: TradeJournalEntry) -> dict:
    return {
        "id": row.id,
        "paper_trade_id": row.paper_trade_id,
        "symbol": row.symbol,
        "strategy_mode": row.strategy_mode,
        "entry_reason": row.entry_reason,
        "exit_reason": row.exit_reason,
        "thesis": row.thesis,
        "risk_plan": row.risk_plan,
        "post_trade_review": row.post_trade_review,
        "tags": loads_json(row.tags_json, default=[]),
        "result_classification": row.result_classification,
        "analysis_snapshot": loads_json(row.analysis_snapshot_json),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def upsert_trade_journal_entry(
    symbol: str,
    strategy_mode: str | None = None,
    paper_trade_id: int | None = None,
    entry_reason: str | None = None,
    exit_reason: str | None = None,
    thesis: str | None = None,
    risk_plan: str | None = None,
    post_trade_review: str | None = None,
    tags: list[str] | None = None,
    result_classification: str | None = None,
    analysis_snapshot: dict | None = None,
) -> dict:
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return {"error": "Symbol is required."}

    with session_scope() as session:
        row = None
        if paper_trade_id is not None:
            row = session.query(TradeJournalEntry).filter(TradeJournalEntry.paper_trade_id == paper_trade_id).first()
            if row is None:
                trade = session.query(PaperTrade).filter(PaperTrade.id == paper_trade_id).first()
                if trade is not None and not strategy_mode:
                    strategy_mode = trade.strategy_mode
        if row is None:
            row = TradeJournalEntry(symbol=normalized_symbol, paper_trade_id=paper_trade_id)
            session.add(row)

        row.symbol = normalized_symbol
        row.strategy_mode = strategy_mode
        row.entry_reason = entry_reason
        row.exit_reason = exit_reason
        row.thesis = thesis
        row.risk_plan = risk_plan
        row.post_trade_review = post_trade_review
        row.tags_json = dumps_json(tags or [])
        row.result_classification = result_classification
        row.analysis_snapshot_json = dumps_json(analysis_snapshot or {})
        row.updated_at = datetime.utcnow()
        session.flush()
        return _serialize_journal_entry(row)


def list_trade_journal_entries(symbol: str | None = None, classification: str | None = None, limit: int = 100) -> dict:
    limit = max(1, min(int(limit or 100), 300))
    with session_scope() as session:
        query = session.query(TradeJournalEntry)
        if symbol:
            query = query.filter(TradeJournalEntry.symbol == str(symbol).strip().upper())
        if classification:
            query = query.filter(TradeJournalEntry.result_classification == classification)
        rows = query.order_by(TradeJournalEntry.updated_at.desc()).limit(limit).all()
        items = [_serialize_journal_entry(row) for row in rows]

    classification_counts = {}
    for item in items:
        key = item.get("result_classification") or "unclassified"
        classification_counts[key] = classification_counts.get(key, 0) + 1
    return {
        "items": items,
        "count": len(items),
        "classification_counts": classification_counts,
    }
