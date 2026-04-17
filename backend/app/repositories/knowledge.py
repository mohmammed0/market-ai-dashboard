from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from backend.app.models.knowledge import KnowledgeDocument
from backend.app.services.storage import dumps_json, loads_json


def _normalize_symbol(value: str | None) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _normalize_tags(values: list[str] | None) -> list[str]:
    tags: list[str] = []
    for value in values or []:
        tag = str(value or "").strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _tokenize_query(query: str | None) -> list[str]:
    if not query:
        return []
    text = str(query).lower()
    tokens = [token for token in re.split(r"[^a-z0-9_]+", text) if token]
    return tokens[:12]


def _build_search_text(
    *,
    title: str,
    summary: str | None,
    content: str | None,
    symbol: str | None,
    source_type: str,
    tags: list[str],
) -> str:
    parts = [
        str(title or "").strip(),
        str(summary or "").strip(),
        str(content or "").strip(),
        str(symbol or "").strip(),
        str(source_type or "").strip(),
        " ".join(tags),
    ]
    return " ".join(part for part in parts if part).strip()[:12000]


def _serialize_document(row: KnowledgeDocument, *, score: float | None = None) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "document_id": row.document_id,
        "source_type": row.source_type,
        "symbol": row.symbol,
        "title": row.title,
        "summary": row.summary,
        "content": row.content,
        "tags": loads_json(row.tags_json, default=[]),
        "metadata": loads_json(row.metadata_json, default={}),
        "provenance": loads_json(row.provenance_json, default={}),
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if score is not None:
        payload["score"] = round(float(score), 4)
    return payload


class KnowledgeDocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_document(
        self,
        *,
        document_id: str,
        source_type: str,
        title: str,
        summary: str | None,
        content: str | None,
        symbol: str | None,
        tags: list[str] | None,
        metadata: dict[str, Any] | None,
        provenance: dict[str, Any] | None,
        published_at: datetime | None,
        is_archived: bool = False,
    ) -> dict[str, Any]:
        normalized_tags = _normalize_tags(tags)
        normalized_symbol = _normalize_symbol(symbol)
        normalized_source_type = str(source_type or "system").strip().lower() or "system"
        now = datetime.utcnow()

        row = (
            self.session.query(KnowledgeDocument)
            .filter(KnowledgeDocument.document_id == str(document_id).strip())
            .first()
        )
        if row is None:
            row = KnowledgeDocument(
                document_id=str(document_id).strip(),
                source_type=normalized_source_type,
                title=str(title or "").strip()[:300] or "Untitled document",
                summary=str(summary or "").strip() or None,
                content=str(content or "").strip() or None,
                symbol=normalized_symbol,
                tags_json=dumps_json(normalized_tags),
                metadata_json=dumps_json(metadata or {}),
                provenance_json=dumps_json(provenance or {}),
                published_at=published_at,
                is_archived=bool(is_archived),
                created_at=now,
                updated_at=now,
            )
            row.search_text = _build_search_text(
                title=row.title,
                summary=row.summary,
                content=row.content,
                symbol=row.symbol,
                source_type=row.source_type,
                tags=normalized_tags,
            )
            self.session.add(row)
            self.session.flush()
            return _serialize_document(row)

        row.source_type = normalized_source_type
        row.title = str(title or "").strip()[:300] or row.title
        row.summary = str(summary or "").strip() or None
        row.content = str(content or "").strip() or None
        row.symbol = normalized_symbol
        row.tags_json = dumps_json(normalized_tags)
        row.metadata_json = dumps_json(metadata or {})
        row.provenance_json = dumps_json(provenance or {})
        row.published_at = published_at
        row.is_archived = bool(is_archived)
        row.updated_at = now
        row.search_text = _build_search_text(
            title=row.title,
            summary=row.summary,
            content=row.content,
            symbol=row.symbol,
            source_type=row.source_type,
            tags=normalized_tags,
        )
        self.session.flush()
        return _serialize_document(row)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        row = (
            self.session.query(KnowledgeDocument)
            .filter(KnowledgeDocument.document_id == str(document_id or "").strip())
            .first()
        )
        return None if row is None else _serialize_document(row)

    def recent_documents(
        self,
        *,
        limit: int = 20,
        symbol: str | None = None,
        source_type: str | None = None,
    ) -> list[dict[str, Any]]:
        query = self.session.query(KnowledgeDocument).filter(KnowledgeDocument.is_archived.is_(False))
        if symbol:
            query = query.filter(KnowledgeDocument.symbol == _normalize_symbol(symbol))
        if source_type:
            query = query.filter(KnowledgeDocument.source_type == str(source_type).strip().lower())
        rows = (
            query.order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
            .limit(max(1, min(int(limit), 100)))
            .all()
        )
        return [_serialize_document(row) for row in rows]

    def search_documents(
        self,
        *,
        query_text: str | None = None,
        symbol: str | None = None,
        source_type: str | None = None,
        tags: list[str] | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = self.session.query(KnowledgeDocument).filter(KnowledgeDocument.is_archived.is_(False))
        if symbol:
            query = query.filter(KnowledgeDocument.symbol == _normalize_symbol(symbol))
        if source_type:
            query = query.filter(KnowledgeDocument.source_type == str(source_type).strip().lower())
        if date_from is not None:
            query = query.filter(KnowledgeDocument.created_at >= date_from)
        if date_to is not None:
            query = query.filter(KnowledgeDocument.created_at <= date_to)

        normalized_tags = _normalize_tags(tags)
        for tag in normalized_tags:
            query = query.filter(KnowledgeDocument.tags_json.ilike(f"%\"{tag}\"%"))

        tokens = _tokenize_query(query_text)
        normalized_query = str(query_text or "").strip().lower()
        if normalized_query:
            clauses = [
                KnowledgeDocument.title.ilike(f"%{normalized_query}%"),
                KnowledgeDocument.summary.ilike(f"%{normalized_query}%"),
                KnowledgeDocument.content.ilike(f"%{normalized_query}%"),
                KnowledgeDocument.search_text.ilike(f"%{normalized_query}%"),
            ]
            for token in tokens:
                clauses.append(KnowledgeDocument.search_text.ilike(f"%{token}%"))
            query = query.filter(or_(*clauses))

        scan_limit = max(30, min(int(limit) * 8, 400))
        rows = (
            query.order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
            .offset(max(0, int(offset)))
            .limit(scan_limit)
            .all()
        )
        if not normalized_query:
            return [_serialize_document(row) for row in rows[: max(1, min(int(limit), 100))]]

        ranked: list[tuple[float, KnowledgeDocument]] = []
        for row in rows:
            title = str(row.title or "").lower()
            summary = str(row.summary or "").lower()
            content = str(row.content or "").lower()
            search_text = str(row.search_text or "").lower()
            score = 0.0
            if normalized_query in title:
                score += 6.0
            if normalized_query in summary:
                score += 4.0
            if normalized_query in content:
                score += 2.0
            for token in tokens:
                if token in title:
                    score += 1.8
                if token in summary:
                    score += 1.2
                if token in content:
                    score += 0.7
                if token in search_text:
                    score += 0.4
            metadata = loads_json(row.metadata_json, default={})
            if isinstance(metadata, dict):
                score += float(metadata.get("importance_boost") or 0.0)
            ranked.append((score, row))

        ranked.sort(
            key=lambda item: (
                item[0],
                item[1].created_at or datetime.min,
                item[1].id,
            ),
            reverse=True,
        )
        output_limit = max(1, min(int(limit), 100))
        return [_serialize_document(row, score=score) for score, row in ranked[:output_limit]]

    def archive_document(self, document_id: str) -> dict[str, Any] | None:
        row = (
            self.session.query(KnowledgeDocument)
            .filter(and_(KnowledgeDocument.document_id == str(document_id or "").strip()))
            .first()
        )
        if row is None:
            return None
        row.is_archived = True
        row.updated_at = datetime.utcnow()
        self.session.flush()
        return _serialize_document(row)
