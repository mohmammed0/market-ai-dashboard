import { getJson, postJson, putJson } from "./client";

export async function fetchRuntimeSettings() {
  return getJson("/api/settings/runtime");
}

export async function saveOpenAISettings(payload) {
  return putJson("/api/settings/runtime/openai", payload);
}

export async function testOpenAISettings() {
  return postJson("/api/settings/runtime/openai/test", {});
}

export async function saveAlpacaSettings(payload) {
  return putJson("/api/settings/runtime/alpaca", payload);
}

export async function testAlpacaSettings() {
  return postJson("/api/settings/runtime/alpaca/test", {});
}
