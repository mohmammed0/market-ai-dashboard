from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.api.rate_limit import enforce_rate_limit
from backend.app.config import (
    KNOWLEDGE_DEFAULT_LIMIT,
    KNOWLEDGE_READ_RATE_LIMIT_PER_MIN,
    KNOWLEDGE_WRITE_RATE_LIMIT_PER_MIN,
)
from backend.app.schemas import KnowledgeIngestRequest
from backend.app.services.knowledge_retrieval import (
    get_knowledge_document,
    get_recent_knowledge_documents,
    ingest_knowledge_documents,
    search_knowledge_documents,
)


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _parse_csv_tags(raw: str | None) -> list[str]:
    return [tag.strip().lower() for tag in str(raw or "").split(",") if tag.strip()]


@router.post("/ingest")
def ingest_knowledge(payload: KnowledgeIngestRequest, request: Request):
    enforce_rate_limit(
        request,
        bucket="knowledge_write",
        per_minute=KNOWLEDGE_WRITE_RATE_LIMIT_PER_MIN,
    )
    rows = [item.model_dump() for item in payload.items]
    return ingest_knowledge_documents(rows, default_source_type="manual_note")


@router.get("/documents/{document_id}")
def get_knowledge_document_by_id(document_id: str, request: Request):
    enforce_rate_limit(
        request,
        bucket="knowledge_read",
        per_minute=KNOWLEDGE_READ_RATE_LIMIT_PER_MIN,
    )
    item = get_knowledge_document(document_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found.")
    return item


@router.get("/recent")
def list_recent_knowledge(
    request: Request,
    limit: int = Query(default=KNOWLEDGE_DEFAULT_LIMIT, ge=1, le=100),
    symbol: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
):
    enforce_rate_limit(
        request,
        bucket="knowledge_read",
        per_minute=KNOWLEDGE_READ_RATE_LIMIT_PER_MIN,
    )
    return get_recent_knowledge_documents(limit=limit, symbol=symbol, source_type=source_type)


@router.get("/search")
def search_knowledge(
    request: Request,
    q: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    tags: str | None = Query(default=None, description="Comma-separated tags."),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=KNOWLEDGE_DEFAULT_LIMIT, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    use_vector: bool = Query(default=False),
):
    enforce_rate_limit(
        request,
        bucket="knowledge_read",
        per_minute=KNOWLEDGE_READ_RATE_LIMIT_PER_MIN,
    )
    return search_knowledge_documents(
        query_text=q,
        symbol=symbol,
        source_type=source_type,
        tags=_parse_csv_tags(tags),
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        use_vector=use_vector,
    )
