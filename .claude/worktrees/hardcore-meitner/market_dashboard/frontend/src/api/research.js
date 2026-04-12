import { postJson } from "./client";

export async function analyzeSymbol(payload) {
  return postJson("/api/analyze", payload);
}

export async function scanSymbols(payload) {
  return postJson("/api/scan", payload);
}

export async function fetchRanking(payload) {
  return postJson("/api/ranking/scan", payload);
}

export async function runBacktest(payload) {
  return postJson("/api/backtest", payload);
}

export async function runVectorbtBacktest(payload) {
  return postJson("/api/backtest/vectorbt", payload);
}
