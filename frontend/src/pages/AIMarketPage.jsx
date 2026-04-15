/**
 * AIMarketPage v2 — محطة السوق بالذكاء الاصطناعي
 * شارت TradingView الاحترافي + لوحة تحليل AI كاملة
 */
import { useState, useEffect, useCallback, useRef } from "react";
import TradingViewWidget, { normalizeSymbol } from "../components/charts/TradingViewWidget";
import {
  fetchSymbolSignal,
  fetchMacroCalendar,
  fetchFundamentals,
  calculateKelly,
  fetchQuoteSnapshot,
} from "../api/intelligence";

// ─── Constants ──────────────────────────────────────────────────────────────
const QUICK_SYMBOLS = [
  { sym: "AAPL",  label: "آبل",      icon: "🍎" },
  { sym: "MSFT",  label: "مايكروسوفت", icon: "🪟" },
  { sym: "NVDA",  label: "إنفيديا",  icon: "🎮" },
  { sym: "TSLA",  label: "تسلا",     icon: "⚡" },
  { sym: "SPY",   label: "S&P 500",  icon: "📈" },
  { sym: "META",  label: "ميتا",     icon: "👓" },
  { sym: "GOOGL", label: "جوجل",     icon: "🔍" },
  { sym: "AMZN",  label: "أمازون",   icon: "📦" },
];

const INTERVALS = [
  { key: "1",   label: "1د" },
  { key: "5",   label: "5د" },
  { key: "15",  label: "15د" },
  { key: "60",  label: "ساعة" },
  { key: "D",   label: "يوم" },
  { key: "W",   label: "أسبوع" },
  { key: "M",   label: "شهر" },
];

const CHART_STYLES = [
  { key: "1", label: "شموع" },
  { key: "2", label: "بارات" },
  { key: "3", label: "خط" },
  { key: "8", label: "Heikin Ashi" },
];

// ─── Styles ─────────────────────────────────────────────────────────────────
const S = {
  page: {
    minHeight: "100vh",
    background: "#020617",
    color: "#f1f5f9",
    fontFamily: "'Inter', 'Cairo', sans-serif",
    direction: "rtl",
  },
  header: {
    background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    borderBottom: "1px solid #1e293b",
    padding: "12px 20px",
    display: "flex",
    alignItems: "center",
    gap: "16px",
    flexWrap: "wrap",
  },
  logo: {
    fontSize: "18px",
    fontWeight: "700",
    color: "#3b82f6",
    display: "flex",
    alignItems: "center",
    gap: "8px",
    whiteSpace: "nowrap",
  },
  searchBox: {
    display: "flex",
    alignItems: "center",
    background: "#1e293b",
    border: "1px solid #334155",
    borderRadius: "8px",
    padding: "6px 12px",
    gap: "8px",
    flex: 1,
    maxWidth: "300px",
  },
  searchInput: {
    background: "none",
    border: "none",
    outline: "none",
    color: "#f1f5f9",
    fontSize: "14px",
    width: "100%",
    textAlign: "right",
  },
  quickBtn: (active) => ({
    padding: "5px 12px",
    borderRadius: "20px",
    border: `1px solid ${active ? "#3b82f6" : "#334155"}`,
    background: active ? "#1d4ed8" : "#1e293b",
    color: active ? "#fff" : "#94a3b8",
    cursor: "pointer",
    fontSize: "12px",
    fontWeight: active ? "600" : "400",
    display: "flex",
    alignItems: "center",
    gap: "4px",
    transition: "all 0.2s",
    whiteSpace: "nowrap",
  }),
  body: {
    display: "grid",
    gridTemplateColumns: "1fr 340px",
    gap: "0",
    height: "calc(100vh - 130px)",
  },
  chartSection: {
    display: "flex",
    flexDirection: "column",
    borderLeft: "1px solid #1e293b",
  },
  chartToolbar: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "8px 16px",
    background: "#0f172a",
    borderBottom: "1px solid #1e293b",
    flexWrap: "wrap",
  },
  intervalBtn: (active) => ({
    padding: "4px 10px",
    borderRadius: "6px",
    border: `1px solid ${active ? "#3b82f6" : "#334155"}`,
    background: active ? "#1d4ed820" : "transparent",
    color: active ? "#60a5fa" : "#64748b",
    cursor: "pointer",
    fontSize: "12px",
    fontWeight: active ? "600" : "400",
    transition: "all 0.15s",
  }),
  styleBtn: (active) => ({
    padding: "4px 8px",
    borderRadius: "6px",
    border: `1px solid ${active ? "#8b5cf6" : "#334155"}`,
    background: active ? "#7c3aed20" : "transparent",
    color: active ? "#a78bfa" : "#64748b",
    cursor: "pointer",
    fontSize: "11px",
    transition: "all 0.15s",
  }),
  chartWrapper: {
    flex: 1,
    minHeight: 0,
  },
  sidebar: {
    background: "#0f172a",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: "1px",
  },
  card: {
    background: "#0f172a",
    borderBottom: "1px solid #1e293b",
    padding: "16px",
  },
  cardTitle: {
    fontSize: "11px",
    fontWeight: "700",
    color: "#64748b",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    marginBottom: "12px",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  },
  priceDisplay: {
    fontSize: "28px",
    fontWeight: "700",
    color: "#f1f5f9",
    lineHeight: 1.2,
  },
  changeDisplay: (positive) => ({
    fontSize: "14px",
    fontWeight: "600",
    color: positive ? "#22c55e" : "#ef4444",
    display: "flex",
    alignItems: "center",
    gap: "4px",
  }),
  signalBadge: (score) => {
    let bg, color;
    if (score >= 65) { bg = "#14532d"; color = "#22c55e"; }
    else if (score <= 35) { bg = "#7f1d1d"; color = "#ef4444"; }
    else { bg = "#78350f"; color = "#f59e0b"; }
    return {
      display: "inline-flex", alignItems: "center", gap: "6px",
      padding: "6px 14px", borderRadius: "20px",
      background: bg, color, fontWeight: "700", fontSize: "15px",
    };
  },
  scoreBar: (score) => ({
    height: "6px",
    borderRadius: "3px",
    background: `linear-gradient(90deg, 
      ${score >= 65 ? "#22c55e" : score <= 35 ? "#ef4444" : "#f59e0b"} ${score}%, 
      #1e293b ${score}%)`,
    marginTop: "6px",
  }),
  metaRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "5px 0",
    borderBottom: "1px solid #0f172a",
    fontSize: "13px",
  },
  metaLabel: { color: "#64748b" },
  metaValue: { color: "#e2e8f0", fontWeight: "500" },
  macroChip: (regime) => {
    const isOn = String(regime||"").includes("risk_on");
    const isOff = String(regime||"").includes("risk_off");
    return {
      display: "inline-flex", alignItems: "center", gap: "6px",
      padding: "5px 12px", borderRadius: "20px", fontSize: "13px", fontWeight: "600",
      background: isOn ? "#14532d" : isOff ? "#7f1d1d" : "#1e293b",
      color: isOn ? "#22c55e" : isOff ? "#ef4444" : "#f59e0b",
    };
  },
  indicator: {
    display: "flex",
    justifyContent: "space-between",
    padding: "4px 0",
    fontSize: "12px",
    borderBottom: "1px solid #1e293b",
  },
  loaderDot: {
    display: "inline-block",
    width: "8px", height: "8px", borderRadius: "50%",
    background: "#3b82f6",
    animation: "pulse 1s infinite",
  },
  refreshBtn: {
    marginRight: "auto",
    padding: "3px 8px",
    borderRadius: "5px",
    border: "1px solid #334155",
    background: "transparent",
    color: "#64748b",
    cursor: "pointer",
    fontSize: "11px",
  },
  symbolDisplay: {
    display: "flex",
    alignItems: "baseline",
    gap: "8px",
  },
  currentSymbol: {
    fontSize: "22px",
    fontWeight: "800",
    color: "#f1f5f9",
  },
  currentName: {
    fontSize: "12px",
    color: "#64748b",
  },
};

// ─── Helper functions ────────────────────────────────────────────────────────
function fmt(v, d = 2) {
  if (v == null || isNaN(Number(v))) return "—";
  return Number(v).toFixed(d);
}
function fmtBig(v) {
  if (v == null || isNaN(Number(v))) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1e12) return `$${(n/1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9)  return `$${(n/1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6)  return `$${(n/1e6).toFixed(2)}M`;
  return `$${n.toFixed(2)}`;
}
function signalText(score) {
  if (score == null) return "—";
  if (score >= 65) return "شراء قوي 🟢";
  if (score >= 55) return "شراء 🟩";
  if (score <= 35) return "بيع قوي 🔴";
  if (score <= 45) return "بيع 🟥";
  return "محايد 🟡";
}
function regimeLabel(r) {
  if (!r) return "—";
  const s = String(r).toLowerCase();
  if (s.includes("risk_on"))  return "توسعي 🟢";
  if (s.includes("risk_off")) return "انكماشي 🔴";
  return "محايد 🟡";
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function QuoteCard({ symbol, quote, signal, loading }) {
  const pos = (quote?.change_pct ?? 0) >= 0;
  return (
    <div style={S.card}>
      <div style={S.cardTitle}>
        <span>💹</span> السعر الحالي
        {loading && <span style={S.loaderDot} />}
      </div>
      <div style={S.symbolDisplay}>
        <span style={S.currentSymbol}>{symbol}</span>
        {quote?.name && <span style={S.currentName}>{quote.name}</span>}
      </div>
      <div style={{ ...S.priceDisplay, marginTop: "8px" }}>
        ${fmt(quote?.price)}
      </div>
      <div style={{ ...S.changeDisplay(pos), marginTop: "4px" }}>
        {pos ? "▲" : "▼"} {fmt(Math.abs(quote?.change_pct))}%
        <span style={{ color: "#64748b", fontWeight: "400", fontSize: "12px", marginRight: "4px" }}>
          ({pos ? "+" : ""}{fmt(quote?.change)})
        </span>
      </div>
      {quote && (
        <div style={{ marginTop: "10px" }}>
          {[
            ["الافتتاح", `$${fmt(quote.open)}`],
            ["الأعلى",  `$${fmt(quote.high)}`],
            ["الأدنى",  `$${fmt(quote.low)}`],
            ["الحجم",   Number(quote.volume||0).toLocaleString()],
          ].map(([k,v]) => (
            <div key={k} style={S.metaRow}>
              <span style={S.metaLabel}>{k}</span>
              <span style={S.metaValue}>{v}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SignalCard({ signal, loading }) {
  const score = signal?.score ?? 50;
  return (
    <div style={S.card}>
      <div style={S.cardTitle}><span>🤖</span> إشارة الذكاء الاصطناعي</div>
      {loading ? (
        <div style={{ color: "#64748b", fontSize: "13px" }}>جاري التحليل...</div>
      ) : signal ? (
        <>
          <div style={{ marginBottom: "10px" }}>
            <span style={S.signalBadge(score)}>{signalText(score)}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "#64748b", marginBottom: "4px" }}>
            <span>قوة الإشارة</span>
            <span style={{ color: "#f1f5f9", fontWeight: "600" }}>{score}/100</span>
          </div>
          <div style={S.scoreBar(score)} />
          {signal.change_pct != null && (
            <div style={{ marginTop: "10px", fontSize: "12px", color: "#94a3b8" }}>
              التغيّر اليوم: <strong style={{ color: signal.change_pct >= 0 ? "#22c55e" : "#ef4444" }}>
                {signal.change_pct >= 0 ? "+" : ""}{fmt(signal.change_pct)}%
              </strong>
            </div>
          )}
        </>
      ) : (
        <div style={{ color: "#64748b", fontSize: "13px" }}>لا توجد بيانات</div>
      )}
    </div>
  );
}

function MacroCard({ macro, loading, onRefresh }) {
  return (
    <div style={S.card}>
      <div style={S.cardTitle}>
        <span>🌍</span> البيئة الاقتصادية
        <button style={S.refreshBtn} onClick={onRefresh} title="تحديث">↻</button>
      </div>
      {loading ? (
        <div style={{ color: "#64748b", fontSize: "13px" }}>جاري التحميل...</div>
      ) : macro ? (
        <>
          <div style={{ marginBottom: "10px" }}>
            <span style={S.macroChip(macro.regime)}>{regimeLabel(macro.regime)}</span>
          </div>
          {macro.score != null && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "#64748b", marginBottom: "4px" }}>
                <span>درجة الاقتصاد</span>
                <span style={{ color: "#f1f5f9", fontWeight: "600" }}>{fmt(macro.score, 1)}/100</span>
              </div>
              <div style={S.scoreBar(macro.score)} />
            </>
          )}
          {macro.indicators && macro.indicators.length > 0 && (
            <div style={{ marginTop: "10px" }}>
              {macro.indicators.slice(0, 4).map((ind) => (
                <div key={ind.name} style={S.indicator}>
                  <span style={{ color: "#64748b" }}>{ind.label || ind.name}</span>
                  <span style={{ color: "#e2e8f0" }}>{fmt(ind.value, ind.decimals ?? 2)}{ind.unit || ""}</span>
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <div style={{ color: "#64748b", fontSize: "13px" }}>غير متاح</div>
      )}
    </div>
  );
}

function FundamentalsCard({ fund, loading }) {
  return (
    <div style={S.card}>
      <div style={S.cardTitle}><span>📊</span> الأساسيات المالية</div>
      {loading ? (
        <div style={{ color: "#64748b", fontSize: "13px" }}>جاري التحميل...</div>
      ) : fund && !fund.error ? (
        <div>
          {[
            ["المبيعات (سنوي)", fmtBig(fund.revenue_ttm)],
            ["صافي الربح",      fmtBig(fund.net_income_ttm)],
            ["EPS",             fund.eps_ttm != null ? `$${fmt(fund.eps_ttm)}` : "—"],
            ["الديون/حقوق",     fund.debt_to_equity != null ? fmt(fund.debt_to_equity) : "—"],
          ].map(([k,v]) => (
            <div key={k} style={S.metaRow}>
              <span style={S.metaLabel}>{k}</span>
              <span style={S.metaValue}>{v}</span>
            </div>
          ))}
          {fund.ticker && (
            <div style={{ marginTop: "8px", fontSize: "11px", color: "#334155" }}>
              المصدر: SEC EDGAR
            </div>
          )}
        </div>
      ) : (
        <div style={{ color: "#64748b", fontSize: "13px" }}>
          {fund?.error === "ETF_OR_NO_DATA" ? "ETF — لا توجد بيانات EDGAR" : "لا توجد بيانات"}
        </div>
      )}
    </div>
  );
}

function KellyCard({ symbol, quote }) {
  const [winRate, setWinRate] = useState(55);
  const [avgWin,  setAvgWin]  = useState(2.5);
  const [avgLoss, setAvgLoss] = useState(1.0);
  const [capital, setCapital] = useState(10000);
  const [result,  setResult]  = useState(null);
  const [loading, setLoading] = useState(false);

  const calculate = useCallback(async () => {
    setLoading(true);
    try {
      const res = await calculateKelly(winRate / 100, avgWin, avgLoss, capital);
      setResult(res);
    } catch { setResult(null); }
    finally { setLoading(false); }
  }, [winRate, avgWin, avgLoss, capital, quote]);

  const inputStyle = {
    background: "#1e293b", border: "1px solid #334155", borderRadius: "6px",
    color: "#f1f5f9", padding: "4px 8px", fontSize: "12px", width: "70px",
    textAlign: "center", outline: "none",
  };
  const labelStyle = { fontSize: "11px", color: "#64748b" };

  return (
    <div style={S.card}>
      <div style={S.cardTitle}><span>📐</span> حجم الصفقة (Kelly)</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "10px" }}>
        {[
          ["نسبة الفوز %", winRate, setWinRate],
          ["متوسط الربح %", avgWin, setAvgWin],
          ["متوسط الخسارة %", avgLoss, setAvgLoss],
          ["رأس المال $", capital, setCapital],
        ].map(([lbl, val, setter]) => (
          <div key={lbl} style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
            <span style={labelStyle}>{lbl}</span>
            <input
              type="number"
              value={val}
              onChange={e => setter(Number(e.target.value))}
              style={inputStyle}
            />
          </div>
        ))}
      </div>
      <button
        onClick={calculate}
        disabled={loading}
        style={{
          width: "100%", padding: "8px", borderRadius: "6px",
          background: loading ? "#334155" : "#1d4ed8",
          color: "#fff", border: "none", cursor: loading ? "not-allowed" : "pointer",
          fontSize: "13px", fontWeight: "600",
        }}
      >
        {loading ? "جاري الحساب..." : "احسب الحجم"}
      </button>
      {result && (
        <div style={{ marginTop: "10px" }}>
          {[
            ["Kelly %",   `${fmt(result.kelly_pct ?? result.half_kelly_pct)}%`],
            ["عدد الأسهم", result.shares ?? "—"],
            ["المبلغ المقترح", result.position_size_usd ? `$${fmt(result.position_size_usd)}` : "—"],
          ].map(([k,v]) => (
            <div key={k} style={S.metaRow}>
              <span style={S.metaLabel}>{k}</span>
              <span style={{ ...S.metaValue, color: "#22c55e" }}>{v}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────
export default function AIMarketPage() {
  const [symbol,   setSymbol]   = useState("AAPL");
  const [search,   setSearch]   = useState("");
  const [interval, setInterval] = useState("D");
  const [chartStyle, setChartStyle] = useState("1");

  const [quote,    setQuote]    = useState(null);
  const [signal,   setSignal]   = useState(null);
  const [macro,    setMacro]    = useState(null);
  const [fund,     setFund]     = useState(null);

  const [quoteLoading,  setQuoteLoading]  = useState(false);
  const [signalLoading, setSignalLoading] = useState(false);
  const [macroLoading,  setMacroLoading]  = useState(false);
  const [fundLoading,   setFundLoading]   = useState(false);

  const loadQuoteAndSignal = useCallback(async (sym) => {
    setQuoteLoading(true);
    setSignalLoading(true);
    try {
      const [snap, sig] = await Promise.all([
        fetchQuoteSnapshot(sym).catch(() => null),
        fetchSymbolSignal(sym).catch(() => null),
      ]);
      setQuote(snap?.quote ?? snap);
      setSignal(sig);
    } finally {
      setQuoteLoading(false);
      setSignalLoading(false);
    }
  }, []);

  const loadMacro = useCallback(async () => {
    setMacroLoading(true);
    try {
      const m = await fetchMacroCalendar().catch(() => null);
      setMacro(m);
    } finally { setMacroLoading(false); }
  }, []);

  const loadFund = useCallback(async (sym) => {
    setFundLoading(true);
    try {
      const f = await fetchFundamentals(sym).catch(() => null);
      setFund(f);
    } finally { setFundLoading(false); }
  }, []);

  const selectSymbol = useCallback((sym) => {
    setSymbol(sym);
    setSearch("");
    loadQuoteAndSignal(sym);
    loadFund(sym);
  }, [loadQuoteAndSignal, loadFund]);

  // Initial load
  useEffect(() => {
    loadQuoteAndSignal(symbol);
    loadMacro();
    loadFund(symbol);
  }, []);

  // Auto-refresh quote every 60s
  useEffect(() => {
    const id = setInterval(() => loadQuoteAndSignal(symbol), 60_000);
    return () => clearInterval(id);
  }, [symbol, loadQuoteAndSignal]);

  const handleSearch = (e) => {
    if (e.key === "Enter" && search.trim()) {
      selectSymbol(search.trim().toUpperCase());
    }
  };

  const tvSymbol = normalizeSymbol(symbol);

  return (
    <div style={S.page}>
      {/* Header */}
      <div style={S.header}>
        <div style={S.logo}>
          <span>📡</span>
          <span>محطة السوق</span>
        </div>

        {/* Search */}
        <div style={S.searchBox}>
          <span style={{ color: "#64748b", fontSize: "14px" }}>🔍</span>
          <input
            style={S.searchInput}
            placeholder="ابحث عن رمز... (AAPL، TSLA...)"
            value={search}
            onChange={e => setSearch(e.target.value.toUpperCase())}
            onKeyDown={handleSearch}
          />
        </div>

        {/* Quick symbols */}
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          {QUICK_SYMBOLS.map(({ sym, label, icon }) => (
            <button
              key={sym}
              style={S.quickBtn(symbol === sym)}
              onClick={() => selectSymbol(sym)}
            >
              {icon} {sym}
            </button>
          ))}
        </div>
      </div>

      {/* Body */}
      <div style={S.body}>
        {/* Chart Section */}
        <div style={S.chartSection}>
          {/* Chart Toolbar */}
          <div style={S.chartToolbar}>
            <span style={{ fontSize: "13px", fontWeight: "700", color: "#94a3b8" }}>
              {tvSymbol}
            </span>
            <span style={{ color: "#334155" }}>|</span>

            {/* Intervals */}
            {INTERVALS.map(({ key, label }) => (
              <button
                key={key}
                style={S.intervalBtn(interval === key)}
                onClick={() => setInterval(key)}
              >
                {label}
              </button>
            ))}
            <span style={{ color: "#334155" }}>|</span>

            {/* Chart styles */}
            {CHART_STYLES.map(({ key, label }) => (
              <button
                key={key}
                style={S.styleBtn(chartStyle === key)}
                onClick={() => setChartStyle(key)}
              >
                {label}
              </button>
            ))}

            <span style={{ marginRight: "auto", fontSize: "11px", color: "#334155" }}>
              Powered by TradingView
            </span>
          </div>

          {/* TradingView Chart */}
          <div style={S.chartWrapper}>
            <TradingViewWidget
              symbol={tvSymbol}
              interval={interval}
              style={chartStyle}
              height={window.innerHeight - 200}
              showToolbar={true}
              showVolume={true}
              locale="ar_AE"
            />
          </div>
        </div>

        {/* Sidebar */}
        <div style={S.sidebar}>
          <QuoteCard
            symbol={symbol}
            quote={quote}
            signal={signal}
            loading={quoteLoading}
          />
          <SignalCard
            signal={signal}
            loading={signalLoading}
          />
          <MacroCard
            macro={macro}
            loading={macroLoading}
            onRefresh={loadMacro}
          />
          <FundamentalsCard
            fund={fund}
            loading={fundLoading}
          />
          <KellyCard
            symbol={symbol}
            quote={quote}
          />
        </div>
      </div>
    </div>
  );
}
