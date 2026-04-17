from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeIngestItem(BaseModel):
    document_id: str | None = None
    source_type: str = Field(default="manual_note")
    symbol: str | None = None
    title: str
    summary: str | None = None
    content: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)
    published_at: str | None = None


class KnowledgeIngestRequest(BaseModel):
    items: list[KnowledgeIngestItem] = Field(default_factory=list)


class AIResearchRequest(BaseModel):
    symbol: str
    question: str = Field(default="Provide a concise symbol research brief.")
    include_news: bool = True
    knowledge_limit: int = Field(default=8, ge=2, le=16)
    use_vector: bool = False
    context_document_ids: list[str] = Field(default_factory=list)
    persist: bool = True


class AIMarketBriefRequest(BaseModel):
    question: str = Field(default="Summarize the current market opportunities.")
    symbols: list[str] = Field(default_factory=list)
    limit: int = Field(default=6, ge=2, le=12)
    use_vector: bool = False
    persist: bool = True
