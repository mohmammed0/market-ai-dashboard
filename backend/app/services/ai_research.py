from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.config import AI_RESEARCH_LLM_TIMEOUT_SECONDS, DEFAULT_SAMPLE_SYMBOLS
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.events.publisher import publish_event
from backend.app.models.market import NewsRecord
from backend.app.observability.metrics import emit_counter
from backend.app.services.dashboard_hub import get_dashboard_lite
from backend.app.services.knowledge_retrieval import (
    get_knowledge_document,
    ingest_knowledge_documents,
    search_knowledge_documents,
)
from backend.app.services.llm_gateway import LLMUnavailableError, llm_chat
from backend.app.services.market_data import fetch_quote_snapshots
from backend.app.services.news_feed import serialize_news_record
from backend.app.services.signal_store import get_cached_signal_view, normalize_signal_symbol, warm_signal_cache_for_symbol
from backend.app.services.storage import session_scope
from packages.contracts.events.topics import AI_ANALYSIS_COMPLETED, AI_ANALYSIS_REQUESTED

logger = get_logger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _extract_json(text: str) -> dict[str, Any]:
    payload = str(text or "").strip()
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", payload, re.DOTALL | re.IGNORECASE)
    if block:
        try:
            parsed = json.loads(block.group(1).strip())
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
    brace = re.search(r"\{.*\}", payload, re.DOTALL)
    if brace:
        try:
            parsed = json.loads(brace.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
    return {}


def _fetch_recent_news(symbol: str, limit: int = 5) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = (
            session.query(NewsRecord)
            .filter(NewsRecord.instrument == symbol)
            .order_by(NewsRecord.captured_at.desc(), NewsRecord.id.desc())
            .limit(max(1, min(int(limit), 20)))
            .all()
        )
        return [serialize_news_record(row) for row in rows]


def _normalize_sentiment(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"BULLISH", "POSITIVE", "BUY", "UP"}:
        return "bullish"
    if text in {"BEARISH", "NEGATIVE", "SELL", "DOWN"}:
        return "bearish"
    return "neutral"


def _signal_sentiment_alignment(action: str, dominant_sentiment: str) -> str:
    normalized_action = str(action or "").strip().lower()
    if dominant_sentiment == "neutral":
        return "mixed"
    if normalized_action in {"buy", "add"}:
        return "supportive" if dominant_sentiment == "bullish" else "contrarian"
    if normalized_action in {"trim", "exit", "sell"}:
        return "supportive" if dominant_sentiment == "bearish" else "contrarian"
    return "mixed"


def _build_sentiment_summary(news_evidence: list[dict[str, Any]], *, action: str) -> dict[str, Any]:
    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    sentiment_priority = {"bearish": 0, "neutral": 1, "bullish": 2}
    event_counts: dict[str, int] = {}
    impact_values: list[float] = []
    for row in news_evidence:
        sentiment = _normalize_sentiment(row.get("sentiment"))
        counts[sentiment] += 1
        event_type = str(row.get("event_type") or "general").strip().lower() or "general"
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        impact_values.append(_safe_float(row.get("impact_score")))

    total = sum(counts.values())
    dominant_sentiment = max(counts.items(), key=lambda item: (item[1], sentiment_priority.get(item[0], 0)))[0] if total else "neutral"
    net_score = round((((counts["bullish"] - counts["bearish"]) / total) * 100.0), 2) if total else 0.0
    avg_impact_score = round(sum(impact_values) / len(impact_values), 2) if impact_values else 0.0
    top_event_types = [
        item[0]
        for item in sorted(event_counts.items(), key=lambda item: (-item[1], item[0]))
    ][:3]
    alignment = _signal_sentiment_alignment(action, dominant_sentiment)
    if total:
        note = (
            f"News tone is {dominant_sentiment} with {counts['bullish']} bullish, "
            f"{counts['bearish']} bearish, and {counts['neutral']} neutral items."
        )
    else:
        note = "No recent news evidence was available for a sentiment overlay."
    return {
        "dominant_sentiment": dominant_sentiment,
        "signal_alignment": alignment,
        "bullish_count": counts["bullish"],
        "bearish_count": counts["bearish"],
        "neutral_count": counts["neutral"],
        "news_item_count": total,
        "net_sentiment_score": net_score,
        "average_impact_score": avg_impact_score,
        "top_event_types": top_event_types,
        "note": note,
    }


def _map_risk_level(signal: str, confidence: float) -> str:
    normalized = str(signal or "HOLD").upper()
    if normalized in {"BUY", "ADD"} and confidence >= 75:
        return "moderate"
    if normalized in {"EXIT", "TRIM", "SELL"} and confidence >= 70:
        return "high"
    if confidence >= 80:
        return "moderate"
    if confidence >= 55:
        return "controlled"
    return "elevated"


def _normalize_action(signal: str, confidence: float) -> str:
    normalized = str(signal or "HOLD").upper()
    if normalized in {"BUY", "BULLISH"}:
        return "buy" if confidence >= 72 else "add"
    if normalized in {"SELL", "BEARISH"}:
        return "exit" if confidence >= 70 else "trim"
    if normalized in {"TRIM", "EXIT", "ADD"}:
        return normalized.lower()
    return "watch"


def _build_deterministic_reason(
    *,
    symbol: str,
    signal: str,
    confidence: float,
    price: float | None,
    knowledge_hits: int,
    news_hits: int,
) -> str:
    price_text = f"${price:,.2f}" if isinstance(price, (int, float)) and price > 0 else "N/A"
    return (
        f"{symbol}: signal={signal} confidence={confidence:.0f}% price={price_text}. "
        f"knowledge_hits={knowledge_hits}, news_hits={news_hits}. "
        "Decision is grounded in cached signal + recent context."
    )


def _build_llm_summary(
    *,
    symbol: str,
    question: str,
    action: str,
    confidence: float,
    risk_level: str,
    quote: dict[str, Any] | None,
    signal_payload: dict[str, Any] | None,
    knowledge_evidence: list[dict[str, Any]],
    news_evidence: list[dict[str, Any]],
    timeout_seconds: float,
) -> dict[str, Any]:
    prompt_payload = {
        "symbol": symbol,
        "question": question,
        "action": action,
        "confidence": round(confidence, 2),
        "risk_level": risk_level,
        "quote": quote or {},
        "signal": signal_payload or {},
        "knowledge_evidence": knowledge_evidence[:6],
        "news_evidence": news_evidence[:4],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are a market research assistant. Use only the provided facts. "
                "Return concise, practical JSON. Do not invent missing data."
            ),
        },
        {
            "role": "user",
            "content": (
                "Summarize the symbol in strict JSON with keys: "
                "summary (string), key_points (array of 3-6 strings), "
                "risk_notes (array of 2-4 strings), confidence_comment (string).\n"
                f"Facts:\n{json.dumps(prompt_payload, ensure_ascii=False)}"
            ),
        },
    ]
    result = llm_chat(
        messages,
        temperature=0.1,
        max_tokens=280,
        timeout=timeout_seconds,
    )
    parsed = _extract_json(result.get("content", ""))
    if not parsed:
        raise LLMUnavailableError("LLM response was not valid JSON.")
    return {
        "summary": str(parsed.get("summary") or "").strip(),
        "key_points": [str(item).strip() for item in parsed.get("key_points", []) if str(item).strip()],
        "risk_notes": [str(item).strip() for item in parsed.get("risk_notes", []) if str(item).strip()],
        "confidence_comment": str(parsed.get("confidence_comment") or "").strip(),
        "provider": result.get("provider"),
        "model": result.get("model"),
    }


def _maybe_notify_telegram(payload: dict[str, Any]) -> None:
    if os.getenv("MARKET_AI_RESEARCH_NOTIFY_TELEGRAM", "0").strip().lower() not in {"1", "true", "yes"}:
        return
    try:
        from core.telegram_notifier import is_telegram_configured, send_telegram_message

        if not is_telegram_configured():
            return
        signal = str(payload.get("signal") or "").upper()
        confidence = _safe_float(payload.get("confidence"))
        if signal not in {"BUY", "ADD", "EXIT"} or confidence < 72:
            return
        symbol = str(payload.get("symbol") or "").upper()
        action = str(payload.get("action") or "watch").upper()
        summary = str(payload.get("summary") or "")[:240]
        send_telegram_message(
            f"🧠 <b>AI Research</b>\n"
            f"📊 {symbol} — {action}\n"
            f"🎯 الثقة: {confidence:.0f}%\n"
            f"💡 {summary}"
        )
    except Exception:
        logger.debug("research notifier failed", exc_info=True)


def build_symbol_research(
    *,
    symbol: str,
    question: str,
    knowledge_limit: int = 8,
    include_news: bool = True,
    use_vector: bool = False,
    context_document_ids: list[str] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    normalized_symbol = normalize_signal_symbol(symbol) or str(symbol or "").strip().upper()
    research_id = f"research-{uuid4().hex[:10]}"
    correlation_id = research_id
    started_at = datetime.utcnow().isoformat()
    publish_event(
        event_type=AI_ANALYSIS_REQUESTED,
        producer="ai_research",
        payload={"research_id": research_id, "symbol": normalized_symbol, "question": question[:200]},
        correlation_id=correlation_id,
    )

    signal_payload = get_cached_signal_view(normalized_symbol, mode="ensemble")
    if signal_payload is None:
        warm_signal_cache_for_symbol(normalized_symbol)
        signal_payload = get_cached_signal_view(normalized_symbol, mode="ensemble")
    signal_payload = signal_payload or {}

    quote_snapshot = fetch_quote_snapshots([normalized_symbol])
    quote = (quote_snapshot.get("items") or [{}])[0] if isinstance(quote_snapshot, dict) else {}

    retrieval_query = question.strip() or f"{normalized_symbol} latest setup"
    knowledge_payload = search_knowledge_documents(
        query_text=retrieval_query,
        symbol=normalized_symbol,
        limit=max(2, min(int(knowledge_limit), 16)),
        use_vector=use_vector,
    )
    knowledge_evidence = list(knowledge_payload.get("items") or [])
    for document_id in context_document_ids or []:
        pinned = get_knowledge_document(document_id)
        if pinned is None:
            continue
        if any(item.get("document_id") == pinned.get("document_id") for item in knowledge_evidence):
            continue
        pinned = {**pinned, "hybrid_score": 999.0, "pinned": True}
        knowledge_evidence.insert(0, pinned)

    news_evidence = _fetch_recent_news(normalized_symbol, limit=6) if include_news else []
    top_news = news_evidence[:4]

    signal = str(signal_payload.get("signal") or "HOLD").upper()
    confidence = _safe_float(signal_payload.get("confidence"), default=0.0)
    if confidence <= 1.0:
        confidence *= 100.0
    confidence = max(0.0, min(confidence, 100.0))
    action = _normalize_action(signal, confidence)
    risk_level = _map_risk_level(signal, confidence)
    sentiment_summary = _build_sentiment_summary(news_evidence, action=action)
    deterministic_summary = _build_deterministic_reason(
        symbol=normalized_symbol,
        signal=signal,
        confidence=confidence,
        price=_safe_float(signal_payload.get("price") or quote.get("price") or 0.0),
        knowledge_hits=len(knowledge_evidence),
        news_hits=len(news_evidence),
    )

    llm_provider = "deterministic"
    llm_model = None
    llm_summary = None
    llm_key_points: list[str] = []
    llm_risk_notes: list[str] = []
    llm_confidence_note = ""
    try:
        llm_payload = _build_llm_summary(
            symbol=normalized_symbol,
            question=question,
            action=action,
            confidence=confidence,
            risk_level=risk_level,
            quote=quote,
            signal_payload=signal_payload,
            knowledge_evidence=knowledge_evidence,
            news_evidence=top_news,
            timeout_seconds=AI_RESEARCH_LLM_TIMEOUT_SECONDS,
        )
        llm_summary = llm_payload.get("summary") or None
        llm_key_points = llm_payload.get("key_points") or []
        llm_risk_notes = llm_payload.get("risk_notes") or []
        llm_confidence_note = llm_payload.get("confidence_comment") or ""
        llm_provider = str(llm_payload.get("provider") or "llm")
        llm_model = llm_payload.get("model")
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "ai_research.llm_fallback",
            symbol=normalized_symbol,
            error=str(exc)[:200],
        )

    key_points: list[str] = []
    if signal_payload.get("reasoning"):
        key_points.append(str(signal_payload.get("reasoning")))
    if top_news:
        for news in top_news[:2]:
            event_type = str(news.get("event_type") or "general")
            sentiment = str(news.get("sentiment") or "NEUTRAL")
            key_points.append(f"News {event_type}: {sentiment}")
    if sentiment_summary.get("news_item_count"):
        key_points.append(
            "Sentiment overlay: "
            f"{sentiment_summary['dominant_sentiment']} / "
            f"{sentiment_summary['signal_alignment']}"
        )
    if knowledge_evidence:
        for evidence in knowledge_evidence[:2]:
            title = str(evidence.get("title") or "").strip()
            if title:
                key_points.append(f"Knowledge context: {title[:120]}")
    if llm_key_points:
        key_points = llm_key_points

    risk_notes = llm_risk_notes or [
        "Use stop discipline and position sizing constraints.",
        "Treat this output as decision support, not direct order execution.",
    ]
    if llm_confidence_note:
        risk_notes.append(llm_confidence_note[:180])

    summary = llm_summary or deterministic_summary
    evidence = []
    for row in knowledge_evidence[:6]:
        evidence.append(
            {
                "type": "knowledge",
                "document_id": row.get("document_id"),
                "title": row.get("title"),
                "summary": row.get("summary"),
                "score": row.get("hybrid_score") or row.get("score"),
                "source_type": row.get("source_type"),
                "symbol": row.get("symbol"),
                "created_at": row.get("created_at"),
            }
        )
    for row in top_news:
        evidence.append(
            {
                "type": "news",
                "title": row.get("title"),
                "summary": row.get("title"),
                "score": row.get("impact_score"),
                "source_type": "news",
                "symbol": row.get("instrument"),
                "created_at": row.get("captured_at"),
            }
        )

    payload = {
        "research_id": research_id,
        "symbol": normalized_symbol,
        "question": question,
        "action": action,
        "signal": signal,
        "confidence": round(confidence, 2),
        "risk_level": risk_level,
        "summary": summary,
        "key_points": key_points[:6],
        "risk_notes": risk_notes[:5],
        "quote": quote,
        "signal_payload": signal_payload,
        "evidence": evidence,
        "retrieval": knowledge_payload.get("retrieval", {}),
        "retrieval_stats": {
            "knowledge_hits": len(knowledge_evidence),
            "news_hits": len(news_evidence),
        },
        "sentiment_summary": sentiment_summary,
        "llm": {
            "provider": llm_provider,
            "model": llm_model,
            "used": llm_provider != "deterministic",
        },
        "generated_at": datetime.utcnow().isoformat(),
        "started_at": started_at,
    }

    if persist:
        persisted = ingest_knowledge_documents(
            [
                {
                    "source_type": "ai_research_report",
                    "symbol": normalized_symbol,
                    "title": f"AI Research • {normalized_symbol} • {action.upper()}",
                    "summary": summary,
                    "content": json.dumps(
                        {
                            "question": question,
                            "signal": signal,
                            "action": action,
                            "confidence": payload["confidence"],
                            "key_points": payload["key_points"],
                            "risk_notes": payload["risk_notes"],
                            "sentiment_summary": payload["sentiment_summary"],
                        },
                        ensure_ascii=False,
                    ),
                    "tags": [normalized_symbol.lower(), action.lower(), "ai_research"],
                    "metadata": {
                        "confidence": payload["confidence"],
                        "risk_level": risk_level,
                        "llm_provider": llm_provider,
                        "dominant_sentiment": sentiment_summary.get("dominant_sentiment"),
                        "sentiment_score": sentiment_summary.get("net_sentiment_score"),
                        "importance_boost": 0.8 if payload["confidence"] >= 75 else 0.4,
                    },
                    "provenance": {
                        "research_id": research_id,
                        "retrieval": payload["retrieval"],
                        "evidence_count": len(evidence),
                        "sentiment_summary": sentiment_summary,
                    },
                    "published_at": datetime.utcnow().isoformat(),
                }
            ],
            default_source_type="ai_research_report",
        )
        payload["persisted_document_id"] = (persisted.get("items") or [{}])[0].get("document_id")

    _maybe_notify_telegram(payload)
    publish_event(
        event_type=AI_ANALYSIS_COMPLETED,
        producer="ai_research",
        payload={
            "research_id": research_id,
            "symbol": normalized_symbol,
            "action": action,
            "confidence": payload["confidence"],
            "evidence_count": len(evidence),
            "llm_used": payload["llm"]["used"],
        },
        correlation_id=correlation_id,
    )
    emit_counter("ai_research_requests_total", value=1, llm_used=str(payload["llm"]["used"]).lower())
    return payload


def build_market_brief(
    *,
    question: str,
    symbols: list[str] | None = None,
    limit: int = 6,
    use_vector: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    selected_symbols = [normalize_signal_symbol(item) or str(item or "").strip().upper() for item in (symbols or DEFAULT_SAMPLE_SYMBOLS)]
    selected_symbols = [item for item in selected_symbols if item][: max(1, min(int(limit), 12))]
    dashboard = get_dashboard_lite()
    opportunity_rows = list((dashboard.get("opportunities") or {}).get("items") or [])[:8]
    research_rows = []
    for symbol in selected_symbols[:4]:
        research_rows.append(
            build_symbol_research(
                symbol=symbol,
                question=question or f"{symbol} market brief",
                knowledge_limit=5,
                include_news=True,
                use_vector=use_vector,
                persist=False,
            )
        )

    summary = (
        f"Market brief generated for {len(research_rows)} symbols. "
        f"Top opportunity count in dashboard snapshot: {len(opportunity_rows)}."
    )
    payload = {
        "brief_id": f"brief-{uuid4().hex[:10]}",
        "question": question,
        "symbols": selected_symbols,
        "summary": summary,
        "opportunities": opportunity_rows,
        "research_items": research_rows,
        "generated_at": datetime.utcnow().isoformat(),
    }
    if persist:
        ingest_knowledge_documents(
            [
                {
                    "source_type": "market_brief",
                    "title": "AI Market Brief",
                    "summary": summary,
                    "content": json.dumps(
                        {"question": question, "symbols": selected_symbols, "opportunity_count": len(opportunity_rows)},
                        ensure_ascii=False,
                    ),
                    "tags": ["market_brief", "dashboard"],
                    "metadata": {"importance_boost": 0.6},
                    "provenance": {"brief_id": payload["brief_id"]},
                }
            ],
            default_source_type="market_brief",
        )
    return payload
