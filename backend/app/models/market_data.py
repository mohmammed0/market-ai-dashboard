from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class OhlcvBar(Base):
    __tablename__ = "ohlcv_bars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), index=True, default="1d")
    bar_time: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(50))


class MarketUniverseSymbol(Base):
    __tablename__ = "market_universe_symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    security_name: Mapped[str | None] = mapped_column(String(255))
    exchange: Mapped[str | None] = mapped_column(String(40), index=True)
    market_type: Mapped[str | None] = mapped_column(String(60), index=True)
    is_etf: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_test_issue: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    round_lot: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class QuoteSnapshot(Base):
    __tablename__ = "quote_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    price: Mapped[float | None] = mapped_column(Float)
    prev_close: Mapped[float | None] = mapped_column(Float)
    change: Mapped[float | None] = mapped_column(Float)
    change_pct: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(50))
    payload_json: Mapped[str | None] = mapped_column(Text)


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    feature_set: Mapped[str] = mapped_column(String(100), default="advanced_v1")
    payload_json: Mapped[str | None] = mapped_column(Text)
