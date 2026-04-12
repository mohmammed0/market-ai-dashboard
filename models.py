from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean
from datetime import datetime
from db import Base


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    instrument = Column(String(20), index=True, nullable=False)
    run_at = Column(DateTime, default=datetime.utcnow, index=True)

    start_date = Column(String(20))
    end_date = Column(String(20))
    analysis_date = Column(String(20))

    signal = Column(String(20))
    technical_signal = Column(String(20))

    close = Column(Float)
    technical_score = Column(Integer)
    news_score = Column(Integer)
    ai_news_score = Column(Integer)
    combined_score = Column(Integer)

    support = Column(Float)
    resistance = Column(Float)
    atr_stop = Column(Float)
    atr_target = Column(Float)
    risk_reward = Column(Float)

    news_sentiment = Column(String(20))
    ai_news_sentiment = Column(String(20))
    ai_enabled = Column(Boolean, default=False)

    reasons = Column(Text)
    ai_summary = Column(Text)
    ai_error = Column(Text)


class LiveQuote(Base):
    __tablename__ = "live_quotes"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True, nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)

    price = Column(Float)
    prev_close = Column(Float)
    change = Column(Float)
    change_pct = Column(Float)
    day_high = Column(Float)
    day_low = Column(Float)
    volume = Column(Float)
    source = Column(String(50))


class NewsRecord(Base):
    __tablename__ = "news_records"

    id = Column(Integer, primary_key=True, index=True)
    instrument = Column(String(20), index=True, nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)

    title = Column(Text)
    source = Column(String(100))
    published = Column(String(100))
    sentiment = Column(String(20))
    score = Column(Integer)
    url = Column(Text)
