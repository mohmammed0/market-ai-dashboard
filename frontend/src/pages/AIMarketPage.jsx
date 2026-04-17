import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import TradingViewWidget from "../components/charts/TradingViewWidget";
import DecisionPanel from "../components/ui/DecisionPanel";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import PageFrame from "../components/ui/PageFrame";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import SymbolPicker from "../components/ui/SymbolPicker";
import { fetchFundamentals, fetchMacroCalendar, fetchQuoteSnapshot, fetchSymbolSignal } from "../api/intelligence";
import useDecisionSurface from "../hooks/useDecisionSurface";
import { buildRecentDateRange } from "../lib/dateDefaults";
import { useAppData } from "../store/AppDataStore";
import { useWorkspace } from "../lib/useWorkspace";

const DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "SPY", "QQQ"];
const INTERVALS = ["15", "60", "D", "W"];
const CHART_STYLES = [
  { key: "1", label: "شموع" },
  { key: "3", label: "خط" },
  { key: "8", label: "Heikin Ashi" },
];

function normalizeSymbolInput(value) {
  let normalized = String(value || "").trim().toUpperCase();
  if (!normalized) return "";
  if (normalized.endsWith("^") && !normalized.startsWith("^")) {
    normalized = `^${normalized.slice(0, -1)}`;
  }
  if (normalized.startsWith("^") && normalized.split("^").length > 2) {
    normalized = `^${normalized.replaceAll("^", "")}`;
  }
  return normalized;
}

function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return `$${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function number(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

function percent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  const amount = Number(value);
  return `${amount >= 0 ? "+" : ""}${amount.toFixed(2)}%`;
}

function signalTone(signal) {
  const normalized = String(signal || "").trim().toUpperCase();
  if (normalized === "BUY" || normalized === "BULLISH") return "positive";
  if (normalized === "SELL" || normalized === "BEARISH") return "negative";
  if (normalized === "HOLD" || normalized === "NEUTRAL") return "warning";
  return "neutral";
}

function quoteTone(changePct) {
  return Number(changePct || 0) >= 0 ? "positive" : "negative";
}

function compactDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("ar-SA", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

function SignalHero({ symbol, signal, quote, loading }) {
  const activeSignal = signal?.signal || "HOLD";
  const signalPrice = signal?.price ?? quote?.price ?? quote?.current_price;
  const changePct = quote?.change_pct ?? quote?.day_change_pct ?? 0;
  const confidence = signal?.confidence ?? signal?.score ?? 0;

  if (loading) {
    return (
      <div className="analysis-hero-card">
        <LoadingSkeleton lines={5} />
      </div>
    );
  }

  return (
    <div className="analysis-hero-card">
      <div className="analysis-hero-topline">
        <div>
          <span className="analysis-hero-kicker">AI Signal Surface</span>
          <h2>{symbol}</h2>
        </div>
        <StatusBadge label={activeSignal} tone={signalTone(activeSignal)} />
      </div>

      <div className="analysis-hero-main">
        <div>
          <div className="analysis-hero-price">{money(signalPrice)}</div>
          <div className={`analysis-hero-change ${Number(changePct || 0) >= 0 ? "quote-positive" : "quote-negative"}`}>{percent(changePct)}</div>
        </div>
        <div className="analysis-hero-metrics">
          <div>
            <span>الثقة</span>
            <strong>{number(confidence, 0)}%</strong>
          </div>
          <div>
            <span>النتيجة</span>
            <strong>{number(signal?.score ?? confidence, 0)}</strong>
          </div>
          <div>
            <span>الوضع</span>
            <strong>{signal?.mode || "ensemble"}</strong>
          </div>
        </div>
      </div>

      <p className="analysis-hero-reasoning">
        {signal?.reasoning || "الإشارة الحالية مأخوذة من العقد canonical على الباك إند. ستظهر الأسباب هنا عندما تتوفر طبقة الشرح."}
      </p>
    </div>
  );
}

function QuoteBoard({ quotePayload, loading }) {
  if (loading) {
    return <LoadingSkeleton lines={5} />;
  }

  const metadata = quotePayload?.metadata || {};
  const quote = quotePayload?.quote || {};

  return (
    <div className="analysis-mini-grid">
      <MetricCard label="السعر" value={money(quote?.price)} detail={quote?.exchange || metadata?.exchange || "—"} tone="accent" />
      <MetricCard label="التغير اليومي" value={percent(quote?.change_pct)} detail={money(quote?.change)} tone={quoteTone(quote?.change_pct)} />
      <MetricCard label="الحجم" value={quote?.volume != null ? Number(quote.volume).toLocaleString("en-US") : "—"} detail="Volume" />
      <MetricCard label="القيمة السوقية" value={quote?.market_cap != null ? `$${Number(quote.market_cap).toLocaleString("en-US")}` : "—"} detail="Market Cap" />
      <MetricCard label="الرمز" value={quotePayload?.symbol || "—"} detail={metadata?.security_name || quote?.security_name || "—"} />
      <MetricCard label="آخر تحديث" value={compactDate(quote?.fetched_at || quotePayload?.history?.generated_at)} detail="Snapshot" />
    </div>
  );
}

function FundamentalsBoard({ fundamentals, loading }) {
  if (loading) {
    return <LoadingSkeleton lines={5} />;
  }

  if (!fundamentals || fundamentals.error) {
    return <EmptyState title="لا توجد Fundamentals جاهزة" description={fundamentals?.error || "المصدر الحالي لم يرجع بيانات أساسية لهذا الرمز."} />;
  }

  return (
    <div className="analysis-mini-grid">
      <MetricCard label="الشركة" value={fundamentals?.entity_name || fundamentals?.ticker || "—"} detail={fundamentals?.source || "SEC EDGAR"} />
      <MetricCard label="الإيرادات TTM" value={money(fundamentals?.revenue_ttm)} detail="Revenue" tone="accent" />
      <MetricCard label="صافي الدخل TTM" value={money(fundamentals?.net_income_ttm)} detail="Net income" tone={Number(fundamentals?.net_income_ttm || 0) >= 0 ? "positive" : "negative"} />
      <MetricCard label="EPS TTM" value={number(fundamentals?.eps_ttm, 2)} detail="EPS" />
      <MetricCard label="Debt / Equity" value={number(fundamentals?.debt_to_equity, 2)} detail="Leverage" />
      <MetricCard label="تاريخ البيانات" value={fundamentals?.data_date || "—"} detail="Latest filing" />
    </div>
  );
}

function MacroBoard({ macro, loading }) {
  if (loading) {
    return <LoadingSkeleton lines={4} />;
  }

  if (!macro) {
    return <EmptyState title="لا توجد قراءة ماكرو" description="تعذر تحميل طبقة الماكرو الحالية." />;
  }

  return (
    <div className="analysis-macro-board">
      <div className="analysis-macro-hero">
        <div>
          <span className="analysis-hero-kicker">Macro Regime</span>
          <h3>{macro?.macro_regime || "neutral"}</h3>
        </div>
        <StatusBadge label={`${macro?.macro_score ?? 0}/100`} tone={Number(macro?.macro_score || 0) >= 60 ? "positive" : Number(macro?.macro_score || 0) <= 40 ? "negative" : "warning"} />
      </div>
      <div className="analysis-macro-grid">
        <MetricCard label="VIX" value={number(macro?.vix)} detail={macro?.vix_regime || "—"} />
        <MetricCard label="10Y-2Y" value={number(macro?.yield_spread_10y2y, 2)} detail={macro?.yield_curve || "—"} />
        <MetricCard label="Fed Funds" value={number(macro?.fed_funds_rate, 2)} detail="Rate" />
        <MetricCard label="HY Spread" value={number(macro?.hy_spread, 2)} detail={macro?.credit_conditions || "—"} />
      </div>
    </div>
  );
}

export default function AIMarketPage() {
  const { startDate: defaultStartDate, todayIso } = buildRecentDateRange();
  const { data: dashboardLite } = useAppData("dashboardLite");
  const [searchParams, setSearchParams] = useSearchParams();
  const { workspace, activeWatchlist, favoriteSymbols } = useWorkspace();
  const [symbol, setSymbol] = useState("AAPL");
  const [chartInterval, setChartInterval] = useState("D");
  const [chartStyle, setChartStyle] = useState("1");
  const [surfaceLoading, setSurfaceLoading] = useState(true);
  const [surfaceError, setSurfaceError] = useState("");
  const [signalSurface, setSignalSurface] = useState(null);
  const [quotePayload, setQuotePayload] = useState(null);
  const [fundamentals, setFundamentals] = useState(null);
  const [macro, setMacro] = useState(null);
  const dlEnabled = Boolean(dashboardLite?.product_scope?.dl_enabled);

  const { decision, loading: decisionLoading, error: decisionError } = useDecisionSurface({
    symbol,
    startDate: defaultStartDate,
    endDate: todayIso,
    includeDl: dlEnabled,
    enabled: Boolean(symbol),
  });

  useEffect(() => {
    const querySymbol = normalizeSymbolInput(searchParams.get("symbol"));
    if (querySymbol) {
      setSymbol(querySymbol);
      return;
    }
    const workspaceSymbol = normalizeSymbolInput(workspace?.active_symbol || activeWatchlist?.symbols?.[0] || "AAPL");
    setSymbol(workspaceSymbol || "AAPL");
  }, [searchParams, workspace?.active_symbol, activeWatchlist?.symbols]);

  useEffect(() => {
    let active = true;

    async function loadSurface() {
      if (!symbol) return;
      setSurfaceLoading(true);
      setSurfaceError("");
      try {
        const [signalData, quoteData, fundamentalsData, macroData] = await Promise.all([
          fetchSymbolSignal(symbol),
          fetchQuoteSnapshot(symbol),
          fetchFundamentals(symbol).catch((error) => ({ error: error.message || "Fundamentals unavailable" })),
          fetchMacroCalendar().catch(() => null),
        ]);
        if (!active) return;
        setSignalSurface(signalData);
        setQuotePayload(quoteData);
        setFundamentals(fundamentalsData);
        setMacro(macroData);
      } catch (error) {
        if (!active) return;
        setSurfaceError(error.message || "تعذر تحميل طبقة التحليل الحالية.");
      } finally {
        if (active) {
          setSurfaceLoading(false);
        }
      }
    }

    loadSurface().catch(() => {});
    return () => {
      active = false;
    };
  }, [symbol]);

  const quickSymbols = useMemo(() => {
    const scopedSymbols = Array.isArray(dashboardLite?.product_scope?.sample_symbols) && dashboardLite?.product_scope?.sample_symbols.length
      ? dashboardLite.product_scope.sample_symbols
      : DEFAULT_SYMBOLS;
    const seen = new Set();
    const values = [
      symbol,
      ...(favoriteSymbols || []),
      ...((activeWatchlist?.symbols || []).slice(0, 4)),
      ...scopedSymbols,
    ];
    return values.filter((item) => {
      const normalized = normalizeSymbolInput(item);
      if (!normalized || seen.has(normalized)) return false;
      seen.add(normalized);
      return true;
    }).slice(0, 8);
  }, [symbol, favoriteSymbols, activeWatchlist?.symbols, dashboardLite]);

  function updateSymbol(next) {
    const normalized = normalizeSymbolInput(next?.symbol || next);
    if (!normalized) return;
    setSymbol(normalized);
    const params = new URLSearchParams(searchParams);
    params.set("symbol", normalized);
    setSearchParams(params);
  }

  return (
    <PageFrame
      title="محطة التحليل"
      description="سطح قرار احترافي يجمع الإشارة canonical، الشرح، الشارت، والبيانات الأساسية في صفحة واحدة."
      eyebrow="AI Research"
      headerActions={<StatusBadge label={signalSurface?.signal || "HOLD"} tone={signalTone(signalSurface?.signal)} />}
    >
      <ErrorBanner message={surfaceError || decisionError} />

      <section className="analysis-toolbar-card">
        <div className="analysis-toolbar-main">
          <SymbolPicker
            label="اختر السهم"
            value={symbol}
            onChange={setSymbol}
            onSelect={updateSymbol}
            placeholder="ابحث بالرمز أو اسم الشركة"
            helperText="اختيار السهم هنا يحدّث الإشارة والشارت ولوحة القرار معًا."
          />
          <div className="analysis-quick-symbols">
            {quickSymbols.map((item) => (
              <button
                key={item}
                className={`workspace-symbol-chip${item === symbol ? " active" : ""}`}
                type="button"
                onClick={() => updateSymbol(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </section>

      <SignalHero symbol={symbol} signal={signalSurface} quote={quotePayload?.quote} loading={surfaceLoading} />

      <div className="command-grid">
        <SectionCard
          className="col-span-7"
          title="الشارت التنفيذي"
          description="شارت TradingView مع التحكم في الإطار الزمني ونمط العرض."
          action={
            <div className="analysis-chip-row">
              {INTERVALS.map((item) => (
                <button
                  key={item}
                  className={`analysis-chip-btn${chartInterval === item ? " active" : ""}`}
                  type="button"
                  onClick={() => setChartInterval(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          }
        >
          <div className="analysis-chart-card">
            <div className="analysis-chart-toolbar">
              <div className="analysis-chip-row">
                {CHART_STYLES.map((item) => (
                  <button
                    key={item.key}
                    className={`analysis-chip-btn analysis-chip-btn--subtle${chartStyle === item.key ? " active" : ""}`}
                    type="button"
                    onClick={() => setChartStyle(item.key)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <StatusBadge label={quotePayload?.metadata?.security_name || quotePayload?.quote?.security_name || symbol} tone="subtle" dot={false} />
            </div>
            <TradingViewWidget symbol={symbol} interval={chartInterval} style={chartStyle} height={560} />
          </div>
        </SectionCard>

        <DecisionPanel
          className="col-span-5"
          decision={decision}
          loading={decisionLoading}
          error={decisionError}
          title="القرار الحالي"
          description="شرح الموقف الحالي، الأدلة، والعوامل الداعمة أو الضاغطة."
        />

        <SectionCard className="col-span-4" title="ملخص السوق للسهم" description="لقطة السعر الحالية كما وصلت من طبقة السوق.">
          <QuoteBoard quotePayload={quotePayload} loading={surfaceLoading} />
        </SectionCard>

        <SectionCard className="col-span-4" title="البيانات الأساسية" description="ملخص fundamentals الحالي عبر SEC EDGAR عندما يكون متاحًا.">
          <FundamentalsBoard fundamentals={fundamentals} loading={surfaceLoading} />
        </SectionCard>

        <SectionCard className="col-span-4" title="سياق الماكرو" description="قراءة مختصرة للنظام الاقتصادي الحالي وتأثيره على المخاطر.">
          <MacroBoard macro={macro} loading={surfaceLoading} />
        </SectionCard>
      </div>

      {!signalSurface && !surfaceLoading ? (
        <EmptyState
          title="لا توجد إشارة جاهزة"
          description="اختر سهمًا آخر أو تأكد من أن endpoint الإشارة متاح من الباك إند الحالي."
        />
      ) : null}
    </PageFrame>
  );
}
