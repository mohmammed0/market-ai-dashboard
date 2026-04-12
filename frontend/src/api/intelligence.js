import { getJson, postJson } from "./client";

export async function fetchMacroCalendar() {
  return getJson("/api/macro/calendar", { cacheTtlMs: 3_600_000 });
}

export async function fetchMacroSnapshot() {
  return getJson("/api/macro/snapshot", { cacheTtlMs: 3_600_000 });
}

export async function fetchRankingLeaders(limit = 50) {
  return getJson(`/api/ranking/leaders?limit=${limit}`, { cacheTtlMs: 60_000 });
}

export async function fetchFundamentals(ticker) {
  return getJson(`/api/fundamentals/${encodeURIComponent(ticker)}`, { cacheTtlMs: 86_400_000 });
}

export async function fetchMarketHistory(symbol, interval = "1d", startDate = "") {
  const query = new URLSearchParams({ symbol, interval });
  if (startDate) query.set("start_date", startDate);
  return getJson(`/api/market/history?${query.toString()}`, { cacheTtlMs: 60_000 });
}

export async function fetchQuoteSnapshot(symbol) {
  return getJson(`/api/market/symbol/${encodeURIComponent(symbol)}/snapshot`, { cacheTtlMs: 15_000 });
}

export async function fetchPortfolioBeta(symbols) {
  const query = new URLSearchParams({ symbols: symbols.join(",") });
  return getJson(`/api/portfolio/beta?${query.toString()}`, { cacheTtlMs: 300_000 });
}

export async function fetchPortfolioCorrelation(symbols, lookbackDays = 60) {
  const query = new URLSearchParams({ symbols: symbols.join(","), lookback_days: String(lookbackDays) });
  return getJson(`/api/portfolio/correlation?${query.toString()}`, { cacheTtlMs: 300_000 });
}

export async function calculateKelly(winRate, avgWinPct, avgLossPct, accountEquity = 100000) {
  return postJson(
    `/api/position-sizing/kelly?win_rate=${winRate}&avg_win_pct=${avgWinPct}&avg_loss_pct=${avgLossPct}&account_equity=${accountEquity}`,
    {}
  );
}

export async function calculateAtrSize(accountEquity, atrValue, price, riskPct = 1.0) {
  return postJson(
    `/api/position-sizing/atr?account_equity=${accountEquity}&atr_value=${atrValue}&price=${price}&risk_pct=${riskPct}`,
    {}
  );
}
