import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import DecisionPanel from "../components/ui/DecisionPanel";
import PageFrame from "../components/ui/PageFrame";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import SectionCard from "../components/ui/SectionCard";
import TradingChart from "../components/ui/TradingChart";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import SignalBadge from "../components/ui/SignalBadge";
import useDecisionSurface from "../hooks/useDecisionSurface";
import useJobRunner from "../hooks/useJobRunner";
import {
  fetchAlertHistory,
  fetchLiveSnapshots,
  runBatchInference,
} from "../lib/api";
import { getJson, postJson } from "../api/client";
import { useSymbolLibrary } from "../lib/useSymbolLibrary";
import { useAppData } from "../store/AppDataStore";


function statusTone(runtimeStatus) {
  const normalized = String(runtimeStatus || "").toLowerCase();
  if (normalized === "running") return "positive";
  if (normalized === "error" || normalized === "failed") return "negative";
  return "neutral";
}


export default function DashboardPage() {
  const todayIso = new Date().toISOString().slice(0, 10);

  // Use pre-fetched summary from global store
  const { data: summary, loading, error } = useAppData("summary");

  const [alerts, setAlerts] = useState([]);
  const [workspaceQuotes, setWorkspaceQuotes] = useState([]);
  const [focusSymbol, setFocusSymbol] = useState("");
  const [batchResult, setBatchResult] = useState(null);
  const [smartAlerts, setSmartAlerts] = useState([]);
  const [smartLoading, setSmartLoading] = useState(false);
  const { pinned, recent } = useSymbolLibrary();
  const batchJob = useJobRunner("intelligence_infer_batch", { recentLimit: 6 });

  const {
    decision,
    loading: decisionLoading,
    error: decisionError,
  } = useDecisionSurface({
    symbol: focusSymbol,
    startDate: "2024-01-01",
    endDate: todayIso,
    enabled: Boolean(focusSymbol),
  });

  // Load alerts and smart alerts
  useEffect(() => {
    let active = true;
    fetchAlertHistory()
      .then((data) => { if (active) setAlerts((data?.items || []).slice(0, 5)); })
      .catch(() => {});
    getJson("/api/smart/alerts")
      .then((data) => { if (active) setSmartAlerts((data?.alerts || []).slice(0, 5)); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  // Load workspace quotes
  useEffect(() => {
    const symbols = [...pinned, ...recent].map((s) => s.symbol).filter(Boolean).slice(0, 8);
    if (!symbols.length) { setWorkspaceQuotes([]); return; }
    let active = true;
    fetchLiveSnapshots({ symbols })
      .then((p) => { if (active) setWorkspaceQuotes(p?.items || []); })
      .catch(() => { if (active) setWorkspaceQuotes([]); });
    return () => { active = false; };
  }, [pinned, recent]);

  // Auto-select focus symbol
  useEffect(() => {
    if (focusSymbol) return;
    const derived = [
      ...workspaceQuotes.map((q) => q.symbol),
      ...pinned.map((s) => s.symbol),
      ...recent.map((s) => s.symbol),
      summary?.sample_analyze?.instrument,
      summary?.scan_ranking?.top_pick,
    ].find(Boolean);
    if (derived) setFocusSymbol(String(derived).trim().toUpperCase());
  }, [focusSymbol, workspaceQuotes, pinned, recent, summary]);

  // Batch results
  useEffect(() => {
    if (batchJob.currentJob?.status === "completed" && batchJob.currentJob?.result) {
      setBatchResult(batchJob.currentJob.result);
    }
  }, [batchJob.currentJob]);

  const opportunities = useMemo(() => (summary?.watchlists?.momentum_leaders || []).slice(0, 5), [summary]);
  const learningState = summary?.continuous_learning?.state || {};
  const marketProvider = summary?.market_data_status?.primary_provider || "-";
  const bestCandidate = learningState?.latest_metrics?.best_candidate?.candidate_name || learningState?.best_strategy_name || "-";
  const workspaceSymbols = useMemo(() => {
    const candidates = [focusSymbol, ...workspaceQuotes.map((q) => q.symbol), ...pinned.map((s) => s.symbol), ...recent.map((s) => s.symbol)].filter(Boolean);
    return [...new Set(candidates.map((s) => String(s).trim().toUpperCase()))].slice(0, 8);
  }, [focusSymbol, workspaceQuotes, pinned, recent]);

  async function handleBatch() {
    setBatchResult(null);
    await batchJob.submit(() => runBatchInference({
      symbols: workspaceSymbols.length ? workspaceSymbols : ["AAPL", "MSFT", "NVDA", "SPY"],
      start_date: "2024-01-01",
      end_date: todayIso,
      include_dl: true,
      include_ensemble: true,
    }));
  }

  async function handleSmartCycle() {
    setSmartLoading(true);
    try {
      await postJson("/api/smart/cycle", {});
      const data = await getJson("/api/smart/alerts");
      setSmartAlerts((data?.alerts || []).slice(0, 5));
    } catch {} finally { setSmartLoading(false); }
  }

  const chartSummaryItems = [
    { label: "الرمز", value: focusSymbol || "-", badge: "Focus" },
    { label: "الموقف", value: decision?.stance || summary?.sample_analyze?.signal || "-", tone: decision?.stance === "BUY" ? "positive" : decision?.stance === "SELL" ? "negative" : "warning" },
    { label: "الثقة", value: decision?.confidence ?? "-", badge: "%" },
    { label: "أفضل إعداد", value: decision?.best_setup || "-" },
  ];

  return (
    <PageFrame
      title="مركز القيادة"
      description="نظرة تشغيلية شاملة: السوق، القرار، المخاطر، والتنفيذ."
      eyebrow="لوحة التداول"
      headerActions={
        <>
          <Link className="btn btn-secondary btn-sm" to={`/live-market?symbol=${encodeURIComponent(focusSymbol || "AAPL")}`}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" /></svg>
            السوق
          </Link>
          <Link className="btn btn-secondary btn-sm" to={`/paper-trading?symbol=${encodeURIComponent(focusSymbol || "AAPL")}`}>
            التداول
          </Link>
          <StatusBadge label={marketProvider !== "-" ? `${marketProvider}` : "بيانات"} tone="positive" />
        </>
      }
    >
      <ErrorBanner message={error} />

      {/* KPI Strip */}
      {loading ? <LoadingSkeleton lines={2} /> : summary && (
        <SummaryStrip
          items={[
            { label: "Top Pick", value: summary.scan_ranking?.top_pick || "-", tone: "info" },
            { label: "اتساع السوق", value: summary.breadth?.breadth_ratio ?? "-" },
            { label: "مزود البيانات", value: marketProvider },
            { label: "المراكز المفتوحة", value: summary.portfolio?.summary?.open_positions ?? 0 },
            { label: "مرحلة التعلم", value: learningState.active_stage || "idle" },
            { label: "أفضل مرشح", value: bestCandidate },
          ]}
        />
      )}

      {/* Main content: Chart + Decision */}
      <div className="command-grid">
        {/* Trading Chart */}
        <TradingChart
          className="col-span-7"
          title="مساحة القرار"
          description="الرمز المحوري مع مناطق القرار والمستويات الرئيسية."
          decision={decision}
          summaryItems={chartSummaryItems}
          loading={decisionLoading}
          height={420}
        />

        {/* Decision Panel */}
        <DecisionPanel
          className="col-span-5"
          decision={decision}
          loading={decisionLoading}
          error={decisionError}
          title="القرار الحالي"
          description="الموقف، الأدلة، والأهداف للرمز المحوري."
        />

        {/* Workspace */}
        <SectionCard
          className="col-span-7"
          title="مساحة العمل"
          description="رموز المتابعة النشطة — انقر لتغيير التركيز."
          action={<StatusBadge label={`${workspaceQuotes.length} رموز`} tone="neutral" dot={false} />}
        >
          {workspaceQuotes.length ? (
            <>
              <div className="workspace-symbol-actions">
                {workspaceQuotes.map((q) => (
                  <button
                    key={q.symbol}
                    className={`workspace-symbol-chip${focusSymbol === q.symbol ? " active" : ""}`}
                    onClick={() => setFocusSymbol(q.symbol)}
                    type="button"
                  >
                    {q.symbol}
                  </button>
                ))}
              </div>
              <div className="result-grid">
                {workspaceQuotes.map((q) => (
                  <MetricCard
                    key={q.symbol}
                    label={q.symbol}
                    value={q.price ?? "-"}
                    detail={`${q.change_pct ?? 0}%`}
                    tone={Number(q.change_pct || 0) >= 0 ? "positive" : "negative"}
                    onClick={() => setFocusSymbol(q.symbol)}
                  />
                ))}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <span className="empty-state-title">ابدأ برمز واحد</span>
              <span className="empty-state-text">اختر رمزاً من شريط العمل ثم ثبّته.</span>
            </div>
          )}
        </SectionCard>

        {/* Batch Intelligence */}
        <SectionCard
          className="col-span-5"
          title="الاستدلال الدفعي"
          description="تحديث ذكي لرموز مساحة العمل."
          action={
            <button
              className="btn btn-primary btn-sm"
              onClick={() => handleBatch().catch(() => {})}
              disabled={batchJob.submitting || !workspaceSymbols.length}
              type="button"
            >
              {batchJob.submitting ? "جارٍ..." : "تشغيل"}
            </button>
          }
        >
          {batchResult?.items?.length ? (
            <div className="dashboard-feed-list">
              {batchResult.items.slice(0, 4).map((item, i) => (
                <div className="dashboard-feed-item" key={item.instrument || i}>
                  <div className="dashboard-feed-copy">
                    <strong>{item.instrument || item.symbol || "Batch"}</strong>
                    <p>{item.setup_type || item.reasons || "Analysis complete"}</p>
                  </div>
                  <SignalBadge signal={item.smart_signal || item.signal || "HOLD"} />
                </div>
              ))}
            </div>
          ) : batchJob.currentJob?.status === "running" ? (
            <LoadingSkeleton lines={3} />
          ) : (
            <div className="empty-state">
              <span className="empty-state-text">اضغط "تشغيل" لتحديث الإشارات.</span>
            </div>
          )}
        </SectionCard>

        {/* Opportunities */}
        <SectionCard
          className="col-span-7"
          title="فرص المتابعة"
          description="أقرب الرموز للانتقال إلى التحليل أو التنفيذ."
          action={<StatusBadge label={`${opportunities.length} فرص`} tone="neutral" dot={false} />}
        >
          {loading ? <LoadingSkeleton lines={4} /> : opportunities.length ? (
            <div className="dashboard-decision-list">
              {opportunities.map((item) => (
                <div className="dashboard-decision-item" key={item.symbol}>
                  <div className="dashboard-decision-primary">
                    <strong>{item.symbol}</strong>
                    <p>{item.security_name || "فرصة متابعة"}</p>
                  </div>
                  <div className="dashboard-decision-metrics">
                    <span className={Number(item.change_pct || 0) >= 0 ? "quote-positive" : "quote-negative"}>
                      {item.change_pct ?? 0}%
                    </span>
                    <small>{item.price ?? "-"}</small>
                  </div>
                  <div className="dashboard-decision-actions">
                    <Link className="btn btn-ghost btn-xs" to={`/analyze?symbol=${encodeURIComponent(item.symbol)}`}>تحليل</Link>
                    <Link className="btn btn-ghost btn-xs" to={`/paper-trading?symbol=${encodeURIComponent(item.symbol)}`}>ورقي</Link>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <span className="empty-state-title">لا توجد فرص حالياً</span>
              <span className="empty-state-text">ستظهر هنا بعد تحديث الإشارات.</span>
            </div>
          )}
        </SectionCard>

        {/* Smart Automation */}
        <SectionCard
          className="col-span-5"
          title="الأتمتة الذكية"
          description="تنبيهات ذكية من المحرك التلقائي."
          action={
            <button
              className="btn btn-primary btn-sm"
              onClick={() => handleSmartCycle().catch(() => {})}
              disabled={smartLoading}
              type="button"
            >
              {smartLoading ? "جارٍ..." : "فحص ذكي"}
            </button>
          }
        >
          {smartAlerts.length ? (
            <div className="dashboard-feed-list">
              {smartAlerts.map((alert) => (
                <div className="dashboard-feed-item" key={alert.id}>
                  <div className="dashboard-feed-copy">
                    <strong>{alert.symbol} · {alert.signal}</strong>
                    <p>{alert.recommendation || alert.ai_summary || "فرصة مكتشفة"}</p>
                  </div>
                  <StatusBadge
                    label={alert.quality || `${alert.confidence}%`}
                    tone={alert.signal === "BUY" ? "positive" : alert.signal === "SELL" ? "negative" : "neutral"}
                    dot={false}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <span className="empty-state-text">اضغط "فحص ذكي" لاكتشاف الفرص.</span>
            </div>
          )}
        </SectionCard>

        {/* Alerts & Engine State */}
        <SectionCard
          className="col-span-5"
          title="التنبيهات والمحرك"
          description="حالة التعلم المستمر وآخر التنبيهات."
          action={<StatusBadge label={learningState.runtime_status || "idle"} tone={statusTone(learningState.runtime_status)} />}
        >
          {loading ? <LoadingSkeleton lines={4} /> : (
            <>
              <SummaryStrip
                compact
                items={[
                  { label: "آخر نجاح", value: learningState.last_success_at || "-" },
                  { label: "الدورة التالية", value: learningState.next_cycle_at || "-" },
                  { label: "تنبيهات المخاطر", value: summary?.risk?.portfolio_warnings?.length ?? 0, tone: "warning" },
                ]}
              />
              {alerts.length ? (
                <div className="dashboard-feed-list" style={{ marginTop: "var(--space-3)" }}>
                  {alerts.map((alert) => (
                    <div className="dashboard-feed-item" key={alert.id}>
                      <div className="dashboard-feed-copy">
                        <strong>{`${alert.symbol || "SYSTEM"} · ${alert.alert_type}`}</strong>
                        <p>{alert.message}</p>
                      </div>
                      <StatusBadge label={alert.severity} tone={alert.severity === "warning" ? "warning" : "neutral"} dot={false} />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <span className="empty-state-text">لا توجد تنبيهات حالياً.</span>
                </div>
              )}
            </>
          )}
        </SectionCard>
      </div>
    </PageFrame>
  );
}
