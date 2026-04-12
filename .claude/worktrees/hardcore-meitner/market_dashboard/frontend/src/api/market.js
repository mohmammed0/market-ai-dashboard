import { getJson, postJson } from "./client";

export async function fetchLiveSnapshots(payload) {
  return postJson("/api/market-data/live-snapshot", payload);
}

export async function fetchMarketOverview() {
  return getJson("/api/market/overview", { cacheTtlMs: 15_000 });
}

export async function searchMarketUniverse(params = {}) {
  const query = new URLSearchParams();
  if (params.q) query.set("q", params.q);
  if (params.exchange) query.set("exchange", params.exchange);
  if (params.type) query.set("type", params.type);
  if (params.category) query.set("category", params.category);
  if (params.limit) query.set("limit", String(params.limit));
  return getJson(`/api/market/universe/search${query.size ? `?${query.toString()}` : ""}`, {
    cacheTtlMs: params.q ? 10_000 : 20_000,
    forceFresh: Boolean(params.forceFresh),
    signal: params.signal,
  });
}

export async function fetchMarketUniverseFacets() {
  return getJson("/api/market/universe/facets", { cacheTtlMs: 60_000 });
}

export async function fetchUniversePresetSymbols(params = {}) {
  const query = new URLSearchParams();
  if (params.preset) query.set("preset", params.preset);
  if (params.limit) query.set("limit", String(params.limit));
  return getJson(`/api/market/universe/preset?${query.toString()}`);
}

export async function refreshMarketUniverse(force = true) {
  return postJson(`/api/market/universe/refresh?force=${force ? "true" : "false"}`, {});
}

export async function fetchMarketSymbolSnapshot(symbol) {
  return getJson(`/api/market/symbol/${encodeURIComponent(symbol)}/snapshot`, { cacheTtlMs: 10_000 });
}

export async function fetchBreadthOverview(params = {}) {
  const query = new URLSearchParams();
  if (params.preset) query.set("preset", params.preset);
  if (params.limit) query.set("limit", String(params.limit));
  return getJson(`/api/breadth/overview${query.size ? `?${query.toString()}` : ""}`);
}

export async function fetchDynamicWatchlists(payload) {
  return postJson("/api/watchlists/dynamic", payload);
}

export async function fetchEventsCalendar(payload) {
  return postJson("/api/events/calendar", payload);
}
