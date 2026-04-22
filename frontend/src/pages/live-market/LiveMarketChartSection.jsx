import { memo } from "react";
import { Link } from "react-router-dom";

import EmptyState from "../../components/ui/EmptyState";
import ErrorBanner from "../../components/ui/ErrorBanner";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton";
import TradingChart from "../../components/ui/TradingChart";
import StatusBadge from "../../components/ui/StatusBadge";
import SymbolMultiPicker from "../../components/ui/SymbolMultiPicker";
import SymbolPicker from "../../components/ui/SymbolPicker";
import { MICRO_TIMEFRAMES, RANGE_OPTIONS, TIMEFRAME_OPTIONS } from "./constants";
import { exchangeTone, formatCompact, formatDelta, formatPercent, formatPrice, sessionTone } from "./formatters";


function LiveMarketChartSection({
  bootLoading,
  chartLoading,
  error,
  selectedSymbol,
  selectedName,
  selectedSnapshot,
  session,
  chartPayload,
  decision,
  liveEnabled,
  compareSymbols,
  timeframe,
  rangeKey,
  isSelectedFavorite,
  onToggleLiveEnabled,
  onTimeframeChange,
  onRangeChange,
  onSelectedSymbolChange,
  onSelectSymbol,
  onCompareChange,
  onToggleFavoriteSymbol,
}) {
  const summaryItems = [
    { label: "التغير السعري", value: formatDelta(selectedSnapshot?.quote?.change), badge: "الجلسة", tone: Number(selectedSnapshot?.quote?.change || 0) >= 0 ? "accent" : "warning" },
    { label: "الحجم", value: formatCompact(selectedSnapshot?.quote?.volume), badge: "سيولة" },
    { label: "القيمة السوقية", value: formatCompact(selectedSnapshot?.quote?.market_cap), badge: "حجم الشركة" },
    { label: "الموقف", value: decision?.stance || selectedSnapshot?.signal || "-", badge: "قرار", tone: decision?.stance === "BUY" ? "accent" : decision?.stance === "SELL" ? "negative" : "warning" },
    { label: "الثقة", value: decision?.confidence ?? "-", badge: "%" },
    { label: "التدفق الحي", value: chartPayload?.live_stream?.connected ? "متصل" : (chartPayload?.live_stream?.provider_status || "fallback"), badge: `${chartPayload?.latest_live_items?.length ?? 0} ticks`, tone: chartPayload?.live_stream?.connected ? "accent" : "warning" },
  ];

  return (
    <TradingChart
      className="span-8 terminal-shell"
      title="الشارت المركزي"
      description="سطح السعر والحجم والمستويات المرتبطة بالرمز النشط."
      badge={selectedSymbol}
      chartData={chartPayload}
      chartPlan={decision?.chart_plan}
      summaryItems={summaryItems}
      loading={bootLoading || chartLoading}
      height={480}
      emptyTitle="لا توجد بيانات شارت كافية"
      emptyDescription={chartPayload?.data_note || "ابدأ بنطاق زمني أوسع أو اترك التحديث الحي يعمل."}
      action={
        <div className="terminal-toolbar-actions">
          <StatusBadge label={chartPayload?.mode === "line" ? "تدفق لحظي" : "OHLCV"} tone={chartPayload?.mode === "line" ? "accent" : "subtle"} />
          <StatusBadge label={chartPayload?.live_stream?.provider_status || "snapshot"} tone={chartPayload?.live_stream?.connected ? "accent" : "warning"} />
          <button className={`secondary-button${liveEnabled ? " active" : ""}`} type="button" onClick={onToggleLiveEnabled}>
            {liveEnabled ? "إيقاف الحي" : "تفعيل الحي"}
          </button>
        </div>
      }
      beforeChart={bootLoading ? null : (
        <>
          <ErrorBanner message={error} />
          <div className="terminal-symbol-strip">
            <div className="terminal-symbol-copy">
              <div className="terminal-symbol-topline">
                <h3>{selectedSymbol}</h3>
                <div className="status-badge-stack">
                  <StatusBadge label={selectedSnapshot?.metadata?.exchange || "Unknown"} tone={exchangeTone(selectedSnapshot?.metadata?.exchange)} />
                  <StatusBadge label={session?.label || "السوق"} tone={sessionTone(session?.label)} />
                  {isSelectedFavorite ? <StatusBadge label="مفضل" tone="accent" /> : null}
                </div>
              </div>
              <p>{selectedName}</p>
            </div>
            <div className="terminal-symbol-price">
              <strong>{formatPrice(selectedSnapshot?.quote?.price)}</strong>
              <span className={Number(selectedSnapshot?.quote?.change_pct || 0) >= 0 ? "quote-positive" : "quote-negative"}>
                {formatPercent(selectedSnapshot?.quote?.change_pct)}
              </span>
            </div>
          </div>

          <div className="terminal-control-group">
            <div className="terminal-control-strip">
              {TIMEFRAME_OPTIONS.map((item) => (
                <button
                  key={`timeframe-${item}`}
                  className={`terminal-chip${item === timeframe ? " active" : ""}${MICRO_TIMEFRAMES.has(item) ? " micro" : ""}`}
                  type="button"
                  onClick={() => onTimeframeChange(item)}
                >
                  {item === "1MTH" ? "1M" : item}
                </button>
              ))}
            </div>
            <div className="terminal-control-strip terminal-control-strip-secondary">
              {RANGE_OPTIONS.map((item) => (
                <button
                  key={`range-${item}`}
                  className={`terminal-chip${item === rangeKey ? " active" : ""}`}
                  type="button"
                  onClick={() => onRangeChange(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="terminal-compare-grid">
            <SymbolPicker
              compact
              label="الرمز النشط"
              value={selectedSymbol}
              onChange={onSelectedSymbolChange}
              onSelect={(item) => onSelectSymbol(item.symbol)}
              placeholder="انتقل فوراً إلى سهم أو ETF"
              helperText="أي تغيير هنا يعيد ربط الشارت والسياق على نفس الرمز."
            />
            <SymbolMultiPicker
              label="مقارنة رموز"
              symbols={compareSymbols}
              maxSymbols={3}
              onChange={onCompareChange}
              helperText="حتى ثلاثة رموز مقارنة إضافية."
            />
          </div>
        </>
      )}
      afterChart={bootLoading ? <LoadingSkeleton lines={3} /> : (
        <div className="market-preview-actions">
          <button className="secondary-button" type="button" onClick={onToggleFavoriteSymbol}>
            {isSelectedFavorite ? "إزالة من المفضلة" : "إضافة إلى المفضلة"}
          </button>
          <Link className="inline-link inline-link-strong" to={`/analyze?symbol=${encodeURIComponent(selectedSymbol)}`}>
            فتح التحليل
          </Link>
          <Link className="inline-link inline-link-strong" to={`/strategy-lab?symbol=${encodeURIComponent(selectedSymbol)}`}>
            فتح الاستراتيجية
          </Link>
          <Link className="inline-link inline-link-strong" to={`/trading?symbol=${encodeURIComponent(selectedSymbol)}`}>
            مكتب التداول
          </Link>
        </div>
      )}
    />
  );
}


export default memo(LiveMarketChartSection);
