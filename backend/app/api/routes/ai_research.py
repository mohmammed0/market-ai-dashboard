from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.api.rate_limit import enforce_rate_limit
from backend.app.config import AI_RESEARCH_RATE_LIMIT_PER_MIN
from backend.app.schemas import AIMarketBriefRequest, AIResearchRequest
from backend.app.services.ai_research import build_market_brief, build_symbol_research


router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/research")
def ai_symbol_research(payload: AIResearchRequest, request: Request):
    enforce_rate_limit(
        request,
        bucket="ai_research",
        per_minute=AI_RESEARCH_RATE_LIMIT_PER_MIN,
    )
    return build_symbol_research(
        symbol=payload.symbol,
        question=payload.question,
        knowledge_limit=payload.knowledge_limit,
        include_news=payload.include_news,
        use_vector=payload.use_vector,
        context_document_ids=payload.context_document_ids,
        persist=payload.persist,
    )


@router.post("/contextual-analyze")
def ai_contextual_analyze(payload: AIResearchRequest, request: Request):
    enforce_rate_limit(
        request,
        bucket="ai_research",
        per_minute=AI_RESEARCH_RATE_LIMIT_PER_MIN,
    )
    return build_symbol_research(
        symbol=payload.symbol,
        question=payload.question,
        knowledge_limit=payload.knowledge_limit,
        include_news=payload.include_news,
        use_vector=payload.use_vector,
        context_document_ids=payload.context_document_ids,
        persist=payload.persist,
    )


@router.post("/market-brief")
def ai_market_brief(payload: AIMarketBriefRequest, request: Request):
    enforce_rate_limit(
        request,
        bucket="ai_research",
        per_minute=AI_RESEARCH_RATE_LIMIT_PER_MIN,
    )
    return build_market_brief(
        question=payload.question,
        symbols=payload.symbols,
        limit=payload.limit,
        use_vector=payload.use_vector,
        persist=payload.persist,
    )
