import { useMemo, useState } from "react";

import EmptyState from "./EmptyState";
import SectionHeader from "./SectionHeader";
import StatusBadge from "./StatusBadge";


export default function WatchlistDock({
  watchlists = [],
  activeWatchlistId = null,
  activeSymbol = "",
  pending = false,
  onSelectWatchlist,
  onSelectSymbol,
  onCreateWatchlist,
  onAddCurrentSymbol,
  onRemoveSymbol,
  onToggleFavorite,
  isFavoriteSymbol,
}) {
  const [watchlistName, setWatchlistName] = useState("");
  const activeWatchlist = useMemo(
    () => watchlists.find((item) => item.id === activeWatchlistId) || watchlists[0] || null,
    [activeWatchlistId, watchlists]
  );

  async function handleCreateWatchlist() {
    const normalized = String(watchlistName || "").trim();
    if (!normalized) {
      return;
    }
    await onCreateWatchlist?.({
      name: normalized,
      category: "custom",
      color_token: "cyan",
    });
    setWatchlistName("");
  }

  function fireAndForget(action) {
    Promise.resolve(action?.()).catch(() => {});
  }

  return (
    <div className="panel result-panel watchlist-dock">
      <SectionHeader
        title="مساحة القوائم"
        description="قوائم خادم متزامنة للمتابعة اليومية، مع تثبيت الرمز النشط وإرساله مباشرة إلى الشارت أو مكتب التداول."
        badge={activeWatchlist?.name || "قوائم"}
        action={<StatusBadge label={pending ? "جارٍ الحفظ" : "متزامنة"} tone={pending ? "warning" : "accent"} />}
      />

      <div className="watchlist-tab-row">
        {watchlists.map((watchlist) => (
          <button
            key={`watchlist-${watchlist.id}`}
            className={`watchlist-tab${watchlist.id === activeWatchlist?.id ? " active" : ""}`}
            type="button"
            onClick={() => onSelectWatchlist?.(watchlist)}
          >
            <strong>{watchlist.name}</strong>
            <span>{watchlist.count || watchlist.symbols?.length || 0}</span>
          </button>
        ))}
      </div>

      <div className="watchlist-toolbar">
        <button className="primary-button" type="button" disabled={!activeSymbol || pending} onClick={() => fireAndForget(onAddCurrentSymbol)}>
          إضافة {activeSymbol || "الرمز"} إلى القائمة
        </button>
        <button className="secondary-button" type="button" disabled={!activeSymbol || pending} onClick={() => fireAndForget(onToggleFavorite)}>
          {isFavoriteSymbol ? "إزالة من المفضلة" : "إضافة إلى المفضلة"}
        </button>
      </div>

      <div className="watchlist-create-row">
        <input
          value={watchlistName}
          onChange={(event) => setWatchlistName(event.target.value)}
          placeholder="أنشئ قائمة جديدة باسم واضح"
        />
        <button className="secondary-button" type="button" disabled={pending || !watchlistName.trim()} onClick={() => fireAndForget(handleCreateWatchlist)}>
          إنشاء
        </button>
      </div>

      {activeWatchlist?.items?.length ? (
        <div className="watchlist-item-list">
          {activeWatchlist.items.map((item) => (
            <div
            key={`watchlist-item-${activeWatchlist.id}-${item.symbol}`}
            className={`watchlist-item${item.symbol === activeSymbol ? " active" : ""}`}
          >
              <button className="watchlist-item-button" type="button" onClick={() => fireAndForget(() => onSelectSymbol?.(item.symbol))}>
                <strong>{item.symbol}</strong>
                <span>{item.notes || "انتقال سريع إلى الشارت والتحليل ومكتب التداول"}</span>
              </button>
              {!activeWatchlist.is_system ? (
                <button
                  className="watchlist-item-remove"
                  type="button"
                  disabled={pending}
                  onClick={() => fireAndForget(() => onRemoveSymbol?.(activeWatchlist, item.symbol))}
                >
                  إزالة
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <EmptyState
          title="القائمة الحالية فارغة"
          description="أضف الرمز النشط أو أنشئ قائمة مخصصة حتى تصبح مساحة العمل أقرب لطرفية متابعة يومية."
        />
      )}
    </div>
  );
}
