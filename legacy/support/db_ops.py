from legacy.support.db import SessionLocal
from legacy.support.models import AnalysisRun, LiveQuote, NewsRecord


def _to_float(value):
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _to_int(value):
    try:
        if value in (None, "", "None"):
            return None
        return int(value)
    except Exception:
        return None


def _to_text(value):
    if value is None:
        return None
    return str(value)


def save_analysis_result(result: dict):
    session = SessionLocal()
    try:
        row = AnalysisRun(
            instrument=_to_text(result.get("instrument")),
            start_date=_to_text(result.get("start_date")),
            end_date=_to_text(result.get("end_date")),
            analysis_date=_to_text(result.get("date")),
            signal=_to_text(result.get("signal")),
            technical_signal=_to_text(result.get("technical_signal")),
            close=_to_float(result.get("close")),
            technical_score=_to_int(result.get("technical_score")),
            news_score=_to_int(result.get("news_score")),
            ai_news_score=_to_int(result.get("ai_news_score")),
            combined_score=_to_int(result.get("combined_score")),
            support=_to_float(result.get("support")),
            resistance=_to_float(result.get("resistance")),
            atr_stop=_to_float(result.get("atr_stop")),
            atr_target=_to_float(result.get("atr_target")),
            risk_reward=_to_float(result.get("risk_reward")),
            news_sentiment=_to_text(result.get("news_sentiment")),
            ai_news_sentiment=_to_text(result.get("ai_news_sentiment")),
            ai_enabled=bool(result.get("ai_enabled", False)),
            reasons=_to_text(result.get("reasons")),
            ai_summary=_to_text(result.get("ai_summary")),
            ai_error=_to_text(result.get("ai_error")),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


def save_live_quote(quote: dict):
    session = SessionLocal()
    try:
        row = LiveQuote(
            symbol=_to_text(quote.get("symbol")),
            price=_to_float(quote.get("price")),
            prev_close=_to_float(quote.get("prev_close")),
            change=_to_float(quote.get("change")),
            change_pct=_to_float(quote.get("change_pct")),
            day_high=_to_float(quote.get("day_high")),
            day_low=_to_float(quote.get("day_low")),
            volume=_to_float(quote.get("volume")),
            source=_to_text(quote.get("source")),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        session.close()


def save_news_items(instrument: str, news_items: list):
    session = SessionLocal()
    try:
        count = 0
        for item in news_items or []:
            row = NewsRecord(
                instrument=_to_text(instrument),
                title=_to_text(item.get("title")),
                source=_to_text(item.get("source")),
                published=_to_text(item.get("published")),
                sentiment=_to_text(item.get("sentiment")),
                score=_to_int(item.get("score")),
                url=_to_text(item.get("url") or item.get("link")),
            )
            session.add(row)
            count += 1

        session.commit()
        return count
    finally:
        session.close()
