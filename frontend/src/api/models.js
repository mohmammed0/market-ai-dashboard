import { getJson, postJson } from "./client";

export async function fetchIntelligenceStatus() {
  return getJson("/api/intelligence/status");
}

export async function trainMlModel(payload) {
  return postJson("/api/intelligence/train/ml", payload);
}

export async function trainDlModel(payload) {
  return postJson("/api/intelligence/train/dl", payload);
}

export async function fetchModelRuns() {
  return getJson("/api/intelligence/models");
}

export async function fetchModelDetails(runId) {
  return getJson(`/api/intelligence/models/${runId}`);
}

export async function runSmartInference(payload) {
  return postJson("/api/intelligence/infer", payload);
}

export async function runBatchInference(payload) {
  return postJson("/api/intelligence/infer/batch", payload);
}

export async function runModelBacktest(payload) {
  return postJson("/api/intelligence/backtest", payload);
}

export async function fetchPromotionStatus() {
  return getJson("/api/models/promotion/status");
}

export async function promoteModelRun(runId) {
  return postJson(`/api/models/promotion/promote/${encodeURIComponent(runId)}`, {});
}

export async function fetchSignalExplanation(payload) {
  return postJson("/api/intelligence/explain", payload);
}

export async function fetchDecisionSurface(payload) {
  return postJson("/api/intelligence/decision", payload);
}

export async function fetchModelLifecycleStatus() {
  return getJson("/api/model-lifecycle/status");
}
