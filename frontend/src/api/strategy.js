import { getJson, postJson } from "./client";

export async function fetchStrategyLabHistory(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) {
    query.set("limit", String(params.limit));
  }
  return getJson(`/api/strategy-lab/history${query.size ? `?${query.toString()}` : ""}`);
}

export async function fetchGeneratedStrategyCandidates(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) {
    query.set("limit", String(params.limit));
  }
  return getJson(`/api/strategy-lab/generated-candidates${query.size ? `?${query.toString()}` : ""}`);
}

export async function runStrategyEvaluation(payload) {
  return postJson("/api/strategy-lab/evaluate", payload);
}
