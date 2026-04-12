import { memo } from "react";
import { Link } from "react-router-dom";

import ChartCard from "../../components/ui/ChartCard";
import EmptyState from "../../components/ui/EmptyState";
import ErrorBanner from "../../components/ui/ErrorBanner";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton";
import SectionCard from "../../components/ui/SectionCard";
import StatusBadge from "../../components/ui/StatusBadge";
import SummaryStrip from "../../components/ui/SummaryStrip";
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
  chartOption,
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
  return (
    <SectionCard
      className="span-8 terminal-shell"
      title="الشارت المركزي"
      description="ملخص مباشر للسهم النشط، أزرار زمن احترافية، نطاقات سريعة، ومقارنات مرجعية تجعل القرار أسرع وأوضح."
      badge={selectedSymbol}
      action={
        <div className="terminal-toolbar-actions">
          <StatusBadge label={chartPayload?.mode === "line" ? "تدفق لحظي" : "OHLCV"} tone={chartPayload?.mode === "line" ? "accent" : "subtle"} />
          <button className={`secondary-button${liveEnabled ? " active" : ""}`} type="button" onClick={onToggleLiveEnabled}>
            {liveEnabled ? "إيقاف التحديث الحي" : "تفعيل التحديث الحي"}
          </button>
        </div>
      }
    >
      <ErrorBanner message={error} />
      {bootLoading ? (
        <LoadingSkeleton lines={10} />
      ) : (
        <>
          <div className="terminal-symbol-strip">
            <div className="terminal-symbol-copy">
              <div className="terminal-symbol-topline">
                <h3>{selectedSymbol}</h3>
                <div className="status-badge-stack">
                  <StatusBadge label={selectedSnapshot?.metadata?.exchange || "Unknown"} tone={exchangeTone(selectedSnapshot?.metadata?.exchange)} />
                  <StatusBadge label={session?.label || "السوق"} tone={sessionTone(session?.label)} />
                  {isSelectedFavorite ? <StatusBadge label="ضمن المفضلة" tone="accent" /> : null}
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

          <SummaryStrip
            items={[
              { label: "التغير السعري", value: formatDelta(selectedSnapshot?.quote?.change), badge: "الجلسة", tone: Number(selectedSnapshot?.quote?.change || 0) >= 0 ? "accent" : "warning" },
              { label: "الحجم", value: formatCompact(selectedSnapshot?.quote?.volume), badge: "سيولة" },
              { label: "القيمة السوقية", value: formatCompact(selectedSnapshot?.quote?.market_cap), badge: "حجم الشركة" },
              { label: "مقارنات", value: compareSymbols.length ? compareSymbols.join(" · ") : "بدون مقارنة", badge: "Overlay" },
            ]}
          />

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
              helperText="أي تغيير هنا يعيد ربط الشارت والسياق ولوحة القوائم على نفس الرمز."
            />
            <SymbolMultiPicker
              label="مقارنة رموز"
              symbols={compareSymbols}
              maxSymbols={3}
              onChange={onCompareChange}
              helperText="يمكنك مقارنة حتى ثلاثة رموز إضافية كنسبة أداء تراكمية أسفل الشارت."
            />
          </div>

          {chartLoading ? (
            <LoadingSkeleton lines={8} />
          ) : chartOption ? (
            <ChartCard
              title={`${selectedSymbol} Chart`}
              description={chartPayload?.data_note || "شارت متعدد الطبقات مع حجم ومقارنات مرجعية ونطاقات زمنية سريعة."}
              option={chartOption}
              height={560}
              className="terminal-chart-card"
            />
          ) : (
            <EmptyState
              title="لا توجد بيانات شارت كافية"
              description="ابدأ بنطاق زمني أوسع أو اترك التحديث الحي يعمل قليلاً لتجميع اللقطات اللحظية تحت الدقيقة."
            />
          )}

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
            <Link className="inline-link inline-link-strong" to={`/paper-trading?symbol=${encodeURIComponent(selectedSymbol)}`}>
              تنفيذ ورقي
            </Link>
          </div>
        </>
      )}
    </SectionCard>
  );
}


export default memo(LiveMarketChartSection);
