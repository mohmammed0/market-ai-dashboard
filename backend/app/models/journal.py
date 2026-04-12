from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class TradeJournalEntry(Base):
    __tablename__ = "trade_journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_trade_id: Mapped[int | None] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    strategy_mode: Mapped[str | None] = mapped_column(String(20), index=True)
    entry_reason: Mapped[str | None] = mapped_column(Text)
    exit_reason: Mapped[str | None] = mapped_column(Text)
    thesis: Mapped[str | None] = mapped_column(Text)
    risk_plan: Mapped[str | None] = mapped_column(Text)
    post_trade_review: Mapped[str | None] = mapped_column(Text)
    tags_json: Mapped[str | None] = mapped_column(Text)
    result_classification: Mapped[str | None] = mapped_column(String(50), index=True)
    analysis_snapshot_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
