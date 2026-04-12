import { useEffect, useState, useCallback } from "react";
import { getJson, invalidateJsonCache } from "../api/client";

// ─── helpers ────────────────────────────────────────────────
function fmtNum(v, decimals = 2) {
  const n = Number(v ?? 0);
  return n.toFixed(decimals);
}

function fmtChange(v) {
  const n = Number(v ?? 0);
  if (n === 0) return { text: "→ 0.00", color: "var(--tv-text-muted)" };
  if (n > 0)   return { text: `↑ +${n.toFixed(2)}`, color: "var(--tv-positive)" };
  return           { text: `↓ ${n.toFixed(2)}`, color: "var(--tv-negative)" };
}

function macroScoreColor(score) {
  if (score >= 60) return "var(--tv-positive)";
  if (score >= 40) return "var(--tv-warning)";
  return "var(--tv-negative)";
}

function indicatorColor(ind) {
  const cat = String(ind.category || "").toLowerCase();
  const val = Number(ind.value ?? 0);
  if (cat === "volatility") {
    if (val < 15)  return "var(--tv-positive)";
    if (val <= 25) return "var(--tv-warning)";
    return "var(--tv-negative)";
  }
  if (cat === "credit") {
    if (val < 350)  return "var(--tv-positive)";
    if (val <= 550) return "var(--tv-warning)";
    return "var(--tv-negative)";
  }
  if (cat === "yield_curve" || ind.series_id === "T10Y2Y") {
    if (val > 0)      return "var(--tv-positive)";
    if (val >= -0.25) return "var(--tv-warning)";
    return "var(--tv-negative)";
  }
  // rates and others
  return "var(--tv-text-muted)";
}

const REGIME_LABELS = {
  risk_on:  "توسعي 🟢",
  neutral:  "محايد 🟡",
  risk_off: "انكماشي 🔴",
};
const VIX_LABELS = {
  low_vol:      "تقلب منخفض",
  elevated_vol: "تقلب متوسط",
  high_vol:     "تقلب عالي",
};
const YIELD_LABELS = {
  normal:   "منحنى طبيعي",
  flat:     "منحنى مسطح",
  inverted: "منحنى مقلوب",
};

// ─── sub-components ─────────────────────────────────────────
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
      <div style={{ height: 12, background: "var(--tv-border)", borderRadius: 4, width: "55%" }} />
      <div style={{ height: 22, background: "var(--tv-border)", borderRadius: 4, width: "70%" }} />
      <div style={{ height: 11, background: "var(--tv-border)", borderRadius: 4, width: "40%" }} />
    </div>
  );
}

function IndicatorCard({ ind }) {
  const color = indicatorColor(ind);
  const chg   = fmtChange(ind.change);
  return (
    <div style={{
      background: "var(--tv-elevated)",
      border: "1px solid var(--tv-border)",
      borderRadius: 10,
      padding: "16px 14px",
      display: "flex",
      flexDirection: "column",
      gap: 8,
      transition: "border-color 0.2s",
    }}
    onMouseEnter={e => e.currentTarget.style.borderColor = "var(--tv-accent)"}
    onMouseLeave={e => e.currentTarget.style.borderColor = "var(--tv-border)"}
    >
      <span style={{ fontSize: 11, color: "var(--tv-text-muted)", letterSpacing: "0.04em" }}>
        {ind.label}
      </span>
      <span style={{ fontSize: 20, fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>
        {fmtNum(ind.value)}
      </span>
      <span style={{ fontSize: 11, color: chg.color, fontVariantNumeric: "tabular-nums" }}>
        {chg.text}
      </span>
      {ind.date && (
        <span style={{ fontSize: 10, color: "var(--tv-text-dim)", marginTop: 2 }}>
          {ind.date}
        </span>
      )}
    </div>
  );
}

function MacroScoreBar({ score }) {
  const color = macroScoreColor(score);
  const pct   = Math.min(100, Math.max(0, score));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{
        width: "100%",
        height: 8,
        background: "var(--tv-border)",
        borderRadius: 4,
        overflow: "hidden",
      }}>
        <div style={{
          width: `${pct}%`,
          height: "100%",
          background: color,
          borderRadius: 4,
          transition: "width 0.8s ease",
        }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontSize: 10, color: "var(--tv-text-dim)" }}>0</span>
        <span style={{ fontSize: 10, color: "var(--tv-text-dim)" }}>100</span>
      </div>
    </div>
  );
}

// ─── main component ──────────────────────────────────────────
export default function MacroDashboardPage() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(async (fresh = false) => {
    if (fresh) {
      invalidateJsonCache("/api/macro/calendar");
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError("");
    try {
      const d = await getJson("/api/macro/calendar", { cacheTtlMs: fresh ? 0 : 3600_000, forceFresh: fresh });
      setData(d);
    } catch (err) {
      setError(err.message || "تعذر تحميل البيانات");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadData(false); }, [loadData]);

  const score      = Number(data?.macro_score ?? 0);
  const regime     = data?.macro_regime   ?? "";
  const vixRegime  = data?.vix_regime     ?? "";
  const yieldCurve = data?.yield_curve    ?? "";
  const indicators = data?.indicators     ?? [];
  const scoreColor = macroScoreColor(score);

  // ── loading skeleton ──
  if (loading) {
    return (
      <div dir="rtl" style={pageStyle}>
        <PageHeader />
        <div style={gridStyle}>
          {Array.from({ length: 10 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      </div>
    );
  }

  // ── error state ──
  if (error) {
    return (
      <div dir="rtl" style={pageStyle}>
        <PageHeader />
        <div style={{
          background: "var(--tv-elevated)",
          border: "1px solid var(--tv-negative)",
          borderRadius: 10,
          padding: "20px 24px",
          color: "var(--tv-negative)",
          fontSize: 14,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
        }}>
          <span>⚠️ تعذر تحميل البيانات — البيانات متاحة خلال ساعة</span>
          <button onClick={() => loadData(true)} style={btnStyle}>تحديث</button>
        </div>
      </div>
    );
  }

  return (
    <div dir="rtl" style={pageStyle}>
      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }`}</style>
      <PageHeader />

      {/* ── summary strip ── */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "260px 1fr",
        gap: 16,
      }}>
        {/* Score card */}
        <div style={{
          background: "var(--tv-elevated)",
          border: `1px solid ${scoreColor}`,
          borderRadius: 12,
          padding: "20px 18px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}>
          <span style={{ fontSize: 12, color: "var(--tv-text-muted)" }}>درجة الماكرو</span>
          <span style={{ fontSize: 40, fontWeight: 800, color: scoreColor, fontVariantNumeric: "tabular-nums" }}>
            {score}
          </span>
          <MacroScoreBar score={score} />
          <span style={{ fontSize: 14, fontWeight: 600, color: scoreColor }}>
            {REGIME_LABELS[regime] ?? regime}
          </span>
        </div>

        {/* Quick stats */}
        <div style={{
          background: "var(--tv-elevated)",
          border: "1px solid var(--tv-border)",
          borderRadius: 12,
          padding: "20px 20px",
          display: "grid",
          gridTemplateColumns: "repeat(2, 1fr)",
          gap: 16,
          alignContent: "start",
        }}>
          <QuickStat label="VIX" value={`${fmtNum(data?.vix)} — ${VIX_LABELS[vixRegime] ?? vixRegime}`} />
          <QuickStat label="منحنى العائد" value={`${fmtNum(data?.yield_spread_10y2y)}% — ${YIELD_LABELS[yieldCurve] ?? yieldCurve}`} />
          <QuickStat label="Fed Funds Rate" value={`${fmtNum(data?.fed_funds_rate)}%`} />
          <QuickStat label="HY Spread" value={`${fmtNum(data?.hy_spread)}%`} />
        </div>
      </div>

      {/* ── indicators grid ── */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: "var(--tv-text)" }}>
            المؤشرات الاقتصادية
          </h2>
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            style={{ ...btnStyle, opacity: refreshing ? 0.6 : 1 }}
          >
            {refreshing ? "جارٍ التحديث…" : "تحديث"}
          </button>
        </div>
        <div style={gridStyle}>
          {indicators.map((ind) => (
            <IndicatorCard key={ind.series_id} ind={ind} />
          ))}
        </div>
      </div>

      {/* ── footer note ── */}
      <p style={{ margin: 0, fontSize: 11, color: "var(--tv-text-dim)", textAlign: "center" }}>
        المصدر: Federal Reserve Economic Data (FRED) · تُحدَّث البيانات كل ساعة
      </p>
    </div>
  );
}

// ── shared fragments ──────────────────────────────────────────
function PageHeader() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "var(--tv-text)" }}>
        🌍 البيئة الاقتصادية الكلية
      </h1>
      <p style={{ margin: 0, fontSize: 12, color: "var(--tv-text-muted)" }}>
        المصدر: Federal Reserve Economic Data (FRED)
      </p>
    </div>
  );
}

function QuickStat({ label, value }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 11, color: "var(--tv-text-muted)" }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: "var(--tv-text)", fontVariantNumeric: "tabular-nums" }}>
        {value}
      </span>
    </div>
  );
}

// ── styles ────────────────────────────────────────────────────
const pageStyle = {
  padding: "24px 28px",
  display: "flex",
  flexDirection: "column",
  gap: 20,
  maxWidth: 1200,
  margin: "0 auto",
};

const gridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
  gap: 14,
};

const btnStyle = {
  background: "var(--tv-accent)",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  padding: "7px 16px",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};
