import { getApiBaseUrl, getJson, postJson } from "./client";

export { getApiBaseUrl };

export async function fetchHealth() {
  return getJson("/health");
}

export async function fetchReadiness() {
  return getJson("/ready");
}

export async function fetchDashboardSummary() {
  return getJson("/api/dashboard/summary");
}

export async function fetchDashboardKpis() {
  return getJson("/api/dashboard/kpis");
}

export async function fetchSchedulerStatus() {
  return getJson("/api/scheduler/status");
}

export async function fetchAutomationStatus(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", String(params.limit));
  return getJson(`/api/automation/status${query.size ? `?${query.toString()}` : ""}`);
}

export async function runAutomationJob(payload) {
  return postJson("/api/automation/run", payload);
}

export async function fetchOperationsOverview() {
  return getJson("/api/operations/overview");
}

export async function fetchOperationsLogs(limit = 100) {
  return getJson(`/api/operations/logs?limit=${encodeURIComponent(limit)}`);
}
