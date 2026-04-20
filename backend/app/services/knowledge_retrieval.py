from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from backend.app.config import (
    KNOWLEDGE_DEFAULT_LIMIT,
    KNOWLEDGE_MAX_LIMIT,
    KNOWLEDGE_VECTOR_ENABLED,
    KNOWLEDGE_VECTOR_MIN_SCORE,
)
from backend.app.core.logging_utils import get_logger, log_event
from backend.app.events.publisher import publish_event
from backend.app.observability.metrics import emit_counter
from backend.app.repositories.knowledge import KnowledgeDocumentRepository
from backend.app.services.storage import session_scope
from packages.contracts.events.topics import KNOWLEDGE_DOCUMENT_INGESTED, KNOWLEDGE_SEARCH_EXECUTED

logger = get_logger(__name__)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)
    except Exception:
        return None


def _normalize_limit(value: int | None, *, default: int = KNOWLEDGE_DEFAULT_LIMIT) -> int:
    candidate = default if value is None else int(value)
    return max(1, min(candidate, KNOWLEDGE_MAX_LIMIT))


class VectorSearchProvider(Protocol):
    provider_name: str
    ready: bool

    def search(
        self,
        *,
        query_text: str,
        symbol: str | None,
        source_type: str | None,
        tags: list[str] | None,
        date_from: str | None,
        date_to: str | None,
        limit: int,
        min_score: float,
    ) -> list[dict[str, Any]]: ...


@dataclass(slots=True)
class NullVectorSearchProvider:
    provider_name: str = "disabled"
    ready: bool = False

    def search(
        self,
        *,
        query_text: str,
        symbol: str | None,
        source_type: str | None,
        tags: list[str] | None,
        date_from: str | None,
        date_to: str | None,
        limit: int,
        min_score: float,
    ) -> list[dict[str, Any]]:
        return []


def _semantic_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9_]+", str(value or "").lower()) if len(token) >= 2][:256]


def _char_ngrams(value: str, n: int = 3) -> set[str]:
    text = re.sub(r"\s+", " ", str(value or "").lower()).strip()
    if len(text) < n:
        return {text} if text else set()
    return {text[index:index + n] for index in range(len(text) - n + 1)}


def _semantic_text(row: dict[str, Any]) -> str:
    tags = row.get("tags") if isinstance(row.get("tags"), list) else []
    return " ".join(
        part
        for part in [
            str(row.get("title") or "").strip(),
            str(row.get("summary") or "").strip(),
            str(row.get("content") or "").strip(),
            str(row.get("symbol") or "").strip(),
            str(row.get("source_type") or "").strip(),
            " ".join(str(tag).strip().lower() for tag in tags if str(tag).strip()),
        ]
        if part
    ).strip()


def _overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(math.sqrt(len(left) * len(right)), 1.0)


@dataclass(slots=True)
class LocalSemanticSearchProvider:
    provider_name: str = "local_semantic"
    ready: bool = True

    def search(
        self,
        *,
        query_text: str,
        symbol: str | None,
        source_type: str | None,
        tags: list[str] | None,
        date_from: str | None,
        date_to: str | None,
        limit: int,
        min_score: float,
    ) -> list[dict[str, Any]]:
        normalized_query = str(query_text or "").strip()
        if not normalized_query:
            return []

        candidate_limit = max(120, min(int(limit or 8) * 20, 400))
        with session_scope() as session:
            repo = KnowledgeDocumentRepository(session)
            candidates = repo.search_documents(
                query_text=None,
                symbol=symbol,
                source_type=source_type,
                tags=tags,
                date_from=_parse_iso_datetime(date_from),
                date_to=_parse_iso_datetime(date_to),
                limit=candidate_limit,
                offset=0,
            )

        query_tokens = set(_semantic_tokens(normalized_query))
        query_ngrams = _char_ngrams(normalized_query)
        ranked: list[dict[str, Any]] = []
        for item in candidates:
            semantic_text = _semantic_text(item)
            text_lower = semantic_text.lower()
            doc_tokens = set(_semantic_tokens(semantic_text))
            doc_ngrams = _char_ngrams(semantic_text)
            token_score = _overlap_ratio(query_tokens, doc_tokens)
            ngram_score = _overlap_ratio(query_ngrams, doc_ngrams)
            phrase_bonus = 0.2 if normalized_query.lower() in text_lower else 0.0
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            importance_boost = max(0.0, min(float(metadata.get("importance_boost") or 0.0), 1.0))
            score = min(1.0, round((token_score * 0.55) + (ngram_score * 0.25) + phrase_bonus + (importance_boost * 0.15), 4))
            if score < float(min_score or 0.0):
                continue
            ranked.append({**item, "vector_score": score, "score": score})

        ranked.sort(
            key=lambda row: (
                float(row.get("vector_score") or row.get("score") or 0.0),
                str(row.get("created_at") or ""),
            ),
            reverse=True,
        )
        return ranked[: max(1, int(limit or 8))]


_vector_provider: VectorSearchProvider = NullVectorSearchProvider()


def get_vector_provider() -> VectorSearchProvider:
    global _vector_provider
    if not KNOWLEDGE_VECTOR_ENABLED:
        if not isinstance(_vector_provider, NullVectorSearchProvider):
            _vector_provider = NullVectorSearchProvider()
        return _vector_provider
    if isinstance(_vector_provider, NullVectorSearchProvider):
        _vector_provider = LocalSemanticSearchProvider()
    return _vector_provider


def ingest_knowledge_documents(
    items: list[dict[str, Any]],
    *,
    default_source_type: str = "system",
) -> dict[str, Any]:
    prepared_items = [item for item in items if isinstance(item, dict)]
    if not prepared_items:
        return {"inserted": 0, "items": [], "errors": ["No valid items provided."]}

    ingested: list[dict[str, Any]] = []
    errors: list[str] = []
    with session_scope() as session:
        repo = KnowledgeDocumentRepository(session)
        for item in prepared_items:
            try:
                title = str(item.get("title") or "").strip()
                content = str(item.get("content") or "").strip()
                summary = str(item.get("summary") or "").strip()
                if not title and not content and not summary:
                    errors.append("Skipped an item without title/summary/content.")
                    continue
                source_type = str(item.get("source_type") or default_source_type).strip().lower() or default_source_type
                symbol = str(item.get("symbol") or "").strip().upper() or None
                tags = item.get("tags") if isinstance(item.get("tags"), list) else []
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
                document_id = str(item.get("document_id") or "").strip() or f"doc-{uuid4().hex[:12]}"
                payload = repo.upsert_document(
                    document_id=document_id,
                    source_type=source_type,
                    title=title or (summary[:120] if summary else "Untitled document"),
                    summary=summary or None,
                    content=content or None,
                    symbol=symbol,
                    tags=tags,
                    metadata=metadata,
                    provenance=provenance,
                    published_at=_parse_iso_datetime(item.get("published_at")),
                    is_archived=bool(item.get("is_archived", False)),
                )
                ingested.append(payload)
            except Exception as exc:
                errors.append(str(exc))

    for row in ingested:
        try:
            publish_event(
                event_type=KNOWLEDGE_DOCUMENT_INGESTED,
                producer="knowledge_retrieval",
                payload={
                    "action": "knowledge_document_ingested",
                    "document_id": row.get("document_id"),
                    "source_type": row.get("source_type"),
                    "symbol": row.get("symbol"),
                },
                correlation_id=str(row.get("document_id") or None),
            )
        except Exception:
            logger.debug("knowledge event publish failed for %s", row.get("document_id"), exc_info=True)

    emit_counter(
        "knowledge_documents_ingested_total",
        value=len(ingested),
        source_type=default_source_type,
    )
    if errors:
        emit_counter("knowledge_documents_ingest_errors_total", value=len(errors), source_type=default_source_type)

    return {
        "inserted": len(ingested),
        "items": ingested,
        "errors": errors,
    }


def get_knowledge_document(document_id: str) -> dict[str, Any] | None:
    with session_scope() as session:
        repo = KnowledgeDocumentRepository(session)
        return repo.get_document(document_id)


def get_recent_knowledge_documents(
    *,
    limit: int = KNOWLEDGE_DEFAULT_LIMIT,
    symbol: str | None = None,
    source_type: str | None = None,
) -> dict[str, Any]:
    resolved_limit = _normalize_limit(limit)
    with session_scope() as session:
        repo = KnowledgeDocumentRepository(session)
        items = repo.recent_documents(limit=resolved_limit, symbol=symbol, source_type=source_type)
    return {
        "items": items,
        "count": len(items),
        "limit": resolved_limit,
        "symbol": str(symbol or "").strip().upper() or None,
        "source_type": str(source_type or "").strip().lower() or None,
    }


def search_knowledge_documents(
    *,
    query_text: str | None = None,
    symbol: str | None = None,
    source_type: str | None = None,
    tags: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = KNOWLEDGE_DEFAULT_LIMIT,
    offset: int = 0,
    use_vector: bool = False,
) -> dict[str, Any]:
    resolved_limit = _normalize_limit(limit)
    normalized_query = str(query_text or "").strip()
    with session_scope() as session:
        repo = KnowledgeDocumentRepository(session)
        lexical_items = repo.search_documents(
            query_text=normalized_query or None,
            symbol=symbol,
            source_type=source_type,
            tags=tags,
            date_from=_parse_iso_datetime(date_from),
            date_to=_parse_iso_datetime(date_to),
            limit=resolved_limit,
            offset=max(0, int(offset)),
        )

    vector_items: list[dict[str, Any]] = []
    provider = get_vector_provider()
    vector_mode_active = bool(use_vector and provider.ready and normalized_query)
    if vector_mode_active:
        vector_items = provider.search(
            query_text=normalized_query,
            symbol=symbol,
            source_type=source_type,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
            limit=resolved_limit,
            min_score=KNOWLEDGE_VECTOR_MIN_SCORE,
        )

    merged_by_id: dict[str, dict[str, Any]] = {}
    for item in lexical_items:
        key = str(item.get("document_id"))
        merged = dict(item)
        merged["lexical_score"] = float(item.get("score") or 1.0)
        merged["vector_score"] = 0.0
        merged["hybrid_score"] = round(merged["lexical_score"], 4)
        merged_by_id[key] = merged

    for item in vector_items:
        key = str(item.get("document_id") or item.get("id") or "")
        if not key:
            continue
        vector_score = float(item.get("vector_score") or item.get("score") or 0.0)
        if key in merged_by_id:
            merged = merged_by_id[key]
            merged["vector_score"] = max(float(merged.get("vector_score") or 0.0), vector_score)
            merged["hybrid_score"] = round((float(merged.get("lexical_score") or 0.0) * 0.7) + (merged["vector_score"] * 0.3), 4)
            continue
        merged = dict(item)
        merged["lexical_score"] = 0.0
        merged["vector_score"] = vector_score
        merged["hybrid_score"] = round(vector_score, 4)
        merged_by_id[key] = merged

    merged_items = list(merged_by_id.values())
    merged_items.sort(
        key=lambda row: (
            float(row.get("hybrid_score") or 0.0),
            str(row.get("created_at") or ""),
        ),
        reverse=True,
    )
    final_items = merged_items[:resolved_limit]

    log_event(
        logger,
        logging.INFO,
        "knowledge.search",
        query=normalized_query[:120] if normalized_query else None,
        symbol=str(symbol or "").strip().upper() or None,
        source_type=str(source_type or "").strip().lower() or None,
        tags=tags or [],
        lexical_hits=len(lexical_items),
        vector_hits=len(vector_items),
        returned=len(final_items),
        vector_mode=vector_mode_active,
    )
    emit_counter("knowledge_search_total", value=1, vector_mode=str(vector_mode_active).lower())
    try:
        publish_event(
            event_type=KNOWLEDGE_SEARCH_EXECUTED,
            producer="knowledge_retrieval",
            payload={
                "query": normalized_query[:120] if normalized_query else None,
                "symbol": str(symbol or "").strip().upper() or None,
                "source_type": str(source_type or "").strip().lower() or None,
                "returned": len(final_items),
                "lexical_hits": len(lexical_items),
                "vector_hits": len(vector_items),
                "vector_mode": vector_mode_active,
            },
        )
    except Exception:
        logger.debug("knowledge search event publish failed", exc_info=True)

    return {
        "items": final_items,
        "count": len(final_items),
        "limit": resolved_limit,
        "offset": max(0, int(offset)),
        "query": normalized_query or None,
        "symbol": str(symbol or "").strip().upper() or None,
        "source_type": str(source_type or "").strip().lower() or None,
        "tags": tags or [],
        "retrieval": {
            "mode": "hybrid" if vector_mode_active else "lexical",
            "lexical_hits": len(lexical_items),
            "vector_hits": len(vector_items),
            "vector_ready": bool(provider.ready),
            "vector_provider": provider.provider_name,
        },
    }


def build_retrieval_context(
    *,
    query_text: str,
    symbol: str | None = None,
    limit: int = 8,
    use_vector: bool = False,
) -> dict[str, Any]:
    payload = search_knowledge_documents(
        query_text=query_text,
        symbol=symbol,
        limit=limit,
        offset=0,
        use_vector=use_vector,
    )
    evidence = []
    for item in payload.get("items", []):
        evidence.append(
            {
                "document_id": item.get("document_id"),
                "title": item.get("title"),
                "source_type": item.get("source_type"),
                "symbol": item.get("symbol"),
                "summary": item.get("summary"),
                "score": item.get("hybrid_score") or item.get("score"),
                "created_at": item.get("created_at"),
                "tags": item.get("tags", []),
            }
        )
    return {
        "query": payload.get("query"),
        "retrieval": payload.get("retrieval", {}),
        "evidence": evidence,
    }
