/**
 * AIMarketPage — محطة الذكاء الاصطناعي للسوق المالي
 * الواجهة الرئيسية للطرفية الاحترافية: شارت OHLCV + لوحة ذكاء متكاملة
 */

import { useEffect, useRef, useCallback, useState, useMemo } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";

import {
  fetchMacroCalendar,
  fetchRankingLeaders,
  fetchFundamentals,
  fetchMarketHistory,
  fetchQuoteSnapshot,
  calculateKelly,
} from "../api/intelligence";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_SYMBOL = "AAPL";

const QUICK_SYMBOLS = ["AAPL", "MSFT", "NVDA", "SPY", "TSLA"];

const TIMEFRAMES = [
  { label: "أسبوع", key: "1W", days: 7, interval: "1d" },
  { label: "شهر", key: "1M", days: 30, interval: "1d" },
  { label: "3 أشهر", key: "3M", days: 90, interval: "1d" },
  { label: "6 أشهر", key: "6M", days: 180, interval: "1d" },
  { label: "سنة", key: "1Y", days: 365, interval: "1d" },
];

const CHART_HEIGHT = 420;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function subtractDays(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function datetimeToTimestamp(datetime) {
  const s = String(datetime || "");
  if (s.length <= 10) {
    return Math.floor(new Date(s + "T00:00:00Z").getTime() / 1000);
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? 0 : Math.floor(d.getTime() / 1000);
}

function formatLargeNumber(value) {
  if (value == null || isNaN(Number(value))) return "—";
  const n = Number(value);
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(2)}`;
}

function formatNumber(value, decimals = 2) {
  if (value == null || isNaN(Number(value))) return "—";
  return Number(value).toFixed(decimals);
}

function signalLabel(score) {
  if (score == null) return { text: "—", color: "#94a3b8" };
  const s = Number(score);
  if (s >= 65) return { text: "شراء", color: "#22c55e" };
  if (s <= 35) return { text: "بيع", color: "#ef4444" };
  return { text: "محايد", color: "#f59e0b" };
}

function regimeColor(regime) {
  if (!regime) return "#94a3b8";
  const r = String(regime).toLowerCase();
  if (r.includes("risk_on") || r.includes("on")) return "#22c55e";
  if (r.includes("risk_off") || r.includes("off")) return "#ef4444";
  return "#f59e0b";
}

function regimeLabel(regime) {
  if (!regime) return "—";
  const r = String(regime).toLowerCase();
  if (r.includes("risk_on")) return "مخاطرة مرتفعة";
  if (r.includes("risk_off")) return "مخاطرة منخفضة";
  return "محايد";
}

// ---------------------------------------------------------------------------
// Inline styles (CSS vars from design system)
// ---------------------------------------------------------------------------

const S = {
  page: {
    display: "grid",
    gridTemplateColumns: "1fr 320px",
    gridTemplateRows: "auto 1fr",
    gap: "0",
    minHeight: "100vh",
    background: "var(--color-bg-canvas, #0f172a)",
    color: "var(--color-text-primary, #f1f5f9)",
    direction: "rtl",
    fontFamily: "'IBM Plex Sans Arabic', sans-serif",
  },
  toolbar: {
    gridColumn: "1 / -1",
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "12px 20px",
    borderBottom: "1px solid var(--color-border, rgba(148,163,184,0.12))",
    background: "var(--color-bg-surface, #1e293b)",
    flexWrap: "wrap",
  },
  symbolInput: {
    background: "rgba(15,23,42,0.6)",
    border: "1px solid var(--color-border, rgba(148,163,184,0.2))",
    borderRadius: "6px",
    color: "var(--color-text-primary, #f1f5f9)",
    padding: "6px 12px",
    fontSize: "14px",
    width: "120px",
    outline: "none",
    textTransform: "uppercase",
    direction: "ltr",
  },
  quickBtn: (active) => ({
    padding: "5px 12px",
    borderRadius: "6px",
    border: active
      ? "1px solid var(--tv-accent, #60a5fa)"
      : "1px solid var(--color-border, rgba(148,163,184,0.2))",
    background: active ? "rgba(96,165,250,0.15)" : "transparent",
    color: active ? "var(--tv-accent, #60a5fa)" : "var(--color-text-secondary, #94a3b8)",
    fontSize: "13px",
    cursor: "pointer",
    fontFamily: "inherit",
    transition: "all 0.15s",
  }),
  timeframeDivider: {
    width: "1px",
    height: "24px",
    background: "var(--color-border, rgba(148,163,184,0.15))",
    margin: "0 4px",
  },
  tfBtn: (active) => ({
    padding: "5px 14px",
    borderRadius: "6px",
    border: "none",
    background: active ? "var(--tv-accent, #60a5fa)" : "transparent",
    color: active ? "#0f172a" : "var(--color-text-secondary, #94a3b8)",
    fontSize: "13px",
    fontWeight: active ? "600" : "400",
    cursor: "pointer",
    fontFamily: "inherit",
    transition: "all 0.15s",
  }),
  chartPanel: {
    gridColumn: "1",
    gridRow: "2",
    background: "var(--color-bg-canvas, #0f172a)",
    borderLeft: "1px solid var(--color-border, rgba(148,163,184,0.12))",
    display: "flex",
    flexDirection: "column",
  },
  chartHeader: {
    padding: "14px 20px 10px",
    borderBottom: "1px solid var(--color-border, rgba(148,163,184,0.08))",
  },
  chartTitle: {
    margin: 0,
    fontSize: "18px",
    fontWeight: "700",
    color: "var(--color-text-primary, #f1f5f9)",
    letterSpacing: "0.5px",
  },
  chartSubtitle: {
    margin: "3px 0 0",
    fontSize: "12px",
    color: "var(--color-text-secondary, #94a3b8)",
  },
  chartContainer: {
    flex: 1,
    position: "relative",
  },
  chartCanvas: {
    width: "100%",
  },
  sidePanel: {
    gridColumn: "2",
    gridRow: "2",
    background: "var(--color-bg-surface, #1e293b)",
    borderRight: "1px solid var(--color-border, rgba(148,163,184,0.12))",
    overflowY: "auto",
    padding: "0",
  },
  card: {
    padding: "16px 18px",
    borderBottom: "1px solid var(--color-border, rgba(148,163,184,0.08))",
  },
  cardTitle: {
    margin: "0 0 12px",
    fontSize: "13px",
    fontWeight: "600",
    color: "var(--color-text-secondary, #94a3b8)",
    textTransform: "uppercase",
    letterSpacing: "0.8px",
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  cardIcon: {
    fontSize: "15px",
  },
  statRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "8px",
  },
  statLabel: {
    fontSize: "12px",
    color: "var(--color-text-secondary, #94a3b8)",
  },
  statValue: (color) => ({
    fontSize: "14px",
    fontWeight: "600",
    color: color || "var(--color-text-primary, #f1f5f9)",
    direction: "ltr",
  }),
  bigStat: (color) => ({
    fontSize: "28px",
    fontWeight: "700",
    color: color || "var(--color-text-primary, #f1f5f9)",
    lineHeight: 1,
    margin: "6px 0",
    direction: "ltr",
  }),
  badge: (color, bg) => ({
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "12px",
    fontWeight: "600",
    color: color || "#f1f5f9",
    background: bg || "rgba(148,163,184,0.15)",
  }),
  skeleton: {
    background: "linear-gradient(90deg, rgba(148,163,184,0.06) 25%, rgba(148,163,184,0.1) 50%, rgba(148,163,184,0.06) 75%)",
    backgroundSize: "200% 100%",
    animation: "skeleton-shimmer 1.5s infinite",
    borderRadius: "4px",
    height: "16px",
    marginBottom: "8px",
  },
  errorText: {
    fontSize: "12px",
    color: "#ef4444",
    padding: "8px 0",
  },
  divider: {
    borderColor: "rgba(148,163,184,0.08)",
    margin: "10px 0",
  },
  priceBig: {
    fontSize: "26px",
    fontWeight: "700",
    letterSpacing: "-0.5px",
    direction: "ltr",
  },
  changeRow: {
    display: "flex",
    gap: "8px",
    alignItems: "center",
    marginTop: "2px",
    direction: "ltr",
  },
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Skeleton({ lines = 3, width }) {
  return (
    <>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          style={{
            ...S.skeleton,
            width: width || (i % 2 === 0 ? "80%" : "55%"),
            opacity: 1 - i * 0.15,
          }}
        />
      ))}
    </>
  );
}

function SectionError({ message }) {
  return <div style={S.errorText}>خطأ: {message}</div>;
}

// ---------------------------------------------------------------------------
// Chart hook — lightweight-charts v5 direct integration
// ---------------------------------------------------------------------------

function useTradeChart(containerRef, chartData, chartLoading) {
  const chartRef = useRef(null);
  const seriesRef = useRef({});

  useEffect(() => {
    if (!containerRef.current) return;
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
      seriesRef.current = {};
    }

    const items = chartData?.items || [];
    if (!items.length) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: CHART_HEIGHT,
      layout: {
        background: { color: "transparent" },
        textColor: "#94a3b8",
        fontFamily: "'IBM Plex Sans Arabic', sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.06)" },
        horzLines: { color: "rgba(148, 163, 184, 0.06)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(96, 165, 250, 0.3)", width: 1, style: LineStyle.Dashed },
        horzLine: { color: "rgba(96, 165, 250, 0.3)", width: 1, style: LineStyle.Dashed },
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.12)",
        timeVisible: false,
        rightOffset: 5,
        barSpacing: 6,
        minBarSpacing: 3,
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.12)",
        scaleMargins: { top: 0.05, bottom: 0.2 },
      },
      handleScale: { mouseWheel: true, pinch: true },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
    });

    chartRef.current = chart;

    // Build candle data
    const candleData = items
      .filter((it) => it.datetime && it.close != null)
      .map((it) => ({
        time: datetimeToTimestamp(it.datetime),
        open: Number(it.open ?? it.close),
        high: Number(it.high ?? it.close),
        low: Number(it.low ?? it.close),
        close: Number(it.close),
      }))
      .sort((a, b) => a.time - b.time);

    const volData = items
      .filter((it) => it.datetime && it.volume != null && Number(it.volume) > 0)
      .map((it) => {
        const close = Number(it.close ?? 0);
        const open = Number(it.open ?? close);
        return {
          time: datetimeToTimestamp(it.datetime),
          value: Number(it.volume),
          color: close >= open ? "rgba(34, 197, 94, 0.35)" : "rgba(249, 115, 22, 0.35)",
        };
      })
      .sort((a, b) => a.time - b.time);

    if (candleData.length) {
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderUpColor: "#22c55e",
        borderDownColor: "#ef4444",
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
        lastValueVisible: true,
        priceLineVisible: true,
      });
      candleSeries.setData(candleData);
      seriesRef.current.candle = candleSeries;
    }

    if (volData.length) {
      const volSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
        lastValueVisible: false,
        priceLineVisible: false,
      });
      chart.priceScale("volume").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      });
      volSeries.setData(volData);
      seriesRef.current.volume = volSeries;
    }

    chart.timeScale().fitContent();

    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = {};
      }
    };
  }, [chartData]);

  // Resize observer
  useEffect(() => {
    if (!chartRef.current || !containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (chartRef.current) {
          chartRef.current.applyOptions({ width: entry.contentRect.width });
        }
      }
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [chartData]);
}

// ---------------------------------------------------------------------------
// Signal Card
// ---------------------------------------------------------------------------

function SignalCard({ symbol, loading, error, data }) {
  const entry = useMemo(() => {
    if (!data?.items && !Array.isArray(data)) return null;
    const list = Array.isArray(data) ? data : (data?.items || data?.leaders || []);
    return list.find((item) => String(item.symbol || "").toUpperCase() === String(symbol || "").toUpperCase()) || null;
  }, [data, symbol]);

  const score = entry?.score ?? entry?.composite_score ?? null;
  const signal = signalLabel(score);
  const price = entry?.close ?? entry?.price ?? null;
  const changePct = entry?.change_pct ?? null;

  return (
    <div style={S.card}>
      <div style={S.cardTitle}>
        <span style={S.cardIcon}>📊</span>
        إشارة الذكاء الاصطناعي
      </div>
      {loading ? (
        <Skeleton lines={3} />
      ) : error ? (
        <SectionError message={error} />
      ) : (
        <>
          <div style={S.bigStat(signal.color)}>
            {score != null ? `${Number(score).toFixed(0)}` : "—"}
            {score != null && (
              <span style={{ fontSize: "14px", marginRight: "8px", fontWeight: "400" }}>/ 100</span>
            )}
          </div>
          <div style={{ marginTop: "6px", marginBottom: "10px" }}>
            <span
              style={S.badge(
                signal.color,
                signal.color === "#22c55e"
                  ? "rgba(34,197,94,0.15)"
                  : signal.color === "#ef4444"
                  ? "rgba(239,68,68,0.15)"
                  : "rgba(245,158,11,0.15)"
              )}
            >
              {signal.text}
            </span>
          </div>
          {price != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>السعر</span>
              <span style={S.statValue()}>
                ${Number(price).toFixed(2)}
              </span>
            </div>
          )}
          {changePct != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>التغير</span>
              <span
                style={S.statValue(Number(changePct) >= 0 ? "#22c55e" : "#ef4444")}
              >
                {Number(changePct) >= 0 ? "+" : ""}
                {Number(changePct).toFixed(2)}%
              </span>
            </div>
          )}
          {!entry && (
            <div style={{ fontSize: "12px", color: "#94a3b8" }}>
              لا توجد بيانات إشارة للرمز المحدد
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quote Card (price snapshot from market history)
// ---------------------------------------------------------------------------

function QuoteCard({ symbol, historyData, historyLoading, historyError }) {
  const latest = useMemo(() => {
    const items = historyData?.items || [];
    if (!items.length) return null;
    return items[items.length - 1];
  }, [historyData]);

  const changePct = useMemo(() => {
    const items = historyData?.items || [];
    if (items.length < 2) return null;
    const prev = items[items.length - 2].close;
    const curr = items[items.length - 1].close;
    if (!prev || !curr) return null;
    return ((curr - prev) / prev) * 100;
  }, [historyData]);

  if (historyLoading) return null; // shown as part of chart loading
  if (!latest) return null;

  const isUp = changePct == null || changePct >= 0;

  return (
    <div style={{ padding: "10px 20px 6px", borderBottom: "1px solid var(--color-border, rgba(148,163,184,0.08))" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "16px" }}>
        <span style={{ ...S.priceBig, color: isUp ? "#22c55e" : "#ef4444" }}>
          ${Number(latest.close).toFixed(2)}
        </span>
        {changePct != null && (
          <span style={{ fontSize: "14px", color: isUp ? "#22c55e" : "#ef4444", fontWeight: "500", direction: "ltr" }}>
            {isUp ? "+" : ""}{changePct.toFixed(2)}%
          </span>
        )}
        <span style={{ fontSize: "12px", color: "#94a3b8", marginRight: "auto" }}>
          آخر إغلاق
        </span>
      </div>
      {latest.volume != null && (
        <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "4px", direction: "ltr" }}>
          الحجم: {Number(latest.volume).toLocaleString()}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Macro Card
// ---------------------------------------------------------------------------

function MacroCard({ loading, error, data }) {
  const macro_score = data?.macro_score ?? null;
  const macro_regime = data?.macro_regime ?? null;
  const vix = data?.vix ?? null;
  const yield_spread = data?.yield_spread_10y2y ?? null;
  const fed_funds = data?.fed_funds_rate ?? null;

  const rColor = regimeColor(macro_regime);

  return (
    <div style={S.card}>
      <div style={S.cardTitle}>
        <span style={S.cardIcon}>🌍</span>
        البيئة الكلية
      </div>
      {loading ? (
        <Skeleton lines={4} />
      ) : error ? (
        <SectionError message={error} />
      ) : (
        <>
          {macro_score != null && (
            <>
              <div style={{ ...S.bigStat(), color: rColor }}>
                {Number(macro_score).toFixed(0)}
                <span style={{ fontSize: "13px", fontWeight: "400", color: "#94a3b8", marginRight: "6px" }}>/ 100</span>
              </div>
              <div style={{ marginBottom: "10px" }}>
                <span style={S.badge(rColor, rColor + "22")}>
                  {regimeLabel(macro_regime)}
                </span>
              </div>
            </>
          )}
          {vix != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>VIX</span>
              <span style={S.statValue(Number(vix) > 25 ? "#ef4444" : Number(vix) > 18 ? "#f59e0b" : "#22c55e")}>
                {Number(vix).toFixed(2)}
              </span>
            </div>
          )}
          {yield_spread != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>انتشار 10y/2y</span>
              <span style={S.statValue(Number(yield_spread) < 0 ? "#ef4444" : "#22c55e")}>
                {Number(yield_spread).toFixed(2)}%
              </span>
            </div>
          )}
          {fed_funds != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>الفيدرالي</span>
              <span style={S.statValue()}>
                {Number(fed_funds).toFixed(2)}%
              </span>
            </div>
          )}
          {macro_score == null && vix == null && (
            <div style={{ fontSize: "12px", color: "#94a3b8" }}>لا توجد بيانات كلية متاحة</div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fundamentals Card
// ---------------------------------------------------------------------------

function FundamentalsCard({ loading, error, data }) {
  const revenue = data?.revenue_ttm ?? null;
  const net_income = data?.net_income_ttm ?? null;
  const eps = data?.eps_ttm ?? null;
  const de = data?.debt_to_equity ?? null;
  const name = data?.entity_name ?? null;

  return (
    <div style={S.card}>
      <div style={S.cardTitle}>
        <span style={S.cardIcon}>🏛</span>
        الأساسيات المالية
      </div>
      {loading ? (
        <Skeleton lines={4} />
      ) : error ? (
        <SectionError message={error} />
      ) : (
        <>
          {name && (
            <div style={{ fontSize: "12px", color: "#94a3b8", marginBottom: "10px" }}>
              {name}
            </div>
          )}
          {revenue != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>الإيرادات (TTM)</span>
              <span style={S.statValue()}>{formatLargeNumber(revenue)}</span>
            </div>
          )}
          {net_income != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>صافي الربح (TTM)</span>
              <span style={S.statValue(Number(net_income) >= 0 ? "#22c55e" : "#ef4444")}>
                {formatLargeNumber(net_income)}
              </span>
            </div>
          )}
          {eps != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>ربحية السهم (EPS)</span>
              <span style={S.statValue(Number(eps) >= 0 ? "#22c55e" : "#ef4444")}>
                ${formatNumber(eps)}
              </span>
            </div>
          )}
          {de != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>الدين / حقوق الملكية</span>
              <span style={S.statValue(Number(de) > 2 ? "#ef4444" : Number(de) > 1 ? "#f59e0b" : "#22c55e")}>
                {formatNumber(de)}x
              </span>
            </div>
          )}
          {revenue == null && eps == null && (
            <div style={{ fontSize: "12px", color: "#94a3b8" }}>لا توجد بيانات أساسية متاحة</div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Position Sizing Card
// ---------------------------------------------------------------------------

function SizingCard({ loading, error, data }) {
  const kellyFraction = data?.kelly_fraction ?? data?.kelly_pct ?? null;
  const halfKelly = kellyFraction != null ? Number(kellyFraction) / 2 : null;
  const positionSize = data?.position_size ?? data?.shares ?? null;
  const dollarRisk = data?.dollar_risk ?? null;

  return (
    <div style={S.card}>
      <div style={S.cardTitle}>
        <span style={S.cardIcon}>📐</span>
        تحجيم المراكز
      </div>
      {loading ? (
        <Skeleton lines={3} />
      ) : error ? (
        <SectionError message={error} />
      ) : (
        <>
          <div style={{ fontSize: "11px", color: "#64748b", marginBottom: "10px" }}>
            نسبة الفوز 55% · متوسط الربح 2% · متوسط الخسارة 1%
          </div>
          {halfKelly != null && (
            <>
              <div style={S.statRow}>
                <span style={S.statLabel}>كيلي نصفي</span>
                <span style={S.statValue("#60a5fa")}>
                  {halfKelly.toFixed(2)}%
                </span>
              </div>
              <div style={S.statRow}>
                <span style={S.statLabel}>من رأس المال ($100K)</span>
                <span style={S.statValue()}>
                  ${(100000 * halfKelly / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              </div>
            </>
          )}
          {kellyFraction == null && (
            <div style={{ fontSize: "12px", color: "#94a3b8" }}>
              نسبة كيلي الكاملة:{" "}
              <strong style={{ color: "#60a5fa" }}>
                {/* Default calculation: Kelly = W - (1-W)/R = 0.55 - 0.45/2 = 0.325 → half = 16.25% */}
                16.25%
              </strong>
            </div>
          )}
          {positionSize != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>عدد الأسهم (ATR)</span>
              <span style={S.statValue()}>{Number(positionSize).toFixed(0)}</span>
            </div>
          )}
          {dollarRisk != null && (
            <div style={S.statRow}>
              <span style={S.statLabel}>المخاطرة بالدولار</span>
              <span style={S.statValue("#f59e0b")}>${Number(dollarRisk).toFixed(0)}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chart loading / empty overlay
// ---------------------------------------------------------------------------

function ChartOverlay({ loading, hasData }) {
  if (!loading && hasData) return null;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(15,23,42,0.7)",
        zIndex: 10,
      }}
    >
      {loading ? (
        <div style={{ textAlign: "center", color: "#94a3b8" }}>
          <div
            style={{
              width: "36px",
              height: "36px",
              border: "3px solid rgba(96,165,250,0.3)",
              borderTopColor: "#60a5fa",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
              margin: "0 auto 10px",
            }}
          />
          <div style={{ fontSize: "13px" }}>جاري تحميل الشارت…</div>
        </div>
      ) : (
        <div style={{ textAlign: "center", color: "#94a3b8" }}>
          <div style={{ fontSize: "32px", marginBottom: "8px" }}>📈</div>
          <div style={{ fontSize: "14px" }}>لا توجد بيانات للرسم البياني</div>
          <div style={{ fontSize: "12px", marginTop: "4px" }}>اختر نطاقاً زمنياً أوسع</div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

export default function AIMarketPage() {
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);
  const [inputVal, setInputVal] = useState(DEFAULT_SYMBOL);
  const [activeTimeframe, setActiveTimeframe] = useState("3M");

  // Chart data
  const [historyData, setHistoryData] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);

  // Signal / leaders
  const [signalData, setSignalData] = useState(null);
  const [signalLoading, setSignalLoading] = useState(false);
  const [signalError, setSignalError] = useState(null);

  // Macro
  const [macroData, setMacroData] = useState(null);
  const [macroLoading, setMacroLoading] = useState(false);
  const [macroError, setMacroError] = useState(null);

  // Fundamentals
  const [fundData, setFundData] = useState(null);
  const [fundLoading, setFundLoading] = useState(false);
  const [fundError, setFundError] = useState(null);

  // Sizing
  const [sizingData, setSizingData] = useState(null);
  const [sizingLoading, setSizingLoading] = useState(false);
  const [sizingError, setSizingError] = useState(null);

  const chartContainerRef = useRef(null);

  // Resolve the active timeframe config
  const tfConfig = useMemo(
    () => TIMEFRAMES.find((t) => t.key === activeTimeframe) || TIMEFRAMES[2],
    [activeTimeframe]
  );

  // Load market history
  const loadHistory = useCallback(
    async (sym, tf) => {
      const config = TIMEFRAMES.find((t) => t.key === tf) || TIMEFRAMES[2];
      const startDate = subtractDays(config.days);
      setHistoryLoading(true);
      setHistoryError(null);
      try {
        const data = await fetchMarketHistory(sym, config.interval, startDate);
        setHistoryData(data);
      } catch (err) {
        setHistoryError(err.message || "تعذر تحميل بيانات السوق");
        setHistoryData(null);
      } finally {
        setHistoryLoading(false);
      }
    },
    []
  );

  // Load signal leaders
  const loadSignal = useCallback(async () => {
    setSignalLoading(true);
    setSignalError(null);
    try {
      const data = await fetchRankingLeaders(50);
      setSignalData(data);
    } catch (err) {
      setSignalError(err.message || "تعذر تحميل الإشارة");
    } finally {
      setSignalLoading(false);
    }
  }, []);

  // Load macro
  const loadMacro = useCallback(async () => {
    setMacroLoading(true);
    setMacroError(null);
    try {
      const data = await fetchMacroCalendar();
      setMacroData(data);
    } catch (err) {
      setMacroError(err.message || "تعذر تحميل البيانات الكلية");
    } finally {
      setMacroLoading(false);
    }
  }, []);

  // Load fundamentals
  const loadFundamentals = useCallback(async (sym) => {
    setFundLoading(true);
    setFundError(null);
    setFundData(null);
    try {
      const data = await fetchFundamentals(sym);
      setFundData(data);
    } catch (err) {
      setFundError(err.message || "تعذر تحميل الأساسيات");
    } finally {
      setFundLoading(false);
    }
  }, []);

  // Load Kelly sizing
  const loadSizing = useCallback(async () => {
    setSizingLoading(true);
    setSizingError(null);
    try {
      const data = await calculateKelly(0.55, 2.0, 1.0, 100000);
      setSizingData(data);
    } catch (err) {
      // Fallback to static calculation
      setSizingData({ kelly_fraction: 32.5 }); // Kelly = 55% - 45%/2 = 32.5% → half=16.25%
    } finally {
      setSizingLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadHistory(symbol, activeTimeframe);
    loadSignal();
    loadMacro();
    loadFundamentals(symbol);
    loadSizing();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // When symbol changes
  useEffect(() => {
    loadHistory(symbol, activeTimeframe);
    loadFundamentals(symbol);
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  // When timeframe changes
  useEffect(() => {
    loadHistory(symbol, activeTimeframe);
  }, [activeTimeframe]); // eslint-disable-line react-hooks/exhaustive-deps

  // Chart rendering
  useTradeChart(chartContainerRef, historyData, historyLoading);

  // Handlers
  const handleInputKeyDown = useCallback(
    (e) => {
      if (e.key === "Enter") {
        const s = inputVal.trim().toUpperCase();
        if (s) {
          setSymbol(s);
        }
      }
    },
    [inputVal]
  );

  const handleQuickSymbol = useCallback((sym) => {
    setSymbol(sym);
    setInputVal(sym);
  }, []);

  const handleTimeframe = useCallback((key) => {
    setActiveTimeframe(key);
  }, []);

  const hasChartData = Boolean(historyData?.items?.length);

  return (
    <>
      {/* Keyframe animations injected once */}
      <style>{`
        @keyframes skeleton-shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        .ai-market-page * { box-sizing: border-box; }
        .ai-market-page ::-webkit-scrollbar { width: 4px; }
        .ai-market-page ::-webkit-scrollbar-track { background: transparent; }
        .ai-market-page ::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.2); border-radius: 2px; }
        .ai-market-page input:focus { outline: 1px solid var(--tv-accent, #60a5fa); }
      `}</style>

      <div className="ai-market-page" style={S.page}>

        {/* ── Toolbar ─────────────────────────────────────────────────── */}
        <div style={S.toolbar}>
          {/* Symbol input */}
          <input
            type="text"
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value.toUpperCase())}
            onKeyDown={handleInputKeyDown}
            placeholder="AAPL"
            style={S.symbolInput}
            aria-label="رمز السهم"
          />

          {/* Quick symbol buttons */}
          {QUICK_SYMBOLS.map((sym) => (
            <button
              key={sym}
              type="button"
              style={S.quickBtn(symbol === sym)}
              onClick={() => handleQuickSymbol(sym)}
            >
              {sym}
            </button>
          ))}

          <div style={S.timeframeDivider} />

          {/* Timeframe tabs */}
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.key}
              type="button"
              style={S.tfBtn(activeTimeframe === tf.key)}
              onClick={() => handleTimeframe(tf.key)}
            >
              {tf.label}
            </button>
          ))}

          {/* Symbol badge */}
          <div style={{ marginRight: "auto", display: "flex", alignItems: "center", gap: "8px" }}>
            <span
              style={{
                fontSize: "16px",
                fontWeight: "700",
                color: "var(--tv-accent, #60a5fa)",
                letterSpacing: "1px",
                direction: "ltr",
              }}
            >
              {symbol}
            </span>
            <span
              style={{
                fontSize: "11px",
                color: "#64748b",
                background: "rgba(96,165,250,0.08)",
                padding: "2px 8px",
                borderRadius: "4px",
              }}
            >
              {tfConfig.label}
            </span>
          </div>
        </div>

        {/* ── Chart Panel ─────────────────────────────────────────────── */}
        <div style={S.chartPanel}>
          <div style={S.chartHeader}>
            <h2 style={S.chartTitle}>{symbol} — الشارت التاريخي</h2>
            <p style={S.chartSubtitle}>
              OHLCV · {tfConfig.label} · بيانات يومية · مشغّل بالذكاء الاصطناعي
            </p>
          </div>

          {/* Quote strip */}
          <QuoteCard
            symbol={symbol}
            historyData={historyData}
            historyLoading={historyLoading}
            historyError={historyError}
          />

          {/* Chart canvas */}
          <div style={{ ...S.chartContainer, height: `${CHART_HEIGHT}px` }}>
            <div
              ref={chartContainerRef}
              style={{ ...S.chartCanvas, height: "100%" }}
            />
            <ChartOverlay loading={historyLoading} hasData={hasChartData} />
          </div>

          {/* Chart error */}
          {historyError && !historyLoading && (
            <div style={{ padding: "10px 20px" }}>
              <SectionError message={historyError} />
            </div>
          )}

          {/* OHLCV summary strip */}
          {hasChartData && !historyLoading && (() => {
            const items = historyData.items;
            const last = items[items.length - 1];
            return (
              <div
                style={{
                  display: "flex",
                  gap: "20px",
                  padding: "10px 20px",
                  borderTop: "1px solid var(--color-border, rgba(148,163,184,0.08))",
                  fontSize: "12px",
                  color: "#94a3b8",
                  direction: "ltr",
                  flexWrap: "wrap",
                }}
              >
                <span>O: <strong style={{ color: "#f1f5f9" }}>${Number(last.open || 0).toFixed(2)}</strong></span>
                <span>H: <strong style={{ color: "#22c55e" }}>${Number(last.high || 0).toFixed(2)}</strong></span>
                <span>L: <strong style={{ color: "#ef4444" }}>${Number(last.low || 0).toFixed(2)}</strong></span>
                <span>C: <strong style={{ color: "#60a5fa" }}>${Number(last.close || 0).toFixed(2)}</strong></span>
                <span>V: <strong style={{ color: "#f1f5f9" }}>{Number(last.volume || 0).toLocaleString()}</strong></span>
                <span style={{ marginRight: "auto", color: "#475569" }}>{last.datetime?.slice(0, 10)}</span>
              </div>
            );
          })()}
        </div>

        {/* ── AI Intelligence Side Panel ───────────────────────────────── */}
        <div style={S.sidePanel}>

          {/* Header */}
          <div
            style={{
              padding: "14px 18px 12px",
              borderBottom: "1px solid var(--color-border, rgba(148,163,184,0.12))",
              background: "rgba(96,165,250,0.04)",
            }}
          >
            <div style={{ fontSize: "13px", fontWeight: "700", color: "#60a5fa", letterSpacing: "0.5px" }}>
              ذكاء السوق
            </div>
            <div style={{ fontSize: "11px", color: "#64748b", marginTop: "2px" }}>
              تحليل متكامل · {symbol}
            </div>
          </div>

          {/* Signal */}
          <SignalCard
            symbol={symbol}
            loading={signalLoading}
            error={signalError}
            data={signalData}
          />

          {/* Macro */}
          <MacroCard
            loading={macroLoading}
            error={macroError}
            data={macroData}
          />

          {/* Fundamentals */}
          <FundamentalsCard
            loading={fundLoading}
            error={fundError}
            data={fundData}
          />

          {/* Position Sizing */}
          <SizingCard
            loading={sizingLoading}
            error={sizingError}
            data={sizingData}
          />

          {/* Footer note */}
          <div
            style={{
              padding: "12px 18px",
              fontSize: "10px",
              color: "#334155",
              lineHeight: "1.6",
            }}
          >
            هذه الأداة مخصصة للأغراض التعليمية والبحثية فقط. لا تمثل نصيحة استثمارية.
          </div>
        </div>
      </div>
    </>
  );
}
