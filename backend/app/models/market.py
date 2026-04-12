from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    instrument: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    start_date: Mapped[str | None] = mapped_column(String(20))
    end_date: Mapped[str | None] = mapped_column(String(20))
    analysis_date: Mapped[str | None] = mapped_column(String(20))
    signal: Mapped[str | None] = mapped_column(String(20))
    technical_signal: Mapped[str | None] = mapped_column(String(20))
    close: Mapped[float | None] = mapped_column(Float)
    technical_score: Mapped[int | None] = mapped_column(Integer)
    news_score: Mapped[int | None] = mapped_column(Integer)
    ai_news_score: Mapped[int | None] = mapped_column(Integer)
    combined_score: Mapped[int | None] = mapped_column(Integer)
    support: Mapped[float | None] = mapped_column(Float)
    resistance: Mapped[float | None] = mapped_column(Float)
    atr_stop: Mapped[float | None] = mapped_column(Float)
    atr_target: Mapped[float | None] = mapped_column(Float)
    risk_reward: Mapped[float | None] = mapped_column(Float)
    news_sentiment: Mapped[str | None] = mapped_column(String(20))
    ai_news_sentiment: Mapped[str | None] = mapped_column(String(20))
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reasons: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_error: Mapped[str | None] = mapped_column(Text)


class LiveQuote(Base):
    __tablename__ = "live_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    price: Mapped[float | None] = mapped_column(Float)
    prev_close: Mapped[float | None] = mapped_column(Float)
    change: Mapped[float | None] = mapped_column(Float)
    change_pct: Mapped[float | None] = mapped_column(Float)
    day_high: Mapped[float | None] = mapped_column(Float)
    day_low: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(50))


class NewsRecord(Base):
    __tablename__ = "news_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    instrument: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    title: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))
    published: Mapped[str | None] = mapped_column(String(100))
    sentiment: Mapped[str | None] = mapped_column(String(20))
    score: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(Text)
