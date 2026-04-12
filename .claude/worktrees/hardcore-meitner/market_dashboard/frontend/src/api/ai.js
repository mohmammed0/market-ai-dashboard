import { getJson, postJson } from "./client";

export async function fetchAiStatus() {
  return getJson("/api/ai/status");
}

export async function analyzeAiNews(payload) {
  return postJson("/api/ai/news/analyze", payload);
}
