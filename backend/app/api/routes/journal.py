from fastapi import APIRouter, Query

from backend.app.schemas.requests import JournalEntryRequest
from backend.app.services.trade_journal import list_trade_journal_entries, upsert_trade_journal_entry


router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("/entries")
def journal_entries(
    symbol: str | None = None,
    classification: str | None = None,
    limit: int = Query(default=100, ge=1, le=300),
):
    return list_trade_journal_entries(symbol=symbol, classification=classification, limit=limit)


@router.post("/entries")
def create_or_update_journal_entry(payload: JournalEntryRequest):
    return upsert_trade_journal_entry(
        symbol=payload.symbol,
        strategy_mode=payload.strategy_mode,
        paper_trade_id=payload.paper_trade_id,
        entry_reason=payload.entry_reason,
        exit_reason=payload.exit_reason,
        thesis=payload.thesis,
        risk_plan=payload.risk_plan,
        post_trade_review=payload.post_trade_review,
        tags=payload.tags,
        result_classification=payload.result_classification,
        analysis_snapshot=payload.analysis_snapshot,
    )
