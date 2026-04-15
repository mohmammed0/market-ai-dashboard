import { useState, useEffect, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function getHeaders() {
  const token = localStorage.getItem("market_ai_token") || "";
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, { headers: getHeaders(), ...opts });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function normalizeHealthState(value) {
  if (value == null) return "unknown";
  if (typeof value === "string") return value.trim().toLowerCase();
  if (typeof value === "object") {
    const candidate = value.status || value.state || value.mode || value.detail || value.label;
    return String(candidate || "unknown").trim().toLowerCase();
  }
  return String(value).trim().toLowerCase();
}

function healthStateLabel(value) {
  const normalized = normalizeHealthState(value);
  const labels = {
    ok: "متصل",
    connected: "متصل",
    active: "نشط",
    running: "يعمل",
    ready: "جاهز",
    paused: "موقوف",
    disabled: "معطل",
    idle: "خامل",
    unavailable: "غير متاح",
    misconfigured: "غير مهيأ",
    error: "خطأ",
    failed: "فشل",
    unknown: "غير معروف",
  };
  return labels[normalized] || String(value || "غير معروف");
}

function healthStateTone(value) {
  const normalized = normalizeHealthState(value);
  if (["ok", "connected", "active", "running", "ready", "paused"].includes(normalized)) return "positive";
  if (["disabled", "idle", "misconfigured"].includes(normalized)) return "warning";
  return "negative";
}

function formatDuration(startedAt, completedAt) {
  if (!startedAt) return "-";
  const start = new Date(startedAt);
  const end = completedAt ? new Date(completedAt) : new Date();
  const diff = Math.round((end - start) / 1000);
  if (diff < 60) return `${diff}ث`;
  if (diff < 3600) return `${Math.round(diff / 60)}د`;
  return `${Math.round(diff / 3600)}س`;
}

function formatTime(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "-";
  }
}

function formatDateTime(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("ar-SA", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return "-";
  }
}

function pct(val) {
  if (val == null || val === undefined) return "-";
  const n = parseFloat(val);
  if (isNaN(n)) return "-";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function num(val, dec = 2) {
  if (val == null || val === undefined) return "-";
  const n = parseFloat(val);
  if (isNaN(n)) return "-";
  return n.toFixed(dec);
}

// ── Score Gauge ──────────────────────────────────────────────────────────────
function ScoreGauge({ score }) {
  const s = parseFloat(score) || 0;
  const clamped = Math.min(100, Math.max(0, s));
  const color = clamped >= 65 ? "#22c55e" : clamped >= 40 ? "#eab308" : "#ef4444";
  const angle = (clamped / 100) * 180 - 90;
  const rad = (angle * Math.PI) / 180;
  const cx = 60, cy = 60, r = 46;
  const x = cx + r * Math.cos(rad);
  const y = cy + r * Math.sin(rad);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
      <svg width="120" height="70" viewBox="0 0 120 70">
        <path d="M 14 60 A 46 46 0 0 1 106 60" fill="none" stroke="#1e293b" strokeWidth="10" strokeLinecap="round" />
        <path
          d={`M 14 60 A 46 46 0 0 1 ${x.toFixed(2)} ${y.toFixed(2)}`}
          fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
        />
        <line x1={cx} y1={cy} x2={x.toFixed(2)} y2={y.toFixed(2)} stroke={color} strokeWidth="2.5" strokeLinecap="round" />
        <circle cx={cx} cy={cy} r="4" fill={color} />
        <text x={cx} y="58" textAnchor="middle" fill={color} fontSize="16" fontWeight="bold" fontFamily="inherit">
          {clamped.toFixed(0)}
        </text>
      </svg>
      <span style={{ fontSize: 11, color: "#64748b" }}>
        {clamped >= 65 ? "ممتاز" : clamped >= 40 ? "مقبول" : "ضعيف"}
      </span>
    </div>
  );
}

// ── Pulse dot ────────────────────────────────────────────────────────────────
function PulseDot({ color = "#22c55e", animate = true }) {
  return (
    <span style={{ position: "relative", display: "inline-flex", width: 12, height: 12 }}>
      {animate && (
        <span style={{
          position: "absolute", inset: 0, borderRadius: "50%", background: color, opacity: 0.4,
          animation: "ping 1.4s cubic-bezier(0,0,0.2,1) infinite",
        }} />
      )}
      <span style={{ position: "relative", width: 12, height: 12, borderRadius: "50%", background: color, display: "inline-block" }} />
    </span>
  );
}

// ── Stat Card ────────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, sub, color = "#3b82f6", pulse = false }) {
  return (
    <div style={{
      background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12,
      padding: "16px 20px", display: "flex", flexDirection: "column", gap: 8,
      borderTop: `2px solid ${color}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 20 }}>{icon}</span>
        <span style={{ color: "#64748b", fontSize: 12 }}>{label}</span>
        {pulse && <PulseDot color={color} />}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: "#f1f5f9" }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: "#64748b" }}>{sub}</div>}
    </div>
  );
}

// ── Run row ──────────────────────────────────────────────────────────────────
function RunRow({ run, index }) {
  const statusColors = { completed: "#22c55e", failed: "#ef4444", running: "#eab308", pending: "#64748b" };
  const statusLabels = { completed: "مكتمل", failed: "فشل", running: "يعمل", pending: "انتظار" };
  const color = statusColors[run.status] || "#64748b";
  const label = statusLabels[run.status] || run.status;

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
      background: index % 2 === 0 ? "transparent" : "#0f172a1a",
      borderBottom: "1px solid #1e293b0d",
    }}>
      <PulseDot color={color} animate={run.status === "running"} />
      <span style={{ color: "#94a3b8", fontSize: 11, minWidth: 80, fontFamily: "monospace" }}>
        {run.run_id?.slice(-8) || "-"}
      </span>
      <span style={{ fontSize: 11, color, minWidth: 50 }}>{label}</span>
      <span style={{ fontSize: 11, color: "#64748b", minWidth: 60 }}>{run.stage || "-"}</span>
      <span style={{ fontSize: 11, color: "#475569", flex: 1 }}>{formatDateTime(run.started_at)}</span>
      <span style={{ fontSize: 11, color: "#475569" }}>{formatDuration(run.started_at, run.completed_at)}</span>
      {run.error && (
        <span style={{ fontSize: 10, color: "#ef4444", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={run.error}>
          {run.error}
        </span>
      )}
    </div>
  );
}

// ── Job colors ────────────────────────────────────────────────────────────────
const JOB_COLORS = {
  quote_snapshot: "#3b82f6",
  alert_cycle: "#f59e0b",
  breadth_cycle: "#8b5cf6",
  smart_cycle: "#22c55e",
  maintenance_reconcile: "#64748b",
};
function jobColor(name) {
  for (const key of Object.keys(JOB_COLORS)) {
    if (name?.includes(key)) return JOB_COLORS[key];
  }
  return "#94a3b8";
}

function SchedulerRow({ job, index }) {
  const color = jobColor(job.job_name);
  const ok = job.status === "ok" || job.status === "success" || job.status === "completed";
  const statusColor = ok ? "#22c55e" : job.status === "running" ? "#eab308" : "#ef4444";

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10, padding: "7px 12px",
      borderBottom: "1px solid #1e293b22",
      background: index % 2 === 0 ? "transparent" : "#0f172a1a",
    }}>
      <span style={{
        width: 8, height: 8, borderRadius: "50%", background: color,
        display: "inline-block", flexShrink: 0,
      }} />
      <span style={{ fontSize: 11, color, minWidth: 160, fontFamily: "monospace" }}>{job.job_name || "-"}</span>
      <span style={{ fontSize: 11, color: statusColor, minWidth: 60 }}>{job.status || "-"}</span>
      <span style={{ fontSize: 11, color: "#64748b", minWidth: 90 }}>{formatDateTime(job.ran_at)}</span>
      <span style={{ fontSize: 11, color: "#94a3b8", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{job.detail || ""}</span>
    </div>
  );
}

// ── Health Chip ───────────────────────────────────────────────────────────────
function HealthChip({ label, value, ok }) {
  const tone = ok ? "positive" : healthStateTone(value);
  const color = tone === "positive" ? "#22c55e" : tone === "warning" ? "#f59e0b" : "#ef4444";
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      background: "#0f172a", border: `1px solid ${color}33`,
      borderRadius: 20, padding: "4px 12px",
    }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: color, display: "inline-block" }} />
      <span style={{ fontSize: 12, color: "#94a3b8" }}>{label}</span>
      <span style={{ fontSize: 12, color }}>{healthStateLabel(value || (ok ? "connected" : "unknown"))}</span>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
export default function BrainDashboardPage() {
  const [clStatus, setClStatus] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [clResult, healthResult] = await Promise.allSettled([
        apiFetch("/api/continuous-learning/status"),
        apiFetch("/health"),
      ]);
      if (clResult.status === "fulfilled") {
        setClStatus(clResult.value);
      }
      if (healthResult.status === "fulfilled") {
        setHealth(healthResult.value);
      }
      setLastUpdate(new Date());
      const errors = [clResult, healthResult]
        .filter((result) => result.status === "rejected")
        .map((result) => result.reason?.message || "خطأ غير معروف");
      setError(errors.length ? errors.join(" • ") : null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const timer = setInterval(fetchAll, 30000);
    return () => clearInterval(timer);
  }, [fetchAll]);

  const handleStart = async () => {
    setActionLoading(true);
    try { await apiFetch("/api/continuous-learning/start", { method: "POST" }); await fetchAll(); }
    catch (e) { setError(e.message); }
    finally { setActionLoading(false); }
  };

  const handleTogglePause = async () => {
    const isPaused = clStatus?.paused;
    setActionLoading(true);
    try {
      await apiFetch(`/api/continuous-learning/${isPaused ? "resume" : "pause"}`, { method: "POST" });
      await fetchAll();
    } catch (e) { setError(e.message); }
    finally { setActionLoading(false); }
  };

  // Derived values
  const state = clStatus?.state || {};
  const running = clStatus?.running;
  const paused = clStatus?.paused;
  const enabled = clStatus?.enabled;
  const bestCandidate = state?.latest_metrics?.best_candidate || {};
  const bestMetrics = bestCandidate?.metrics || {};
  const recentRuns = (clStatus?.recent_runs || []).slice(0, 10);
  const score = bestCandidate?.score;

  const healthDb = health?.live_stack?.database;
  const healthRedis = health?.live_stack?.redis;
  const schedulerState = health?.orchestration?.scheduler?.runtime_state;
  const clState = health?.orchestration?.continuous_learning?.runtime_state;
  const schedulerJobs = (health?.orchestration?.scheduler?.recent_runs || []).slice(0, 20);

  // Status label
  let statusLabel = "متوقف";
  let statusColor = "#ef4444";
  if (running && !paused) { statusLabel = "نشط"; statusColor = "#22c55e"; }
  else if (paused) { statusLabel = "موقوف مؤقتاً"; statusColor = "#eab308"; }
  else if (enabled) { statusLabel = "ممكّن"; statusColor = "#3b82f6"; }

  const progressPercent = running ? 65 : 0; // Animated indicator when running

  return (
    <div style={{ minHeight: "100vh", background: "#020617", color: "#f1f5f9", direction: "rtl", fontFamily: "inherit", padding: "0 0 40px" }}>
      <style>{`
        @keyframes ping {
          75%, 100% { transform: scale(2); opacity: 0; }
        }
        @keyframes progress-pulse {
          0% { opacity: 1; }
          50% { opacity: 0.5; }
          100% { opacity: 1; }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .brain-btn {
          background: #1e293b;
          border: 1px solid #334155;
          color: #94a3b8;
          border-radius: 8px;
          padding: 7px 16px;
          cursor: pointer;
          font-size: 13px;
          transition: all 0.15s;
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .brain-btn:hover { background: #334155; color: #f1f5f9; border-color: #475569; }
        .brain-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .brain-btn--primary { background: #1d4ed8; border-color: #3b82f6; color: #fff; }
        .brain-btn--primary:hover { background: #2563eb; }
        .brain-btn--danger { background: #7f1d1d; border-color: #ef4444; color: #fca5a5; }
        .brain-btn--danger:hover { background: #991b1b; }
        .brain-btn--success { background: #14532d; border-color: #22c55e; color: #86efac; }
        .brain-btn--success:hover { background: #166534; }
        .brain-section {
          background: #0f172a;
          border: 1px solid #1e293b;
          border-radius: 14px;
          overflow: hidden;
        }
        .brain-section-header {
          padding: 14px 20px;
          border-bottom: 1px solid #1e293b;
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .brain-metric-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 0;
          border-bottom: 1px solid #1e293b22;
        }
        .brain-metric-row:last-child { border-bottom: none; }
      `}</style>

      {/* ── Header ─────────────────────────────────────────────────── */}
      <div style={{
        background: "#0a1628", borderBottom: "1px solid #1e293b",
        padding: "14px 24px", display: "flex", alignItems: "center", gap: 16,
        position: "sticky", top: 0, zIndex: 10,
      }}>
        <span style={{ fontSize: 22, fontWeight: 700, color: "#f1f5f9" }}>🧠 مركز الذكاء الاصطناعي</span>
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: `${statusColor}15`, border: `1px solid ${statusColor}44`, borderRadius: 20, padding: "4px 14px" }}>
          <PulseDot color={statusColor} animate={running && !paused} />
          <span style={{ fontSize: 13, color: statusColor, fontWeight: 600 }}>{statusLabel}</span>
        </div>
        <div style={{ flex: 1 }} />
        {lastUpdate && (
          <span style={{ fontSize: 12, color: "#475569" }}>
            آخر تحديث: {formatTime(lastUpdate.toISOString())}
          </span>
        )}
        <button className="brain-btn" onClick={fetchAll} disabled={loading} title="تحديث">
          <svg style={{ width: 14, height: 14, animation: loading ? "spin 1s linear infinite" : "none" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
          تحديث
        </button>
      </div>

      <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 20 }}>

        {error && (
          <div style={{ background: "#7f1d1d33", border: "1px solid #ef444444", borderRadius: 10, padding: "12px 16px", color: "#fca5a5", fontSize: 13 }}>
            ⚠️ خطأ في الاتصال: {error}
          </div>
        )}

        {/* ── Top stats ─────────────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14 }}>
          <StatCard
            icon="⚡"
            label="حالة التعلم"
            value={statusLabel}
            sub={state.current_model_version ? `الإصدار: ${state.current_model_version}` : "—"}
            color={statusColor}
            pulse={running && !paused}
          />
          <StatCard
            icon="🏆"
            label="أفضل استراتيجية"
            value={state.best_strategy_name || "—"}
            sub={score != null ? `النتيجة: ${parseFloat(score).toFixed(3)}` : "لا توجد بيانات"}
            color="#8b5cf6"
          />
          <StatCard
            icon="🎯"
            label="معدل الفوز"
            value={bestMetrics.win_rate_pct != null ? `${parseFloat(bestMetrics.win_rate_pct).toFixed(1)}%` : "—"}
            sub={bestMetrics.trade_count != null ? `${bestMetrics.trade_count} صفقة` : ""}
            color="#22c55e"
          />
          <StatCard
            icon="📈"
            label="العائد الكلي"
            value={pct(bestMetrics.total_return_pct)}
            sub={bestMetrics.avg_trade_return_pct != null ? `متوسط صفقة: ${pct(bestMetrics.avg_trade_return_pct)}` : ""}
            color={parseFloat(bestMetrics.total_return_pct) >= 0 ? "#22c55e" : "#ef4444"}
          />
        </div>

        {/* ── Main 2-col grid ───────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>

          {/* LEFT — Learning Timeline */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="brain-section">
              <div className="brain-section-header">
                <span style={{ fontSize: 16 }}>🔄</span>
                <span style={{ fontWeight: 600, color: "#e2e8f0" }}>خط زمني للتعلم</span>
                <div style={{ flex: 1 }} />
                <button
                  className={`brain-btn ${running && !paused ? "brain-btn--danger" : "brain-btn--success"}`}
                  onClick={handleTogglePause}
                  disabled={actionLoading || !running}
                  title={paused ? "استئناف" : "إيقاف مؤقت"}
                >
                  {paused ? "▶ استئناف" : "⏸ إيقاف مؤقت"}
                </button>
                <button
                  className="brain-btn brain-btn--primary"
                  onClick={handleStart}
                  disabled={actionLoading || (running && !paused)}
                  title="بدء دورة جديدة"
                >
                  ▶ بدء دورة جديدة
                </button>
              </div>

              {/* Progress bar */}
              <div style={{ padding: "14px 16px", borderBottom: "1px solid #1e293b" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: "#64748b" }}>
                    {running ? `المرحلة: ${recentRuns[0]?.stage || "جارٍ التشغيل"}` : "لا توجد دورة نشطة"}
                  </span>
                  <span style={{ fontSize: 12, color: "#94a3b8" }}>
                    {state.next_cycle_at ? `التالية: ${formatDateTime(state.next_cycle_at)}` : ""}
                  </span>
                </div>
                <div style={{ height: 6, background: "#1e293b", borderRadius: 6, overflow: "hidden" }}>
                  <div style={{
                    height: "100%", width: running ? "65%" : "0%",
                    background: running ? "linear-gradient(90deg,#3b82f6,#8b5cf6)" : "#1e293b",
                    borderRadius: 6, transition: "width 0.6s ease",
                    animation: running ? "progress-pulse 2s ease-in-out infinite" : "none",
                  }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 11, color: "#475569" }}>
                  <span>آخر نجاح: {formatDateTime(state.last_success_at)}</span>
                  <span>بدأ: {formatDateTime(state.last_started_at)}</span>
                </div>
              </div>

              {/* Run list */}
              <div>
                <div style={{ padding: "8px 12px 4px", display: "flex", gap: 10, fontSize: 10, color: "#475569", borderBottom: "1px solid #1e293b22" }}>
                  <span style={{ width: 12 }} />
                  <span style={{ minWidth: 80 }}>معرف الجلسة</span>
                  <span style={{ minWidth: 50 }}>الحالة</span>
                  <span style={{ minWidth: 60 }}>المرحلة</span>
                  <span style={{ flex: 1 }}>وقت البدء</span>
                  <span>المدة</span>
                </div>
                {recentRuns.length === 0 ? (
                  <div style={{ padding: 24, textAlign: "center", color: "#475569", fontSize: 13 }}>لا توجد جلسات سابقة</div>
                ) : (
                  recentRuns.map((r, i) => <RunRow key={r.run_id || i} run={r} index={i} />)
                )}
              </div>
            </div>
          </div>

          {/* RIGHT — Best Strategy Card */}
          <div className="brain-section" style={{ alignSelf: "start" }}>
            <div className="brain-section-header">
              <span style={{ fontSize: 16 }}>🏅</span>
              <span style={{ fontWeight: 600, color: "#e2e8f0" }}>أفضل استراتيجية</span>
            </div>

            <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

              {/* Strategy name + gauge */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#f1f5f9", marginBottom: 4 }}>
                    {state.best_strategy_name || "—"}
                  </div>
                  <div style={{ fontSize: 12, color: "#64748b" }}>
                    الإصدار: {state.current_model_version || "—"}
                  </div>
                </div>
                <ScoreGauge score={score || 0} />
              </div>

              {/* Metrics */}
              <div style={{ borderTop: "1px solid #1e293b", paddingTop: 14 }}>
                <div style={{ fontSize: 12, color: "#64748b", marginBottom: 10 }}>مؤشرات الأداء</div>
                {[
                  { label: "معدل الفوز", value: bestMetrics.win_rate_pct != null ? `${parseFloat(bestMetrics.win_rate_pct).toFixed(1)}%` : "—", color: "#22c55e" },
                  { label: "متوسط عائد الصفقة", value: pct(bestMetrics.avg_trade_return_pct), color: parseFloat(bestMetrics.avg_trade_return_pct) >= 0 ? "#22c55e" : "#ef4444" },
                  { label: "العائد الإجمالي", value: pct(bestMetrics.total_return_pct), color: parseFloat(bestMetrics.total_return_pct) >= 0 ? "#22c55e" : "#ef4444" },
                  { label: "أقصى تراجع", value: bestMetrics.max_drawdown_pct != null ? `${parseFloat(bestMetrics.max_drawdown_pct).toFixed(2)}%` : "—", color: "#f59e0b" },
                  { label: "عدد الصفقات", value: bestMetrics.trade_count ?? "—", color: "#94a3b8" },
                ].map(({ label, value, color }) => (
                  <div key={label} className="brain-metric-row">
                    <span style={{ fontSize: 13, color: "#94a3b8" }}>{label}</span>
                    <span style={{ fontSize: 14, fontWeight: 600, color }}>{value}</span>
                  </div>
                ))}
              </div>

              {/* Score breakdown */}
              {score != null && (
                <div style={{ background: "#020617", border: "1px solid #1e293b", borderRadius: 10, padding: "12px 16px" }}>
                  <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>درجة المرشح</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ flex: 1, height: 8, background: "#1e293b", borderRadius: 6, overflow: "hidden" }}>
                      <div style={{
                        height: "100%",
                        width: `${Math.min(100, parseFloat(score) * 100).toFixed(1)}%`,
                        background: parseFloat(score) >= 0.65 ? "#22c55e" : parseFloat(score) >= 0.4 ? "#eab308" : "#ef4444",
                        borderRadius: 6,
                      }} />
                    </div>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", minWidth: 40, textAlign: "left" }}>
                      {(parseFloat(score) * 100).toFixed(1)}
                    </span>
                  </div>
                </div>
              )}

              {!state.best_strategy_name && (
                <div style={{ textAlign: "center", padding: "20px 0", color: "#475569", fontSize: 13 }}>
                  لم تكتمل أي دورة تعلم بعد
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Scheduler Jobs ────────────────────────────────────────── */}
        <div className="brain-section">
          <div className="brain-section-header">
            <span style={{ fontSize: 16 }}>⏱</span>
            <span style={{ fontWeight: 600, color: "#e2e8f0" }}>جدولة المهام</span>
            <div style={{ flex: 1 }} />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {Object.entries(JOB_COLORS).map(([key, color]) => (
                <span key={key} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, color: "#94a3b8" }}>
                  <span style={{ width: 7, height: 7, borderRadius: "50%", background: color, display: "inline-block" }} />
                  {key.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </div>
          <div>
            <div style={{ padding: "8px 12px 4px", display: "flex", gap: 10, fontSize: 10, color: "#475569", borderBottom: "1px solid #1e293b22" }}>
              <span style={{ width: 8 }} />
              <span style={{ minWidth: 160 }}>اسم المهمة</span>
              <span style={{ minWidth: 60 }}>الحالة</span>
              <span style={{ minWidth: 90 }}>وقت التشغيل</span>
              <span>التفاصيل</span>
            </div>
            {schedulerJobs.length === 0 ? (
              <div style={{ padding: 24, textAlign: "center", color: "#475569", fontSize: 13 }}>لا توجد مهام مجدولة سابقة</div>
            ) : (
              schedulerJobs.map((j, i) => <SchedulerRow key={i} job={j} index={i} />)
            )}
          </div>
        </div>

        {/* ── System Health bar ─────────────────────────────────────── */}
        <div style={{
          background: "#0f172a", border: "1px solid #1e293b", borderRadius: 12,
          padding: "14px 20px", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
        }}>
          <span style={{ fontSize: 13, color: "#64748b", marginLeft: 8 }}>🩺 صحة النظام:</span>
          <HealthChip label="قاعدة البيانات" value={healthDb} ok={healthDb === "ok" || healthDb === "connected"} />
          <HealthChip label="Redis" value={healthRedis} ok={healthRedis === "ok" || healthRedis === "connected"} />
          <HealthChip label="المجدول" value={schedulerState} ok={schedulerState === "running" || schedulerState === "active"} />
          <HealthChip label="التعلم المستمر" value={clState} ok={clState === "running" || clState === "active" || clState === "paused"} />
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: "#334155" }}>تحديث تلقائي كل 30 ثانية</span>
        </div>

      </div>
    </div>
  );
}
