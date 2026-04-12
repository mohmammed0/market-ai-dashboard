import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useSymbolLibrary } from "../../lib/useSymbolLibrary";
import { useWorkspace } from "../../lib/useWorkspace";
import ActionButton from "./ActionButton";
import SymbolBadge from "./SymbolBadge";
import SymbolPicker from "./SymbolPicker";
import StatusBadge from "./StatusBadge";


const DEFAULT_SYMBOL = "AAPL";


export default function SymbolWorkspaceBar({ compact = false }) {
  const navigate = useNavigate();
  const { pinned, recent, rememberSymbol, togglePinnedSymbol, isPinnedSymbol } = useSymbolLibrary();
  const {
    workspace,
    activeWatchlist,
    favoriteSymbols,
    isFavoriteSymbol,
    toggleFavoriteSymbol,
    updateWorkspaceState,
    pending,
  } = useWorkspace();
  const [selectedSymbol, setSelectedSymbol] = useState(DEFAULT_SYMBOL);

  useEffect(() => {
    const preferredSymbol = workspace?.active_symbol || pinned[0]?.symbol || recent[0]?.symbol || DEFAULT_SYMBOL;
    setSelectedSymbol((current) => {
      const normalizedCurrent = String(current || "").trim().toUpperCase();
      if (!normalizedCurrent || normalizedCurrent === DEFAULT_SYMBOL) {
        return preferredSymbol;
      }
      return normalizedCurrent;
    });
  }, [workspace?.active_symbol, pinned, recent]);

  async function selectWorkspaceSymbol(item) {
    const symbol = String(item?.symbol || selectedSymbol || "").trim().toUpperCase();
    if (!symbol) {
      return;
    }
    const normalizedItem = { ...item, symbol };
    setSelectedSymbol(symbol);
    rememberSymbol(normalizedItem);
    try {
      await updateWorkspaceState({ active_symbol: symbol });
    } catch {
      // Workspace persistence is helpful but should not block navigation.
    }
  }

  function jumpTo(pathname) {
    const symbol = String(selectedSymbol || "").trim().toUpperCase();
    if (!symbol) {
      return;
    }
    selectWorkspaceSymbol({ symbol }).catch(() => {});
    navigate(`${pathname}?symbol=${encodeURIComponent(symbol)}`);
  }

  const currentItem = pinned.find((item) => item.symbol === selectedSymbol)
    || recent.find((item) => item.symbol === selectedSymbol)
    || { symbol: selectedSymbol };
  const watchlistChips = activeWatchlist?.symbols?.length ? activeWatchlist.symbols.slice(0, 6) : favoriteSymbols.slice(0, 6);

  return (
    <div className={`workspace-symbol-bar${compact ? " compact" : ""}`}>
      <div className="workspace-symbol-picker">
        <SymbolPicker
          compact
          label="رمز العمل"
          value={selectedSymbol}
          onChange={setSelectedSymbol}
          onSelect={selectWorkspaceSymbol}
          placeholder="ابحث عن سهم أو ETF أو شركة"
          helperText="اختصار موحد للتنقل السريع مع حفظ الرمز النشط عبر مساحة العمل والصفحات الرئيسية."
        />
      </div>
      <div className="workspace-symbol-actions">
        <ActionButton variant="primary" onClick={() => jumpTo("/analyze")}>تحليل</ActionButton>
        <ActionButton variant="secondary" onClick={() => jumpTo("/live-market")}>المستكشف</ActionButton>
        <ActionButton variant="secondary" onClick={() => jumpTo("/strategy-lab")}>الاستراتيجية</ActionButton>
        <ActionButton variant="secondary" onClick={() => jumpTo("/paper-trading")}>ورقي</ActionButton>
        <ActionButton variant="ghost" onClick={() => togglePinnedSymbol(currentItem)}>
          {isPinnedSymbol(selectedSymbol) ? "إلغاء التثبيت" : "تثبيت"}
        </ActionButton>
        <ActionButton
          variant="ghost"
          disabled={pending}
          onClick={() => toggleFavoriteSymbol(selectedSymbol).catch(() => {})}
        >
          {isFavoriteSymbol(selectedSymbol) ? "إزالة من المفضلة" : "إضافة إلى المفضلة"}
        </ActionButton>
      </div>
      <div className="workspace-symbol-meta">
        <StatusBadge label={isPinnedSymbol(selectedSymbol) ? "مثبّت محلياً" : "تنقل سريع"} tone="subtle" />
        {activeWatchlist?.name ? <StatusBadge label={`قائمة ${activeWatchlist.name}`} tone="accent" /> : null}
        {watchlistChips.map((symbol) => (
          <button
            key={`workspace-${symbol}`}
            className="workspace-symbol-chip"
            type="button"
            onClick={() => selectWorkspaceSymbol({ symbol }).catch(() => {})}
          >
            <SymbolBadge symbol={symbol} />
          </button>
        ))}
      </div>
    </div>
  );
}
