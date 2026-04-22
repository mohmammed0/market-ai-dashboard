import { getJson, postJson } from "./client";

export async function fetchRiskDashboard() {
  return getJson("/api/risk/dashboard");
}

export async function createRiskPlan(payload) {
  return postJson("/api/risk/plan", payload);
}

export async function fetchPortfolioExposure() {
  return getJson("/api/portfolio/exposure");
}

export async function fetchPortfolioSnapshot() {
  return getJson("/api/portfolio/snapshot");
}

export async function fetchAlertsCenter(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", String(params.limit));
  if (params.severity) query.set("severity", params.severity);
  return getJson(`/api/alerts/history${query.size ? `?${query.toString()}` : ""}`);
}

export async function runAlertsCycle(params = {}) {
  const query = new URLSearchParams();
  if (params.preset) query.set("preset", params.preset);
  if (params.limit) query.set("limit", String(params.limit));
  if (typeof params.dryRun === "boolean") query.set("dry_run", String(params.dryRun));
  return postJson(`/api/alerts/run${query.size ? `?${query.toString()}` : ""}`, {});
}

export async function fetchJournalEntries(params = {}) {
  const query = new URLSearchParams();
  if (params.symbol) query.set("symbol", params.symbol);
  if (params.classification) query.set("classification", params.classification);
  if (params.limit) query.set("limit", String(params.limit));
  return getJson(`/api/journal/entries${query.size ? `?${query.toString()}` : ""}`);
}

export async function saveJournalEntry(payload) {
  return postJson("/api/journal/entries", payload);
}

export async function fetchTradingPortfolio() {
  return getJson("/api/trading/portfolio");
}

export async function fetchTradingControlPanel(refreshBroker = false) {
  return getJson(`/api/trading/control-panel${refreshBroker ? "?refresh_broker=true" : ""}`);
}

export async function fetchTradingTrades() {
  return getJson("/api/trading/trades");
}

export async function fetchAlertHistory() {
  return getJson("/api/trading/alerts");
}

export async function fetchSignalHistory() {
  return getJson("/api/trading/signals");
}

export async function refreshTradingSignals(payload) {
  return postJson("/api/trading/refresh", payload);
}

export async function fetchExecutionAudit(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", String(params.limit));
  if (params.symbol) query.set("symbol", params.symbol);
  return getJson(`/api/execution/audit${query.size ? `?${query.toString()}` : ""}`);
}

export async function fetchExecutionReconcile(params = {}) {
  const query = new URLSearchParams();
  if (params.broker) query.set("broker", params.broker);
  if (params.strategy_mode) query.set("strategy_mode", params.strategy_mode);
  return getJson(`/api/execution/reconcile${query.size ? `?${query.toString()}` : ""}`);
}

export async function runExecutionReconcile(payload = {}) {
  return postJson("/api/execution/reconcile", payload);
}

export async function fetchTradingOrders(status = "OPEN") {
  const query = new URLSearchParams();
  if (status) query.set("status", status);
  return getJson(`/api/trading/orders${query.size ? `?${query.toString()}` : ""}`);
}

export async function createTradingOrder(payload) {
  return postJson("/api/trading/orders", payload);
}

export async function cancelTradingOrder(orderId) {
  return postJson(`/api/trading/orders/${encodeURIComponent(orderId)}/cancel`, {});
}

export async function fetchExecutionPreview(payload) {
  return postJson("/api/execution/preview", payload);
}

export async function confirmExecution(previewId) {
  return postJson(`/api/execution/confirm/${encodeURIComponent(previewId)}`, {});
}

export async function fetchOrchestrationStatus() {
  return getJson("/api/operations/orchestration");
}

export async function runOrchestrationReconcile() {
  return postJson("/api/operations/orchestration/reconcile", {});
}

export async function fetchStrategyLabTracking() {
  return getJson("/api/strategy-lab/tracking");
}


export const fetchPaperPortfolio = fetchTradingPortfolio;
export const fetchPaperControlPanel = fetchTradingControlPanel;
export const fetchPaperTrades = fetchTradingTrades;
export const refreshPaperSignals = refreshTradingSignals;
export const fetchPaperOrders = fetchTradingOrders;
export const createPaperOrder = createTradingOrder;
export const cancelPaperOrder = cancelTradingOrder;
