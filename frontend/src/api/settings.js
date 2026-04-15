import { getJson, postJson, putJson } from "./client";

export async function fetchSmartAlerts() {
  return getJson("/api/smart/alerts");
}

export async function triggerSmartCycle() {
  return postJson("/api/smart/cycle", {});
}

export async function fetchRuntimeSettings() {
  return getJson("/api/settings/runtime");
}

export async function saveAlpacaSettings(payload) {
  return putJson("/api/settings/runtime/alpaca", payload);
}

export async function testAlpacaSettings() {
  return postJson("/api/settings/runtime/alpaca/test", {});
}

export async function fetchTelegramStatus() {
  return getJson("/api/notifications/telegram/status");
}

export async function saveTelegramSettings(payload) {
  return postJson("/api/notifications/telegram/configure", payload);
}

export async function testTelegramConnection() {
  return postJson("/api/notifications/telegram/test", {});
}

export async function fetchAutoTradingConfig() {
  return getJson("/api/settings/runtime/auto-trading");
}
