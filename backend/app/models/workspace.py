from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="custom", index=True)
    color_token: Mapped[str | None] = mapped_column(String(24))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_items_watchlist_symbol"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class WorkspaceState(Base):
    __tablename__ = "workspace_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    workspace_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    active_symbol: Mapped[str | None] = mapped_column(String(20), index=True)
    active_watchlist_id: Mapped[int | None] = mapped_column(Integer, index=True)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False, default="1D", index=True)
    range_key: Mapped[str] = mapped_column(String(16), nullable=False, default="3M", index=True)
    layout_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="terminal")
    compare_symbols_json: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
