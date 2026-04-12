import { memo } from "react";

import EmptyState from "../../components/ui/EmptyState";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton";
import SectionCard from "../../components/ui/SectionCard";
import SummaryStrip from "../../components/ui/SummaryStrip";
import WatchlistDock from "../../components/ui/WatchlistDock";
import { formatNumber, formatPercent, formatPrice } from "./formatters";


function LiveMarketSideColumn({
  watchlists,
  activeWatchlistId,
  activeSymbol,
  workspacePending,
  onSelectWatchlist,
  onSelectSymbol,
  onCreateWatchlist,
  onAddCurrentSymbol,
  onRemoveSymbol,
  onToggleFavorite,
  isFavoriteSymbol,
  bootLoading,
  overview,
  facets,
}) {
  return (
    <div className="span-4 terminal-side-column">
      <WatchlistDock
        watchlists={watchlists}
        activeWatchlistId={activeWatchlistId}
        activeSymbol={activeSymbol}
        pending={workspacePending}
        onSelectWatchlist={onSelectWatchlist}
        onSelectSymbol={onSelectSymbol}
        onCreateWatchlist={onCreateWatchlist}
        onAddCurrentSymbol={onAddCurrentSymbol}
        onRemoveSymbol={onRemoveSymbol}
        onToggleFavorite={onToggleFavorite}
        isFavoriteSymbol={isFavoriteSymbol}
      />

      <SectionCard
        className="terminal-overview-panel"
        title="شريط السوق"
        description="شريط جلسة سريع يلخص المؤشرات، القادة، وحالة الكون النشط من دون سحبك بعيداً عن الشارت."
        badge={overview?.indices?.length ? `${overview.indices.length} مؤشر` : "السوق"}
      >
        {bootLoading ? (
          <LoadingSkeleton lines={5} />
        ) : overview ? (
          <>
            <SummaryStrip
              items={[
                { label: "الكون النشط", value: formatNumber(facets?.total_symbols || overview?.universe_status?.total_symbols || 0), badge: "رمز" },
                { label: "NASDAQ", value: formatNumber(overview?.universe_status?.nasdaq_count || 0), badge: "سوق" },
                { label: "NYSE", value: formatNumber(overview?.universe_status?.nyse_count || 0), badge: "سوق" },
                { label: "ETF", value: formatNumber(overview?.universe_status?.etf_count || 0), badge: "إدراج" },
              ]}
            />
            <div className="terminal-index-list">
              {(overview.indices || []).map((item) => (
                <div className="terminal-index-item" key={`index-${item.symbol}`}>
                  <div>
                    <strong>{item.label || item.symbol}</strong>
                    <p>{formatPrice(item.price)}</p>
                  </div>
                  <span className={Number(item.change_pct || 0) >= 0 ? "quote-positive" : "quote-negative"}>
                    {formatPercent(item.change_pct)}
                  </span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <EmptyState title="نبض السوق غير متاح" description="المنصة تحتاج عودة خدمة نظرة السوق حتى يظهر شريط المؤشرات والقادة اللحظيين." />
        )}
      </SectionCard>
    </div>
  );
}


export default memo(LiveMarketSideColumn);
