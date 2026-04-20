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

export async function fetchDashboardLite() {
  return getJson("/api/dashboard/lite");
}

export async function fetchDashboardWidget(widget) {
  return getJson(`/api/dashboard/widgets/${encodeURIComponent(widget)}`);
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

export async function fetchAutoTradingDiagnosticsLatest(params = {}) {
  const query = new URLSearchParams();
  if (params.includeDetails) query.set('include_details', '1');
  if (params.includeModelBreakdown) query.set('include_model_breakdown', '1');
  if (params.includeRaw) query.set('include_raw', '1');
  if (params.rowSymbol) query.set('row_symbol', String(params.rowSymbol));
  if (params.latestNonempty) query.set('latest_nonempty', '1');
  return getJson(`/api/diagnostics/auto-trading/latest${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchAutoTradingDiagnosticsCycles(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.set('limit', String(params.limit));
  if (params.includeRows) query.set('include_rows', 'true');
  if (params.includeDetails) query.set('include_details', '1');
  if (params.includeModelBreakdown) query.set('include_model_breakdown', '1');
  if (params.includeRaw) query.set('include_raw', '1');
  if (params.rowSymbol) query.set('row_symbol', String(params.rowSymbol));
  return getJson(`/api/diagnostics/auto-trading/cycles${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchAutoTradingDiagnosticsCycle(cycleId, params = {}) {
  const query = new URLSearchParams();
  if (params.includeDetails) query.set('include_details', '1');
  if (params.includeModelBreakdown) query.set('include_model_breakdown', '1');
  if (params.includeRaw) query.set('include_raw', '1');
  if (params.rowSymbol) query.set('row_symbol', String(params.rowSymbol));
  return getJson(`/api/diagnostics/auto-trading/cycles/${encodeURIComponent(cycleId)}${query.size ? `?${query.toString()}` : ''}`);
}

export function getAutoTradingDiagnosticsExportUrl(cycleId) {
  return `${getApiBaseUrl()}/api/diagnostics/auto-trading/cycles/${encodeURIComponent(cycleId)}/export.csv`;
}

export async function fetchPortfolioBrainStatus(params = {}) {
  const query = new URLSearchParams();
  if (params.latestNonempty !== undefined) query.set('latest_nonempty', params.latestNonempty ? '1' : '0');
  return getJson(`/api/portfolio-brain/status${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchPortfolioBrainLatest(params = {}) {
  const query = new URLSearchParams();
  if (params.includeRows !== undefined) query.set('include_rows', params.includeRows ? '1' : '0');
  if (params.includeDetails) query.set('include_details', '1');
  if (params.latestNonempty !== undefined) query.set('latest_nonempty', params.latestNonempty ? '1' : '0');
  return getJson(`/api/portfolio-brain/latest${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchPortfolioBrainCycles(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.set('limit', String(params.limit));
  if (params.includeRows !== undefined) query.set('include_rows', params.includeRows ? '1' : '0');
  return getJson(`/api/portfolio-brain/cycles${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchPortfolioBrainCycle(cycleId, params = {}) {
  const query = new URLSearchParams();
  if (params.includeRows !== undefined) query.set('include_rows', params.includeRows ? '1' : '0');
  if (params.includeDetails !== undefined) query.set('include_details', params.includeDetails ? '1' : '0');
  return getJson(`/api/portfolio-brain/cycles/${encodeURIComponent(cycleId)}${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchPortfolioBrainAllocationLedger(cycleId, params = {}) {
  const query = new URLSearchParams();
  if (params.includeRows !== undefined) query.set('include_rows', params.includeRows ? '1' : '0');
  return getJson(`/api/portfolio-brain/cycles/${encodeURIComponent(cycleId)}/allocation-ledger${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchMarketSessionStatus(params = {}) {
  const query = new URLSearchParams();
  if (params.refresh) query.set('refresh', 'true');
  return getJson(`/api/market-session/status${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchMarketReadinessLatest() {
  return getJson('/api/market-readiness/latest');
}

export async function fetchMarketReadinessCycles(params = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.set('limit', String(params.limit));
  return getJson(`/api/market-readiness/cycles${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchMarketReadinessCycle(cycleId) {
  return getJson(`/api/market-readiness/cycles/${encodeURIComponent(cycleId)}`);
}

export async function fetchKronosStatus() {
  return getJson('/api/kronos/status');
}

export async function fetchAnalysisEnginesStatus(params = {}) {
  const query = new URLSearchParams();
  if (params.latestNonempty !== undefined) query.set('latest_nonempty', params.latestNonempty ? '1' : '0');
  return getJson(`/api/analysis-engines/status${query.size ? `?${query.toString()}` : ''}`);
}

export async function fetchKronosLatest(params = {}) {
  const query = new URLSearchParams();
  if (params.limitSymbols) query.set('limit_symbols', String(params.limitSymbols));
  return getJson(`/api/kronos/latest${query.size ? `?${query.toString()}` : ''}`);
}
