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
  // /api/market/symbol/{symbol}/snapshot returns {quote, history:{items:[...]}, ...}
  // This is the correct endpoint that actually has OHLCV data
  const data = await getJson(`/api/market/symbol/${encodeURIComponent(symbol)}/snapshot`, { cacheTtlMs: 60_000 });
  if (!data || data.detail) return { symbol, rows: 0, items: [], error: data?.detail || "No data" };
  const history = data.history || {};
  return {
    symbol,
    rows: history.rows || 0,
    items: history.items || [],
    source: history.source,
    quote: data.quote || null,
  };
}

export async function fetchQuoteSnapshot(symbol) {
  return getJson(`/api/market/symbol/${encodeURIComponent(symbol)}/snapshot`, { cacheTtlMs: 15_000 });
}

export async function fetchPortfolioBeta(symbols) {
  const query = new URLSearchParams({ symbols: symbols.join(",") });
  return getJson(`/api/portfolio-risk/beta?${query.toString()}`, { cacheTtlMs: 300_000 });
}

export async function fetchPortfolioCorrelation(symbols, lookbackDays = 60) {
  const query = new URLSearchParams({ symbols: symbols.join(","), lookback_days: String(lookbackDays) });
  return getJson(`/api/portfolio-risk/correlation?${query.toString()}`, { cacheTtlMs: 300_000 });
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

export async function fetchSymbolSignal(symbol) {
  return getJson(`/api/intelligence/signal/${encodeURIComponent(symbol)}`, { cacheTtlMs: 30_000 });
}
