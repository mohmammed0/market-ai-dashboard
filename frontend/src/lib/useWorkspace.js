import { startTransition, useEffect, useMemo, useState } from "react";

import {
  addWorkspaceSymbol,
  createWorkspaceWatchlist,
  fetchWorkspaceOverview,
  initializeWorkspace,
  removeWorkspaceSymbol,
  toggleWorkspaceFavorite,
  updateWorkspaceState,
} from "../api/workspace";


export function useWorkspace() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function loadOverview(options = {}) {
    if (!overview || options.forceFresh) {
      setLoading(true);
    }
    try {
      let payload = await fetchWorkspaceOverview({ forceFresh: options.forceFresh });
      if (!payload?.initialized && options.initializeIfMissing !== false) {
        await initializeWorkspace();
        payload = await fetchWorkspaceOverview({ forceFresh: true });
      }
      startTransition(() => {
        setOverview(payload);
        setError("");
      });
      return payload;
    } catch (requestError) {
      const nextError = requestError.message || "تعذر تحميل مساحة العمل.";
      setError(nextError);
      throw requestError;
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadOverview().catch(() => {});
  }, []);

  async function runMutation(action) {
    setPending(true);
    try {
      await action();
      return await loadOverview({ forceFresh: true });
    } finally {
      setPending(false);
    }
  }

  const workspace = overview?.workspace || null;
  const watchlists = overview?.watchlists || [];
  const activeWatchlist = overview?.active_watchlist || null;
  const favoritesWatchlistId = overview?.favorites_watchlist_id || null;

  const favoriteSymbols = useMemo(() => {
    const favorites = watchlists.find((item) => item.id === favoritesWatchlistId);
    return favorites?.symbols || [];
  }, [favoritesWatchlistId, watchlists]);

  return {
    overview,
    workspace,
    watchlists,
    activeWatchlist,
    favoritesWatchlistId,
    favoriteSymbols,
    loading,
    pending,
    error,
    refreshWorkspace: (forceFresh = true) => loadOverview({ forceFresh }),
    createWatchlist: (payload) => runMutation(() => createWorkspaceWatchlist(payload)),
    addSymbolToWatchlist: (watchlistId, symbol, notes = null) =>
      runMutation(() => addWorkspaceSymbol(watchlistId, { symbol, notes })),
    removeSymbolFromWatchlist: (watchlistId, symbol) =>
      runMutation(() => removeWorkspaceSymbol(watchlistId, symbol)),
    toggleFavoriteSymbol: (symbol) => runMutation(() => toggleWorkspaceFavorite(symbol)),
    updateWorkspaceState: (payload) => runMutation(() => updateWorkspaceState(payload)),
    isFavoriteSymbol: (symbol) => {
      const normalized = String(symbol || "").trim().toUpperCase();
      return favoriteSymbols.includes(normalized);
    },
  };
}
