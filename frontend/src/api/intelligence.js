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
  // Use quote snapshot to derive a simple signal from price change + momentum
  const data = await getJson(`/api/market/symbol/${encodeURIComponent(symbol)}/snapshot`, { cacheTtlMs: 30_000 });
  if (!data || data.detail) return null;
  const quote = data.quote || {};
  const changePct = quote.change_pct;
  // Simple signal: based on % change today
  let signal = "محايد", score = 50;
  if (changePct != null) {
    if (changePct >= 1.5) { signal = "شراء قوي"; score = 80; }
    else if (changePct >= 0.3) { signal = "شراء"; score = 65; }
    else if (changePct <= -1.5) { signal = "بيع قوي"; score = 20; }
    else if (changePct <= -0.3) { signal = "بيع"; score = 35; }
  }
  return { symbol, signal, score, change_pct: changePct, price: quote.price };
}
