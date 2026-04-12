import { deleteJson, getJson, invalidateJsonCache, postJson, putJson } from "./client";


const WORKSPACE_CACHE_PREFIX = "/api/workspace";


function invalidateWorkspaceCache() {
  invalidateJsonCache(WORKSPACE_CACHE_PREFIX);
}


export async function fetchWorkspaceOverview(options = {}) {
  return getJson("/api/workspace/overview", {
    cacheTtlMs: 10_000,
    forceFresh: Boolean(options.forceFresh),
  });
}


export async function fetchWorkspaceWatchlists(options = {}) {
  return getJson("/api/workspace/watchlists", {
    cacheTtlMs: 10_000,
    forceFresh: Boolean(options.forceFresh),
  });
}


export async function createWorkspaceWatchlist(payload) {
  const response = await postJson("/api/workspace/watchlists", payload);
  invalidateWorkspaceCache();
  return response;
}


export async function updateWorkspaceWatchlist(watchlistId, payload) {
  const response = await putJson(`/api/workspace/watchlists/${encodeURIComponent(watchlistId)}`, payload);
  invalidateWorkspaceCache();
  return response;
}


export async function deleteWorkspaceWatchlist(watchlistId) {
  const response = await deleteJson(`/api/workspace/watchlists/${encodeURIComponent(watchlistId)}`);
  invalidateWorkspaceCache();
  return response;
}


export async function addWorkspaceSymbol(watchlistId, payload) {
  const response = await postJson(`/api/workspace/watchlists/${encodeURIComponent(watchlistId)}/items`, payload);
  invalidateWorkspaceCache();
  return response;
}


export async function removeWorkspaceSymbol(watchlistId, symbol) {
  const response = await deleteJson(`/api/workspace/watchlists/${encodeURIComponent(watchlistId)}/items/${encodeURIComponent(symbol)}`);
  invalidateWorkspaceCache();
  return response;
}


export async function toggleWorkspaceFavorite(symbol) {
  const response = await postJson("/api/workspace/favorites/toggle", { symbol });
  invalidateWorkspaceCache();
  return response;
}


export async function updateWorkspaceState(payload) {
  const response = await putJson("/api/workspace/state", payload);
  invalidateWorkspaceCache();
  return response;
}
