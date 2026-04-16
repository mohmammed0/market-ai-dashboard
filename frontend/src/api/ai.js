import { getJson, postJson } from "./client";

export async function fetchAiStatus() {
  return getJson("/api/ai/status");
}

export async function fetchAiOverlayStatus() {
  return getJson("/api/intelligence/overlay/status");
}

export async function analyzeAiNews(payload) {
  return postJson("/api/ai/news/analyze", payload);
}

export async function getNewsFeed(date, limit = 50, offset = 0, instrument = null, timeZone = null) {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (instrument) params.set("instrument", instrument);
  if (timeZone) params.set("time_zone", timeZone);
  return getJson("/api/ai/news/feed?" + params.toString());
}

export async function refreshNewsFeed(symbols = null, perSymbolLimit = 5) {
  const params = new URLSearchParams();
  if (Array.isArray(symbols) && symbols.length) {
    params.set("symbols", symbols.join(","));
  } else if (typeof symbols === "string" && symbols.trim()) {
    params.set("symbols", symbols.trim());
  }
  params.set("per_symbol_limit", String(perSymbolLimit));
  return postJson("/api/ai/news/refresh?" + params.toString());
}
