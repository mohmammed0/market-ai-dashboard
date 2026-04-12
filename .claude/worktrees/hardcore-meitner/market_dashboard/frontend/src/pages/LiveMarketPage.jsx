import { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import PageFrame from "../components/PageFrame";
import ActionButton from "../components/ui/ActionButton";
import StatusBadge from "../components/ui/StatusBadge";
import { fetchMarketTerminalBootstrap, fetchMarketTerminalChart, fetchMarketTerminalContext } from "../api/terminal";
import { useWorkspace } from "../lib/useWorkspace";
import LiveMarketChartSection from "./live-market/LiveMarketChartSection";
import LiveMarketContextSection from "./live-market/LiveMarketContextSection";
import LiveMarketExplorerTable from "./live-market/LiveMarketExplorerTable";
import LiveMarketFiltersSection from "./live-market/LiveMarketFiltersSection";
import LiveMarketMarketPulse from "./live-market/LiveMarketMarketPulse";
import LiveMarketSideColumn from "./live-market/LiveMarketSideColumn";
import { buildChartOption } from "./live-market/buildChartOption";
import { DEFAULT_SYMBOL, EMPTY_ITEMS, POLL_INTERVAL_MS } from "./live-market/constants";
import { normalizeSymbol, sessionTone } from "./live-market/formatters";
import useStableCallback from "./live-market/useStableCallback";


export default function LiveMarketPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    workspace,
    watchlists,
    activeWatchlist,
    favoriteSymbols,
    loading: workspaceLoading,
    pending: workspacePending,
    addSymbolToWatchlist,
    removeSymbolFromWatchlist,
    toggleFavoriteSymbol,
    updateWorkspaceState,
    createWatchlist,
  } = useWorkspace();
  const [selectedSymbol, setSelectedSymbol] = useState(DEFAULT_SYMBOL);
  const [timeframe, setTimeframe] = useState("1D");
  const [rangeKey, setRangeKey] = useState("3M");
  const [compareSymbols, setCompareSymbols] = useState([]);
  const [liveEnabled, setLiveEnabled] = useState(true);
  const [filters, setFilters] = useState({ q: "", exchange: "ALL", type: "all", category: "all", limit: 40 });
  const [overview, setOverview] = useState(null);
  const [facets, setFacets] = useState(null);
  const [explorer, setExplorer] = useState(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState(null);
  const [chartPayload, setChartPayload] = useState(null);
  const [contextPayload, setContextPayload] = useState(null);
  const [session, setSession] = useState(null);
  const [bootLoading, setBootLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(true);
  const [contextLoading, setContextLoading] = useState(true);
  const [error, setError] = useState("");
  const [filterDraft, setFilterDraft] = useState({ q: "", exchange: "ALL", type: "all", category: "all", limit: 40 });
  const requestRef = useRef(0);
  const bootKeyRef = useRef("");
  const abortRef = useRef(null);

  function setBootKey(symbol, nextTimeframe = timeframe, nextRangeKey = rangeKey, nextCompareSymbols = compareSymbols) {
    bootKeyRef.current = `${normalizeSymbol(symbol)}|${String(nextTimeframe || "1D").toUpperCase()}|${String(nextRangeKey || "3M").toUpperCase()}|${(nextCompareSymbols || []).map(normalizeSymbol).join(",")}`;
  }

  async function loadTerminal(nextSymbol, options = {}) {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const symbol = normalizeSymbol(nextSymbol || selectedSymbol || workspace?.active_symbol || DEFAULT_SYMBOL);
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    const activeTimeframe = String(options.nextTimeframe || timeframe || "1D").toUpperCase();
    const activeRangeKey = String(options.nextRangeKey || rangeKey || "3M").toUpperCase();
    const activeCompareSymbols = (options.nextCompareSymbols || compareSymbols || [])
      .map(normalizeSymbol)
      .filter((item) => item && item !== symbol)
      .slice(0, 3);
    const shouldRefreshBootstrap = options.refreshBootstrap !== false;
    const nextFilters = options.nextFilters || filters;
    if (shouldRefreshBootstrap) {
      setBootLoading(true);
    }
    setChartLoading(true);
    setContextLoading(true);
    setError("");
    try {
      const [bootstrapPayload, chartData, contextData] = await Promise.all([
        shouldRefreshBootstrap
          ? fetchMarketTerminalBootstrap(
              {
                symbol,
                q: nextFilters.q,
                exchange: nextFilters.exchange,
                type: nextFilters.type,
                category: nextFilters.category,
                limit: nextFilters.limit,
              },
              {
                forceFresh: Boolean(options.forceFresh),
                signal: controller.signal,
              }
            )
          : Promise.resolve(null),
        fetchMarketTerminalChart({
          symbol,
          timeframe: activeTimeframe,
          range_key: activeRangeKey,
          compare_symbols: activeCompareSymbols,
        }, { signal: controller.signal }),
        fetchMarketTerminalContext({ symbol }, { signal: controller.signal }),
      ]);
      if (requestRef.current !== requestId) {
        return;
      }
      startTransition(() => {
        setSelectedSymbol(symbol);
        setTimeframe(activeTimeframe);
        setRangeKey(activeRangeKey);
        setCompareSymbols(activeCompareSymbols);
        setChartPayload(chartData);
        setContextPayload(contextData);
        setSession(chartData?.session || bootstrapPayload?.session || null);
        if (bootstrapPayload) {
          setOverview(bootstrapPayload.overview || null);
          setFacets(bootstrapPayload.facets || null);
          setExplorer(bootstrapPayload.explorer || null);
          setSelectedSnapshot(bootstrapPayload.selected_snapshot || null);
        }
      });
    } catch (requestError) {
      if (requestError?.name === "AbortError") {
        return;
      }
      if (requestRef.current === requestId) {
        setError(requestError.message || "تعذر تحميل طرفية السوق.");
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
      if (requestRef.current === requestId) {
        setBootLoading(false);
        setChartLoading(false);
        setContextLoading(false);
      }
    }
  }

  useEffect(() => {
    if (workspaceLoading && !searchParams.get("symbol")) {
      return;
    }
    const querySymbol = normalizeSymbol(searchParams.get("symbol"));
    const bootSymbol = querySymbol || normalizeSymbol(workspace?.active_symbol) || DEFAULT_SYMBOL;
    const bootTimeframe = workspace?.timeframe || "1D";
    const bootRange = workspace?.range_key || "3M";
    const bootCompare = Array.isArray(workspace?.compare_symbols) ? workspace.compare_symbols.slice(0, 3) : [];
    const bootKey = `${bootSymbol}|${bootTimeframe}|${bootRange}|${bootCompare.join(",")}`;
    if (bootKeyRef.current === bootKey) {
      return;
    }
    bootKeyRef.current = bootKey;
    loadTerminal(bootSymbol, {
      forceFresh: true,
      nextTimeframe: bootTimeframe,
      nextRangeKey: bootRange,
      nextCompareSymbols: bootCompare,
      refreshBootstrap: true,
    });
  }, [
    searchParams,
    workspaceLoading,
    workspace?.active_symbol,
    workspace?.timeframe,
    workspace?.range_key,
    JSON.stringify(workspace?.compare_symbols || []),
  ]);

  useEffect(() => () => {
    abortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!liveEnabled || !selectedSymbol) {
      return undefined;
    }
    const intervalMs = POLL_INTERVAL_MS[timeframe] || 30000;
    const timer = window.setInterval(() => {
      loadTerminal(selectedSymbol, { refreshBootstrap: true, forceFresh: true }).catch(() => {});
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [liveEnabled, selectedSymbol, timeframe, rangeKey, compareSymbols.join("|"), filters]);

  async function handleSymbolSelect(symbol) {
    const normalized = normalizeSymbol(symbol);
    if (!normalized) {
      return;
    }
    setBootKey(normalized);
    setSelectedSymbol(normalized);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("symbol", normalized);
    setSearchParams(nextParams);
    try {
      await updateWorkspaceState({ active_symbol: normalized });
    } catch {
      // Search param remains the user-visible source of truth for navigation.
    }
    loadTerminal(normalized, { refreshBootstrap: true, forceFresh: true }).catch(() => {});
  }

  async function handleTimeframeChange(nextTimeframe) {
    setTimeframe(nextTimeframe);
    setBootKey(selectedSymbol, nextTimeframe, rangeKey, compareSymbols);
    try {
      await updateWorkspaceState({ timeframe: nextTimeframe });
    } catch {}
    loadTerminal(selectedSymbol, { refreshBootstrap: false, nextTimeframe }).catch(() => {});
  }

  async function handleRangeChange(nextRangeKey) {
    setRangeKey(nextRangeKey);
    setBootKey(selectedSymbol, timeframe, nextRangeKey, compareSymbols);
    try {
      await updateWorkspaceState({ range_key: nextRangeKey });
    } catch {}
    loadTerminal(selectedSymbol, { refreshBootstrap: false, nextRangeKey }).catch(() => {});
  }

  async function handleCompareChange(nextCompareSymbols) {
    const normalized = (nextCompareSymbols || [])
      .map(normalizeSymbol)
      .filter((item) => item && item !== selectedSymbol)
      .slice(0, 3);
    setCompareSymbols(normalized);
    setBootKey(selectedSymbol, timeframe, rangeKey, normalized);
    try {
      await updateWorkspaceState({ compare_symbols: normalized });
    } catch {}
    loadTerminal(selectedSymbol, { refreshBootstrap: false, nextCompareSymbols: normalized }).catch(() => {});
  }

  async function handleFilterSubmit(event) {
    event.preventDefault();
    setFilters(filterDraft);
    loadTerminal(selectedSymbol, {
      refreshBootstrap: true,
      forceFresh: true,
      nextFilters: filterDraft,
    }).catch(() => {});
  }

  async function handleSelectWatchlist(watchlist) {
    try {
      await updateWorkspaceState({ active_watchlist_id: watchlist.id });
    } catch {}
    if (watchlist.symbols?.[0]) {
      handleSymbolSelect(watchlist.symbols[0]).catch(() => {});
    }
  }

  async function handleAddCurrentSymbol() {
    if (!activeWatchlist?.id || !selectedSymbol) {
      return;
    }
    await addSymbolToWatchlist(activeWatchlist.id, selectedSymbol);
  }

  async function handleRemoveSymbol(watchlist, symbol) {
    await removeSymbolFromWatchlist(watchlist.id, symbol);
  }

  async function handleCreateWatchlist(payload) {
    await createWatchlist(payload);
  }

  const chartOption = useMemo(() => buildChartOption(chartPayload), [chartPayload]);
  const explorerItems = explorer?.items || EMPTY_ITEMS;
  const marketPulse = useMemo(() => {
    const movers = [...explorerItems]
      .filter((item) => item.change_pct !== null && item.change_pct !== undefined)
      .sort((a, b) => Math.abs(Number(b.change_pct || 0)) - Math.abs(Number(a.change_pct || 0)))
      .slice(0, 4);
    const active = [...explorerItems]
      .filter((item) => item.volume !== null && item.volume !== undefined)
      .sort((a, b) => Number(b.volume || 0) - Number(a.volume || 0))
      .slice(0, 4);
    return { movers, active };
  }, [explorerItems]);
  const favoriteSymbolSet = useMemo(
    () => new Set((favoriteSymbols || []).map(normalizeSymbol)),
    [favoriteSymbols]
  );
  const activeWatchlistId = workspace?.active_watchlist_id || activeWatchlist?.id || null;
  const selectedName = selectedSnapshot?.metadata?.security_name || selectedSnapshot?.metadata?.short_name || "الرمز المحدد";
  const isSelectedFavorite = favoriteSymbolSet.has(normalizeSymbol(selectedSymbol));
  const headerActions = useMemo(
    () => (
      <>
        <ActionButton to={`/paper-trading?symbol=${encodeURIComponent(selectedSymbol)}`} variant="secondary">تنفيذ ورقي</ActionButton>
        <StatusBadge label={session?.label || "السوق"} tone={sessionTone(session?.label)} />
      </>
    ),
    [selectedSymbol, session?.label]
  );

  const handleLiveEnabledToggle = useCallback(() => {
    setLiveEnabled((current) => !current);
  }, []);
  const handleFilterQueryChange = useCallback((value) => {
    setFilterDraft((current) => ({ ...current, q: value }));
  }, []);
  const handleFilterExchangeChange = useCallback((value) => {
    setFilterDraft((current) => ({ ...current, exchange: value }));
  }, []);
  const handleFilterTypeChange = useCallback((value) => {
    setFilterDraft((current) => ({ ...current, type: value }));
  }, []);
  const handleFilterCategoryChange = useCallback((value) => {
    setFilterDraft((current) => ({ ...current, category: value }));
  }, []);
  const handleFilterLimitChange = useCallback((value) => {
    setFilterDraft((current) => ({ ...current, limit: value }));
  }, []);

  const handlePresentationalSymbolSelect = useStableCallback((symbol) => handleSymbolSelect(symbol).catch(() => {}));
  const handlePresentationalTimeframeChange = useStableCallback((nextTimeframe) => handleTimeframeChange(nextTimeframe).catch(() => {}));
  const handlePresentationalRangeChange = useStableCallback((nextRangeKey) => handleRangeChange(nextRangeKey).catch(() => {}));
  const handlePresentationalCompareChange = useStableCallback((nextCompareSymbols) => handleCompareChange(nextCompareSymbols).catch(() => {}));
  const handleSelectedFavoriteToggle = useStableCallback(() => toggleFavoriteSymbol(selectedSymbol).catch(() => {}));
  const handleWatchlistSelect = useStableCallback((watchlist) => handleSelectWatchlist(watchlist).catch(() => {}));
  const handleWatchlistCreate = useStableCallback((payload) => handleCreateWatchlist(payload).catch(() => {}));
  const handleWatchlistAddCurrentSymbol = useStableCallback(() => handleAddCurrentSymbol().catch(() => {}));
  const handleWatchlistRemoveSymbol = useStableCallback((watchlist, symbol) => handleRemoveSymbol(watchlist, symbol).catch(() => {}));
  const handleExplorerToggleFavorite = useStableCallback((symbol) => toggleFavoriteSymbol(symbol).catch(() => {}));
  const handleFilterSymbolSelect = useStableCallback((item) => {
    setFilterDraft((current) => ({ ...current, q: item.symbol }));
    return handleSymbolSelect(item.symbol).catch(() => {});
  });
  const handleFilterSubmitStable = useStableCallback((event) => handleFilterSubmit(event).catch(() => {}));

  return (
    <PageFrame
      title="طرفية السوق"
      description="بيئة سوق عربية أولاً تتمحور حول الشارت والرمز والقوائم المتزامنة، مع انتقال سريع من الاكتشاف إلى القرار والتنفيذ الورقي."
      eyebrow="سير عمل السوق"
      headerActions={headerActions}
    >
      <LiveMarketChartSection
        bootLoading={bootLoading}
        chartLoading={chartLoading}
        error={error}
        selectedSymbol={selectedSymbol}
        selectedName={selectedName}
        selectedSnapshot={selectedSnapshot}
        session={session}
        chartPayload={chartPayload}
        chartOption={chartOption}
        liveEnabled={liveEnabled}
        compareSymbols={compareSymbols}
        timeframe={timeframe}
        rangeKey={rangeKey}
        isSelectedFavorite={isSelectedFavorite}
        onToggleLiveEnabled={handleLiveEnabledToggle}
        onTimeframeChange={handlePresentationalTimeframeChange}
        onRangeChange={handlePresentationalRangeChange}
        onSelectedSymbolChange={setSelectedSymbol}
        onSelectSymbol={handlePresentationalSymbolSelect}
        onCompareChange={handlePresentationalCompareChange}
        onToggleFavoriteSymbol={handleSelectedFavoriteToggle}
      />

      <LiveMarketSideColumn
        watchlists={watchlists}
        activeWatchlistId={activeWatchlistId}
        activeSymbol={selectedSymbol}
        workspacePending={workspacePending}
        onSelectWatchlist={handleWatchlistSelect}
        onSelectSymbol={handlePresentationalSymbolSelect}
        onCreateWatchlist={handleWatchlistCreate}
        onAddCurrentSymbol={handleWatchlistAddCurrentSymbol}
        onRemoveSymbol={handleWatchlistRemoveSymbol}
        onToggleFavorite={handleSelectedFavoriteToggle}
        isFavoriteSymbol={isSelectedFavorite}
        bootLoading={bootLoading}
        overview={overview}
        facets={facets}
      />

      <LiveMarketContextSection contextLoading={contextLoading} contextPayload={contextPayload} />

      <LiveMarketMarketPulse
        bootLoading={bootLoading}
        marketPulse={marketPulse}
        onSelectSymbol={handlePresentationalSymbolSelect}
      />

      <LiveMarketFiltersSection
        liveEnabled={liveEnabled}
        explorerTotalMatches={explorer?.total_matches}
        filterDraft={filterDraft}
        facets={facets}
        onSubmit={handleFilterSubmitStable}
        onQueryChange={handleFilterQueryChange}
        onSearchSelect={handleFilterSymbolSelect}
        onExchangeChange={handleFilterExchangeChange}
        onTypeChange={handleFilterTypeChange}
        onCategoryChange={handleFilterCategoryChange}
        onLimitChange={handleFilterLimitChange}
      />

      <LiveMarketExplorerTable
        bootLoading={bootLoading}
        explorerCount={explorer?.count}
        explorerItems={explorerItems}
        favoriteSymbolSet={favoriteSymbolSet}
        onSelectSymbol={handlePresentationalSymbolSelect}
        onToggleFavoriteSymbol={handleExplorerToggleFavorite}
      />
    </PageFrame>
  );
}
