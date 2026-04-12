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

export async function getNewsFeed(date, limit = 50, offset = 0, instrument = null) {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (instrument) params.set("instrument", instrument);
  return getJson("/api/ai/news/feed?" + params.toString());
}
