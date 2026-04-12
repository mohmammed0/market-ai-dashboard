import { useEffect, useState, useCallback, useRef } from "react";
import { getJson, invalidateJsonCache } from "../api/client";

// ─── helpers ────────────────────────────────────────────────
function fmtLargeNumber(v) {
  const n = Number(v ?? 0);
  if (Math.abs(n) >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(0)}B`;
  if (Math.abs(n) >= 1_000_000)     return `$${(n / 1_000_000).toFixed(0)}M`;
  return `$${n.toLocaleString("en-US")}`;
}

function fmtDebt(v) {
  return `${Number(v ?? 0).toFixed(2)}x`;
}

function fmtEps(v) {
  return `$${Number(v ?? 0).toFixed(2)}`;
}

// ─── quick-pick symbols ──────────────────────────────────────
const QUICK_SYMBOLS = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL"];

// ─── sub-components ─────────────────────────────────────────
function MetricCard({ label, value, sub }) {
  return (
    <div style={{
      background: "var(--tv-elevated)",
      border: "1px solid var(--tv-border)",
      borderRadius: 10,
      padding: "18px 16px",
      display: "flex",
      flexDirection: "column",
      gap: 8,
      minWidth: 0,
      transition: "border-color 0.2s",
    }}
    onMouseEnter={e => e.currentTarget.style.borderColor = "var(--tv-accent)"}
    onMouseLeave={e => e.currentTarget.style.borderColor = "var(--tv-border)"}
    >
      <span style={{ fontSize: 11, color: "var(--tv-text-muted)", lineHeight: 1.4 }}>{label}</span>
      <span style={{ fontSize: 22, fontWeight: 700, color: "var(--tv-text)", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </span>
      {sub && <span style={{ fontSize: 11, color: "var(--tv-text-dim)" }}>{sub}</span>}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div style={{
      background: "var(--tv-elevated)",
      borderRadius: 10,
      padding: "18px 16px",
      display: "flex",
      flexDirection: "column",
      gap: 10,
      animation: "pulse 1.5s ease-in-out infinite",
    }}>
      <div style={{ height: 11, background: "var(--tv-border)", borderRadius: 4, width: "50%" }} />
      <div style={{ height: 22, background: "var(--tv-border)", borderRadius: 4, width: "65%" }} />
    </div>
  );
}

// ─── main component ──────────────────────────────────────────
export default function FundamentalsPage() {
  const [symbol, setSymbol]       = useState("AAPL");
  const [inputVal, setInputVal]   = useState("AAPL");
  const [data, setData]           = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState("");
  const inputRef                  = useRef(null);

  const loadFundamentals = useCallback(async (ticker, fresh = false) => {
    const sym = String(ticker || "AAPL").toUpperCase().trim();
    if (!sym) return;
    if (fresh) invalidateJsonCache(`/api/fundamentals/${sym}`);
    setLoading(true);
    setError("");
    setData(null);
    try {
      const d = await getJson(`/api/fundamentals/${sym}`, {
        cacheTtlMs: fresh ? 0 : 3600_000,
        forceFresh: fresh,
      });
      setData(d);
    } catch (err) {
      setError(err.message || "لم يتم العثور على بيانات لهذا السهم");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadFundamentals("AAPL"); }, [loadFundamentals]);

  function handleSearch() {
    const sym = inputVal.toUpperCase().trim();
    if (!sym) return;
    setSymbol(sym);
    setInputVal(sym);
    loadFundamentals(sym);
  }

  function handleQuick(sym) {
    setSymbol(sym);
    setInputVal(sym);
    loadFundamentals(sym);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter") handleSearch();
  }

  return (
    <div dir="rtl" style={pageStyle}>
      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }`}</style>

      {/* ── header ── */}
      <div>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "var(--tv-text)" }}>
          🏛 أساسيات الشركات — SEC EDGAR
        </h1>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--tv-text-muted)" }}>
          البيانات من التقارير المالية لدى هيئة الأوراق المالية الأمريكية
        </p>
      </div>

      {/* ── search bar ── */}
      <div style={{
        background: "var(--tv-elevated)",
        border: "1px solid var(--tv-border)",
        borderRadius: 12,
        padding: "16px 18px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}>
        {/* input row */}
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input
            ref={inputRef}
            value={inputVal}
            onChange={e => setInputVal(e.target.value.toUpperCase())}
            onKeyDown={handleKeyDown}
            placeholder="ابحث عن رمز السهم..."
            style={{
              flex: 1,
              background: "var(--tv-surface)",
              border: "1px solid var(--tv-border)",
              borderRadius: 8,
              padding: "8px 14px",
              fontSize: 14,
              color: "var(--tv-text)",
              outline: "none",
              fontFamily: "var(--font-arabic)",
              direction: "ltr",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
            onFocus={e => e.target.style.borderColor = "var(--tv-accent)"}
            onBlur={e  => e.target.style.borderColor = "var(--tv-border)"}
          />
          <button
            onClick={handleSearch}
            disabled={loading}
            style={{ ...btnStyle, opacity: loading ? 0.65 : 1, minWidth: 80 }}
          >
            {loading ? "…" : "بحث"}
          </button>
        </div>

        {/* quick picks */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {QUICK_SYMBOLS.map(s => (
            <button
              key={s}
              onClick={() => handleQuick(s)}
              style={{
                background: symbol === s ? "var(--tv-accent)" : "var(--tv-surface)",
                color: symbol === s ? "#fff" : "var(--tv-text-muted)",
                border: `1px solid ${symbol === s ? "var(--tv-accent)" : "var(--tv-border)"}`,
                borderRadius: 6,
                padding: "5px 14px",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s",
                letterSpacing: "0.05em",
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* ── loading state ── */}
      {loading && (
        <div>
          <div style={{ height: 24, background: "var(--tv-border)", borderRadius: 6, width: 200, marginBottom: 16, animation: "pulse 1.5s ease-in-out infinite" }} />
          <div style={gridStyle}>
            {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
        </div>
      )}

      {/* ── error state ── */}
      {!loading && error && (
        <div style={{
          background: "var(--tv-elevated)",
          border: "1px solid var(--tv-negative)",
          borderRadius: 10,
          padding: "16px 20px",
          color: "var(--tv-negative)",
          fontSize: 14,
        }}>
          ⚠️ {error || "لم يتم العثور على بيانات لهذا السهم"}
        </div>
      )}

      {/* ── data display ── */}
      {!loading && !error && data && (
        <>
          {/* company header */}
          <div style={{
            background: "var(--tv-elevated)",
            border: "1px solid var(--tv-border)",
            borderRadius: 12,
            padding: "16px 20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 12,
          }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "var(--tv-text)" }}>
                {data.entity_name ?? data.ticker}
                <span style={{ fontSize: 13, fontWeight: 500, color: "var(--tv-text-muted)", marginRight: 10 }}>
                  ({data.ticker})
                </span>
              </h2>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--tv-text-muted)" }}>
                المصدر: {data.source ?? "SEC EDGAR"}
              </p>
            </div>
            {data.data_date && (
              <span style={{
                fontSize: 12,
                color: "var(--tv-text-muted)",
                background: "var(--tv-surface)",
                border: "1px solid var(--tv-border)",
                borderRadius: 6,
                padding: "4px 12px",
              }}>
                آخر تحديث: {data.data_date}
              </span>
            )}
          </div>

          {/* metrics grid */}
          <div style={gridStyle}>
            <MetricCard
              label="الإيرادات السنوية"
              value={fmtLargeNumber(data.revenue_ttm)}
              sub="TTM"
            />
            <MetricCard
              label="صافي الربح السنوي"
              value={fmtLargeNumber(data.net_income_ttm)}
              sub="TTM"
            />
            <MetricCard
              label="ربحية السهم"
              value={fmtEps(data.eps_ttm)}
              sub="EPS TTM"
            />
            <MetricCard
              label="نسبة الدين للحقوق"
              value={fmtDebt(data.debt_to_equity)}
              sub="Debt / Equity"
            />
          </div>

          {/* disclaimer */}
          <div style={{
            background: "var(--tv-elevated)",
            border: "1px solid var(--tv-warning)",
            borderRadius: 8,
            padding: "10px 16px",
            fontSize: 12,
            color: "var(--tv-warning)",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}>
            <span>⚠️</span>
            <span>البيانات من التقارير ربع السنوية لـ SEC EDGAR · تُحدَّث كل ساعة · ليست توصية استثمارية</span>
          </div>
        </>
      )}
    </div>
  );
}

// ── styles ────────────────────────────────────────────────────
const pageStyle = {
  padding: "24px 28px",
  display: "flex",
  flexDirection: "column",
  gap: 20,
  maxWidth: 1100,
  margin: "0 auto",
};

const gridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
  gap: 14,
};

const btnStyle = {
  background: "var(--tv-accent)",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  padding: "8px 18px",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};
