import { getJson, postJson } from "./client";


export async function fetchMarketTerminalBootstrap(params = {}, options = {}) {
  const query = new URLSearchParams();
  if (params.symbol) query.set("symbol", params.symbol);
  if (params.q) query.set("q", params.q);
  if (params.exchange) query.set("exchange", params.exchange);
  if (params.type) query.set("type", params.type);
  if (params.category) query.set("category", params.category);
  if (params.limit) query.set("limit", String(params.limit));
  return getJson(`/api/market/terminal/bootstrap${query.size ? `?${query.toString()}` : ""}`, {
    cacheTtlMs: 8_000,
    forceFresh: Boolean(options.forceFresh),
    signal: options.signal,
  });
}


export async function fetchMarketTerminalChart(payload, options = {}) {
  return postJson("/api/market/terminal/chart", payload, {
    signal: options.signal,
  });
}


export async function fetchMarketTerminalContext(payload, options = {}) {
  return postJson("/api/market/terminal/context", payload, {
    signal: options.signal,
  });
}
