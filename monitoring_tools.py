from pathlib import Path
from sqlalchemy import select, func, desc
from db import DATABASE_URL, SessionLocal
from models import AnalysisRun, LiveQuote, NewsRecord
from core.runtime_paths import sqlite_file_path

LOG_FILE = Path("logs") / "market_ai.log"


def health_snapshot():
    session = SessionLocal()
    try:
        analysis_runs = session.scalar(select(func.count()).select_from(AnalysisRun)) or 0
        live_quotes = session.scalar(select(func.count()).select_from(LiveQuote)) or 0
        news_records = session.scalar(select(func.count()).select_from(NewsRecord)) or 0

        last_run = session.execute(
            select(AnalysisRun).order_by(desc(AnalysisRun.id)).limit(1)
        ).scalars().first()

        return {
            "db_file_exists": bool(sqlite_file_path(DATABASE_URL) and sqlite_file_path(DATABASE_URL).exists()),
            "log_file_exists": LOG_FILE.exists(),
            "log_file_size": LOG_FILE.stat().st_size if LOG_FILE.exists() else 0,
            "analysis_runs": analysis_runs,
            "live_quotes": live_quotes,
            "news_records": news_records,
            "last_run_instrument": getattr(last_run, "instrument", None),
            "last_run_signal": getattr(last_run, "signal", None),
            "last_run_combined_score": getattr(last_run, "combined_score", None),
            "last_run_at": str(getattr(last_run, "run_at", None)),
        }
    finally:
        session.close()


def recent_runs(limit=10):
    session = SessionLocal()
    try:
        rows = session.execute(
            select(AnalysisRun).order_by(desc(AnalysisRun.id)).limit(limit)
        ).scalars().all()

        result = []
        for row in rows:
            result.append({
                "id": row.id,
                "instrument": row.instrument,
                "run_at": str(row.run_at),
                "signal": row.signal,
                "technical_signal": row.technical_signal,
                "technical_score": row.technical_score,
                "ai_news_score": row.ai_news_score,
                "combined_score": row.combined_score,
                "close": row.close,
                "analysis_date": row.analysis_date,
            })
        return result
    finally:
        session.close()
