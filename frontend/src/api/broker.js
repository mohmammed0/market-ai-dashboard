import { getJson, postJson } from "./client";

export async function fetchBrokerStatus() {
  return getJson("/api/broker/status");
}

export async function fetchBrokerSummary(refresh = false) {
  return getJson(`/api/broker/summary${refresh ? "?refresh=true" : ""}`);
}

export async function fetchBrokerAccount(refresh = false) {
  return getJson(`/api/broker/account${refresh ? "?refresh=true" : ""}`);
}

export async function fetchBrokerPositions(refresh = false) {
  return getJson(`/api/broker/positions${refresh ? "?refresh=true" : ""}`);
}

export async function fetchBrokerOrders(refresh = false) {
  return getJson(`/api/broker/orders${refresh ? "?refresh=true" : ""}`);
}

export async function liquidateBrokerPortfolio(payload = {}) {
  return postJson("/api/broker/liquidate", {
    cancel_open_orders: payload.cancel_open_orders ?? true,
  });
}
