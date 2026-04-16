/**
 * TradingChart — Unified trading workspace chart using Lightweight Charts v5.
 *
 * Supports two data modes:
 * 1. Decision mode — from decision.analysis.chart_data (daily close + indicators)
 * 2. Terminal mode — from chartData prop (intraday/daily OHLC + volume)
 *
 * Both modes render the decision surface contract:
 * zones, levels, markers from the chart plan.
 *
 * Provenance: All overlays are derived from deterministic analysis.
 * AI overlay is displayed separately in the DecisionPanel.
 */

import { useEffect, useRef, useCallback, useMemo } from "react";
import {
  createChart,
  createSeriesMarkers,
  LineSeries,
  CandlestickSeries,
  HistogramSeries,
  LineStyle,
  CrosshairMode,
} from "lightweight-charts";
import SectionCard from "./SectionCard";
import SummaryStrip from "./SummaryStrip";
import LoadingSkeleton from "./LoadingSkeleton";
import EmptyState from "./EmptyState";


// ---------------------------------------------------------------------------
// Tone → color mapping (matches design system)
// ---------------------------------------------------------------------------

const TONE_COLORS = {
  accent: "#60a5fa",
  positive: "#22c55e",
  negative: "#ef4444",
  warning: "#f59e0b",
  subtle: "#94a3b8",
  info: "#38bdf8",
};

function toneColor(tone) {
  return TONE_COLORS[tone] || TONE_COLORS.subtle;
}

function toneColorAlpha(tone, alpha = 0.15) {
  const hex = toneColor(tone);
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}


// ---------------------------------------------------------------------------
// Time helpers
// ---------------------------------------------------------------------------

function dateToBusinessDay(d) {
  const parts = String(d).slice(0, 10).split("-");
  return { year: +parts[0], month: +parts[1], day: +parts[2] };
}

function datetimeToTimestamp(datetime) {
  const s = String(datetime || "");
  if (s.length <= 10) {
    const d = new Date(s + "T00:00:00Z");
    return Math.floor(d.getTime() / 1000);
  }
  const d = new Date(s);
  return isNaN(d.getTime()) ? 0 : Math.floor(d.getTime() / 1000);
}

function isBusinessDayTime(time) {
  return Boolean(
    time &&
      typeof time === "object" &&
      Number.isFinite(time.year) &&
      Number.isFinite(time.month) &&
      Number.isFinite(time.day),
  );
}

function isValidChartTime(time) {
  if (typeof time === "number") return Number.isFinite(time) && time > 0;
  if (isBusinessDayTime(time)) return true;
  return false;
}

function sortableChartTime(time) {
  if (typeof time === "number") return time;
  if (isBusinessDayTime(time)) {
    return time.year * 10000 + time.month * 100 + time.day;
  }
  return Number.NEGATIVE_INFINITY;
}

function chartTimeKey(time) {
  if (typeof time === "number") return `ts:${time}`;
  if (isBusinessDayTime(time)) return `bd:${time.year}-${time.month}-${time.day}`;
  return "";
}

function sanitizeSeriesData(items) {
  const deduped = new Map();
  for (const item of items || []) {
    if (!item || !isValidChartTime(item.time)) continue;
    deduped.set(chartTimeKey(item.time), item);
  }
  return Array.from(deduped.values()).sort((left, right) => sortableChartTime(left.time) - sortableChartTime(right.time));
}

function sanitizeMarkerData(items) {
  const deduped = new Map();
  for (const item of items || []) {
    if (!item || !isValidChartTime(item.time)) continue;
    const key = chartTimeKey(item.time);
    const existing = deduped.get(key);
    if (!existing) {
      deduped.set(key, item);
      continue;
    }

    const existingText = String(existing.text || "").trim();
    const nextText = String(item.text || "").trim();
    deduped.set(key, {
      ...existing,
      text: [existingText, nextText].filter(Boolean).join(" • ").slice(0, 120),
    });
  }
  return Array.from(deduped.values()).sort((left, right) => sortableChartTime(left.time) - sortableChartTime(right.time));
}


// ---------------------------------------------------------------------------
// Data transformers — Decision mode (daily, close-only)
// ---------------------------------------------------------------------------

function buildDecisionLineData(dates, values) {
  const result = [];
  for (let i = 0; i < dates.length; i++) {
    const val = values[i];
    if (val != null && !isNaN(val)) {
      result.push({ time: dateToBusinessDay(dates[i]), value: Number(val) });
    }
  }
  return sanitizeSeriesData(result);
}


// ---------------------------------------------------------------------------
// Data transformers — Terminal mode (intraday/daily OHLCV)
// ---------------------------------------------------------------------------

function buildTerminalCandleData(items) {
  return sanitizeSeriesData(
    items
    .filter((it) => it.datetime && it.close != null)
    .map((it) => ({
      time: datetimeToTimestamp(it.datetime),
      open: Number(it.open ?? it.close ?? 0),
      high: Number(it.high ?? it.close ?? 0),
      low: Number(it.low ?? it.close ?? 0),
      close: Number(it.close ?? 0),
    })),
  );
}

function buildTerminalLineData(items) {
  return sanitizeSeriesData(
    items
    .filter((it) => it.datetime && (it.close != null || it.price != null))
    .map((it) => ({
      time: datetimeToTimestamp(it.datetime),
      value: Number(it.close ?? it.price ?? 0),
    })),
  );
}

function buildTerminalVolumeData(items) {
  return sanitizeSeriesData(
    items
    .filter((it) => it.datetime && it.volume != null && Number(it.volume) > 0)
    .map((it) => {
      const close = Number(it.close ?? it.price ?? 0);
      const open = Number(it.open ?? close);
      return {
        time: datetimeToTimestamp(it.datetime),
        value: Number(it.volume),
        color: close >= open ? "rgba(34, 197, 94, 0.4)" : "rgba(249, 115, 22, 0.4)",
      };
    }),
  );
}


// ---------------------------------------------------------------------------
// Compare overlay helpers
// ---------------------------------------------------------------------------

const COMPARE_COLORS = ["#a78bfa", "#fb923c", "#2dd4bf", "#f472b6"];

function buildCompareSeriesData(compareSeries, mainItems) {
  if (!compareSeries?.length || !mainItems?.length) return [];
  // Build a time array from main items
  const mainTimes = mainItems
    .filter((it) => it.datetime)
    .map((it) => datetimeToTimestamp(it.datetime));

  return compareSeries.map((cs, idx) => {
    const items = cs.items || [];
    let data;
    if (items.length && items[0]?.datetime) {
      // Items have their own timestamps
      data = sanitizeSeriesData(items
        .filter((it) => it.datetime && it.value != null)
        .map((it) => ({ time: datetimeToTimestamp(it.datetime), value: Number(it.value) })));
    } else {
      // Items are positional — align to main timestamps
      data = sanitizeSeriesData(items
        .map((it, i) => {
          if (i >= mainTimes.length || it.value == null) return null;
          return { time: mainTimes[i], value: Number(it.value) };
        })
        .filter(Boolean));
    }
    return { symbol: cs.symbol || `Compare ${idx + 1}`, data, color: COMPARE_COLORS[idx % COMPARE_COLORS.length] };
  }).filter((cs) => cs.data.length > 0);
}


// ---------------------------------------------------------------------------
// Chart base configuration
// ---------------------------------------------------------------------------

const BASE_CHART_OPTIONS = {
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
    scaleMargins: { top: 0.1, bottom: 0.1 },
  },
  handleScale: { mouseWheel: true, pinch: true },
  handleScroll: { mouseWheel: true, pressedMouseMove: true },
};


// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TradingChart({
  // Data sources (at least one required for chart to render)
  decision,
  chartData: terminalPayload,
  chartPlan: externalChartPlan,

  // UI composition slots
  beforeChart,
  afterChart,
  summaryItems,

  // SectionCard header props
  badge,
  action,

  // Display options
  loading = false,
  className = "",
  title = "مساحة العمل",
  description = "الرسم البياني والمناطق والمستويات.",
  height = 420,
  showVolume: showVolumeOverride,
  emptyTitle = "لا توجد بيانات رسم بيا��ي",
  emptyDescription = "أجرِ التحليل لعرض مساحة العمل.",
}) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef({});

  // -------------------------------------------------------------------------
  // Resolve data sources
  // -------------------------------------------------------------------------
  const decisionChartData = decision?.analysis?.chart_data;
  const resolvedChartPlan = externalChartPlan || decision?.chart_plan || decision?.decision_surface;

  const terminalItems = terminalPayload?.items || [];
  const hasTerminalData = terminalItems.length > 0;
  const hasDecisionData =
    decisionChartData?.dates?.length > 0 && decisionChartData?.close?.length > 0;

  const dataMode = hasTerminalData ? "terminal" : hasDecisionData ? "decision" : null;
  const hasData = dataMode !== null;

  // Terminal-specific flags
  const isTerminalLine =
    terminalPayload?.mode === "line" ||
    (hasTerminalData && !terminalItems.some((it) => it.open != null && it.high != null && it.low != null));
  const hasVolumeData = hasTerminalData && terminalItems.some((it) => Number(it.volume) > 0);
  const showVolume = showVolumeOverride !== undefined ? showVolumeOverride : hasVolumeData;

  // -------------------------------------------------------------------------
  // Build series data (memoized)
  // -------------------------------------------------------------------------

  // Decision mode
  const decisionPriceData = useMemo(() => {
    if (dataMode !== "decision") return [];
    return buildDecisionLineData(decisionChartData.dates, decisionChartData.close);
  }, [dataMode, decisionChartData]);

  const decisionIndicators = useMemo(() => {
    if (dataMode !== "decision") return {};
    const cd = decisionChartData;
    return {
      ma20: cd.ma20?.length ? buildDecisionLineData(cd.dates, cd.ma20) : [],
      ma50: cd.ma50?.length ? buildDecisionLineData(cd.dates, cd.ma50) : [],
      bbUpper: cd.bb_upper?.length ? buildDecisionLineData(cd.dates, cd.bb_upper) : [],
      bbLower: cd.bb_lower?.length ? buildDecisionLineData(cd.dates, cd.bb_lower) : [],
    };
  }, [dataMode, decisionChartData]);

  // Terminal mode
  const terminalPriceData = useMemo(() => {
    if (dataMode !== "terminal") return [];
    return isTerminalLine ? buildTerminalLineData(terminalItems) : buildTerminalCandleData(terminalItems);
  }, [dataMode, isTerminalLine, terminalItems]);

  const terminalVolumeData = useMemo(() => {
    if (dataMode !== "terminal" || !showVolume) return [];
    return buildTerminalVolumeData(terminalItems);
  }, [dataMode, showVolume, terminalItems]);

  // Compare overlays (terminal mode only)
  const terminalCompareData = useMemo(() => {
    if (dataMode !== "terminal") return [];
    return buildCompareSeriesData(terminalPayload?.compare_series, terminalItems);
  }, [dataMode, terminalPayload?.compare_series, terminalItems]);

  // -------------------------------------------------------------------------
  // Chart creation factory
  // -------------------------------------------------------------------------
  const createChartInstance = useCallback(() => {
    if (!containerRef.current) return null;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
      seriesRef.current = {};
    }

    const timeVisible = dataMode === "terminal";

    const chart = createChart(containerRef.current, {
      ...BASE_CHART_OPTIONS,
      width: containerRef.current.clientWidth,
      height,
      timeScale: {
        ...BASE_CHART_OPTIONS.timeScale,
        timeVisible,
      },
      rightPriceScale: {
        ...BASE_CHART_OPTIONS.rightPriceScale,
        scaleMargins: showVolume ? { top: 0.05, bottom: 0.2 } : { top: 0.1, bottom: 0.1 },
      },
    });

    chartRef.current = chart;
    return chart;
  }, [height, dataMode, showVolume]);

  // -------------------------------------------------------------------------
  // Main render effect
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!hasData || !containerRef.current) return;

    const chart = createChartInstance();
    if (!chart) return;

    let priceSeries;

    // === Terminal mode ===
    if (dataMode === "terminal") {
      if (!isTerminalLine && terminalPriceData.length) {
        priceSeries = chart.addSeries(CandlestickSeries, {
          upColor: "#22c55e",
          downColor: "#ef4444",
          borderUpColor: "#22c55e",
          borderDownColor: "#ef4444",
          wickUpColor: "#22c55e",
          wickDownColor: "#ef4444",
          lastValueVisible: true,
          priceLineVisible: true,
        });
        priceSeries.setData(terminalPriceData);
      } else if (terminalPriceData.length) {
        priceSeries = chart.addSeries(LineSeries, {
          color: "#38bdf8",
          lineWidth: 2,
          crosshairMarkerVisible: true,
          crosshairMarkerRadius: 4,
          lastValueVisible: true,
          priceLineVisible: true,
          priceLineColor: "#38bdf8",
          priceLineWidth: 1,
          priceLineStyle: LineStyle.Dotted,
        });
        priceSeries.setData(terminalPriceData);
      }

      // Volume histogram
      if (showVolume && terminalVolumeData.length) {
        const volSeries = chart.addSeries(HistogramSeries, {
          priceFormat: { type: "volume" },
          priceScaleId: "volume",
          lastValueVisible: false,
          priceLineVisible: false,
        });
        chart.priceScale("volume").applyOptions({
          scaleMargins: { top: 0.85, bottom: 0 },
        });
        volSeries.setData(terminalVolumeData);
        seriesRef.current.volume = volSeries;
      }

      // Compare overlays (percentage performance on left axis)
      if (terminalCompareData.length) {
        chart.priceScale("compare").applyOptions({
          position: "left",
          scaleMargins: { top: 0.1, bottom: 0.2 },
          borderColor: "rgba(148, 163, 184, 0.12)",
          autoScale: true,
        });
        seriesRef.current.compare = [];
        for (const cs of terminalCompareData) {
          const cSeries = chart.addSeries(LineSeries, {
            color: cs.color,
            lineWidth: 1.5,
            lineStyle: LineStyle.Solid,
            priceScaleId: "compare",
            lastValueVisible: true,
            priceLineVisible: false,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 3,
            title: cs.symbol,
            priceFormat: { type: "custom", formatter: (p) => `${p.toFixed(1)}%` },
          });
          cSeries.setData(cs.data);
          seriesRef.current.compare.push(cSeries);
        }
      }

    // === Decision mode ===
    } else if (dataMode === "decision") {
      priceSeries = chart.addSeries(LineSeries, {
        color: "#60a5fa",
        lineWidth: 2,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 4,
        lastValueVisible: true,
        priceLineVisible: true,
        priceLineColor: "#60a5fa",
        priceLineWidth: 1,
        priceLineStyle: LineStyle.Dotted,
      });
      priceSeries.setData(decisionPriceData);

      // MA20
      if (decisionIndicators.ma20?.length) {
        const ma20 = chart.addSeries(LineSeries, {
          color: "#34d399",
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          crosshairMarkerVisible: false,
        });
        ma20.setData(decisionIndicators.ma20);
        seriesRef.current.ma20 = ma20;
      }

      // MA50
      if (decisionIndicators.ma50?.length) {
        const ma50 = chart.addSeries(LineSeries, {
          color: "#f59e0b",
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
          crosshairMarkerVisible: false,
        });
        ma50.setData(decisionIndicators.ma50);
        seriesRef.current.ma50 = ma50;
      }

      // Bollinger Bands
      if (decisionIndicators.bbUpper?.length) {
        const bb = chart.addSeries(LineSeries, {
          color: "rgba(148, 163, 184, 0.5)",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          lastValueVisible: false,
          priceLineVisible: false,
          crosshairMarkerVisible: false,
        });
        bb.setData(decisionIndicators.bbUpper);
        seriesRef.current.bbUpper = bb;
      }
      if (decisionIndicators.bbLower?.length) {
        const bb = chart.addSeries(LineSeries, {
          color: "rgba(148, 163, 184, 0.5)",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          lastValueVisible: false,
          priceLineVisible: false,
          crosshairMarkerVisible: false,
        });
        bb.setData(decisionIndicators.bbLower);
        seriesRef.current.bbLower = bb;
      }
    }

    seriesRef.current.price = priceSeries;

    // -------------------------------------------------------------------
    // Decision surface overlays (work in both modes)
    // -------------------------------------------------------------------
    if (priceSeries && resolvedChartPlan) {
      // Price levels (horizontal)
      const levels = resolvedChartPlan.levels || [];
      for (const level of levels) {
        if (level.value == null) continue;
        const color = toneColor(level.tone);
        const style =
          level.kind === "support" || level.kind === "resistance"
            ? LineStyle.Dashed
            : LineStyle.Solid;
        priceSeries.createPriceLine({
          price: level.value,
          color,
          lineWidth: 1,
          lineStyle: style,
          axisLabelVisible: true,
          title: level.label,
        });
      }

      // Markers (signals, news, events)
      const markers = resolvedChartPlan.markers || [];
      if (markers.length) {
        const priceData = dataMode === "terminal" ? terminalPriceData : decisionPriceData;
        const lastTime = priceData[priceData.length - 1]?.time;
        const chartMarkers = [];

        for (const marker of markers) {
          if (!marker.value) continue;
          let time = lastTime;
          if (marker.date) {
            time =
              dataMode === "terminal"
                ? datetimeToTimestamp(marker.date)
                : dateToBusinessDay(marker.date);
          }
          if (!time) continue;

          const isSignal = marker.kind === "signal_marker";
          const isNews = marker.kind === "news_marker";

          chartMarkers.push({
            time,
            position: isSignal ? "belowBar" : "aboveBar",
            color: toneColor(marker.tone),
            shape: isSignal ? "arrowUp" : isNews ? "circle" : "square",
            text: marker.label || "",
            size: isSignal ? 2 : 1,
          });
        }

        if (chartMarkers.length) {
          createSeriesMarkers(priceSeries, sanitizeMarkerData(chartMarkers));
        }
      }
    }

    // -------------------------------------------------------------------
    // Zoom / fit
    // -------------------------------------------------------------------
    chart.timeScale().fitContent();

    const priceData = dataMode === "terminal" ? terminalPriceData : decisionPriceData;
    if (priceData.length > 30) {
      const fromIdx = Math.floor(priceData.length * 0.6);
      try {
        chart.timeScale().setVisibleRange({
          from: priceData[fromIdx].time,
          to: priceData[priceData.length - 1].time,
        });
      } catch {
        /* range may be invalid if data is sparse */
      }
    }

    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        seriesRef.current = {};
      }
    };
  }, [
    hasData,
    dataMode,
    isTerminalLine,
    showVolume,
    decisionPriceData,
    decisionIndicators,
    terminalPriceData,
    terminalVolumeData,
    terminalCompareData,
    resolvedChartPlan,
    createChartInstance,
  ]);

  // Resize handler
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
  }, [hasData]);

  // -------------------------------------------------------------------------
  // Zones / levels detail data
  // -------------------------------------------------------------------------
  const zones = resolvedChartPlan?.zones || [];
  const levelsList = resolvedChartPlan?.levels || [];
  const statusNote = resolvedChartPlan?.note;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <SectionCard
      title={title}
      description={description}
      className={className}
      flush
      action={
        <>
          {badge && <span className="trading-chart-badge">{badge}</span>}
          {action}
        </>
      }
    >
      {loading ? (
        <div style={{ padding: "var(--space-4)" }}>
          <LoadingSkeleton lines={8} />
        </div>
      ) : !hasData ? (
        <div style={{ padding: "var(--space-4)" }}>
          <EmptyState title={emptyTitle} description={emptyDescription} />
        </div>
      ) : (
        <>
          {beforeChart}

          {/* Chart canvas */}
          <div
            ref={containerRef}
            className="trading-chart-container"
            style={{ width: "100%", height: `${height}px` }}
          />

          {/* Zones & Levels strip */}
          {(zones.length > 0 || levelsList.length > 0) && (
            <div className="trading-chart-overlays">
              {zones.map((zone, i) => (
                <div key={`zone-${i}`} className="trading-chart-overlay-item">
                  <span
                    className="trading-chart-overlay-dot"
                    style={{ background: toneColorAlpha(zone.tone, 0.6) }}
                  />
                  <span className="trading-chart-overlay-label">{zone.label}</span>
                  <span className="trading-chart-overlay-value">
                    {zone.low?.toFixed(2)} – {zone.high?.toFixed(2)}
                  </span>
                </div>
              ))}
              {levelsList.map((level, i) => (
                <div key={`level-${i}`} className="trading-chart-overlay-item">
                  <span
                    className="trading-chart-overlay-dot"
                    style={{ background: toneColor(level.tone) }}
                  />
                  <span className="trading-chart-overlay-label">{level.label}</span>
                  <span className="trading-chart-overlay-value">
                    {level.value?.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Status note from chart plan */}
          {statusNote && (
            <div className="trading-chart-status-note">{statusNote}</div>
          )}

          {/* Summary strip */}
          {summaryItems?.length > 0 && (
            <div style={{ padding: "var(--space-3) var(--space-4)" }}>
              <SummaryStrip compact items={summaryItems} />
            </div>
          )}

          {afterChart}
        </>
      )}
    </SectionCard>
  );
}
