import { getJson, postJson } from "./client";

function toQuery(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    const normalized = String(value).trim();
    if (!normalized) return;
    query.set(key, normalized);
  });
  return query.toString();
}

export async function searchKnowledge(params = {}) {
  const query = toQuery({
    q: params.q || "",
    symbol: params.symbol || "",
    source_type: params.sourceType || "",
    tags: Array.isArray(params.tags) ? params.tags.join(",") : params.tags || "",
    date_from: params.dateFrom || "",
    date_to: params.dateTo || "",
    limit: params.limit ?? 20,
    offset: params.offset ?? 0,
    use_vector: params.useVector ? "true" : "",
  });
  return getJson(`/api/knowledge/search${query ? `?${query}` : ""}`, { cacheTtlMs: 10_000 });
}

export async function listRecentKnowledge(params = {}) {
  const query = toQuery({
    limit: params.limit ?? 20,
    symbol: params.symbol || "",
    source_type: params.sourceType || "",
  });
  return getJson(`/api/knowledge/recent${query ? `?${query}` : ""}`, { cacheTtlMs: 30_000 });
}

export async function getKnowledgeDocument(documentId) {
  return getJson(`/api/knowledge/documents/${encodeURIComponent(documentId)}`, { cacheTtlMs: 30_000 });
}

export async function ingestKnowledge(items) {
  const normalized = Array.isArray(items) ? items : [items];
  return postJson("/api/knowledge/ingest", { items: normalized });
}

export async function runAiResearch(payload) {
  return postJson("/api/ai/research", payload);
}

export async function runAiMarketBrief(payload) {
  return postJson("/api/ai/market-brief", payload);
}
