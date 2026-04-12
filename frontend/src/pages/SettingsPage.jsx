import { useEffect, useMemo, useState } from "react";

import PageFrame from "../components/ui/PageFrame";
import DataTable from "../components/ui/DataTable";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import ErrorBanner from "../components/ui/ErrorBanner";
import useSettingsPageData from "../hooks/useSettingsPageData";
import {
  getApiBaseUrl,
  fetchAiStatus,
  saveAlpacaSettings,
  testAlpacaSettings,
} from "../lib/api";


function toneForState(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (["ready", "ok", "connected", "running"].includes(normalized)) return "positive";
  if (["warning", "degraded", "disabled", "standby"].includes(normalized)) return "warning";
  if (["error", "failed"].includes(normalized)) return "negative";
  return "neutral";
}


export default function SettingsPage() {
  const {
    healthStatus, readinessStatus, runtimeStatus, runtimeSettings,
    recentJobs, settingsLoading, jobsLoading, settingsError, refreshData,
  } = useSettingsPageData();

  const [llmStatus, setLlmStatus] = useState(null);
  const [testingLlm, setTestingLlm] = useState(false);
  const [llmMsg, setLlmMsg] = useState("");
  const [alpacaMsg, setAlpacaMsg] = useState("");
  const [savingAlpaca, setSavingAlpaca] = useState(false);
  const [testingAlpaca, setTestingAlpaca] = useState(false);
  const [alpacaForm, setAlpacaForm] = useState({ enabled: false, paper: true, apiKey: "", secretKey: "", urlOverride: "" });

  useEffect(() => {
    if (!runtimeSettings) return;
    setAlpacaForm({ enabled: Boolean(runtimeSettings?.broker?.alpaca?.enabled), paper: Boolean(runtimeSettings?.broker?.alpaca?.paper ?? true), apiKey: "", secretKey: "", urlOverride: runtimeSettings?.broker?.alpaca?.url_override || "" });
  }, [runtimeSettings]);

  useEffect(() => {
    fetchAiStatus().then(setLlmStatus).catch(() => {});
  }, []);

  async function handleTestLlm() {
    setTestingLlm(true); setLlmMsg("");
    try {
      const r = await fetchAiStatus();
      setLlmStatus(r);
      setLlmMsg(r?.effective_status === "ready" ? "اتصال ناجح" : "غير متاح");
    } catch (e) { setLlmMsg(e.message || "اختبار فشل."); }
    finally { setTestingLlm(false); }
  }

  async function handleSaveAlpaca() {
    setSavingAlpaca(true); setAlpacaMsg("");
    try {
      const r = await saveAlpacaSettings({ enabled: alpacaForm.enabled, provider: "alpaca", paper: alpacaForm.paper, api_key: alpacaForm.apiKey || undefined, secret_key: alpacaForm.secretKey || undefined, url_override: alpacaForm.urlOverride });
      setAlpacaMsg(r.detail || "Saved."); setAlpacaForm((p) => ({ ...p, apiKey: "", secretKey: "" })); await refreshData();
    } catch (e) { setAlpacaMsg(e.message || "Save failed."); }
    finally { setSavingAlpaca(false); }
  }

  async function handleTestAlpaca() {
    setTestingAlpaca(true); setAlpacaMsg("");
    try { const r = await testAlpacaSettings(); setAlpacaMsg(r.detail || (r.ok ? "Test passed." : "Test failed.")); }
    catch (e) { setAlpacaMsg(e.message || "Test failed."); }
    finally { setTestingAlpaca(false); }
  }

  const controlPlane = runtimeSettings?.control_plane;
  const processSummary = controlPlane?.process;
  const orchestrationSummary = controlPlane?.orchestration;
  const envBootstrap = controlPlane?.environment_bootstrap;
  const jobCounts = useMemo(() => {
    const counts = { running: 0, pending: 0, completed: 0, failed: 0 };
    for (const j of recentJobs) { const k = String(j.status || "").toLowerCase(); if (counts[k] !== undefined) counts[k]++; }
    return counts;
  }, [recentJobs]);

  const jobColumns = useMemo(() => [
    { accessorKey: "job_id", header: "ID" },
    { accessorKey: "type", header: "النوع" },
    { accessorKey: "status", header: "الحالة", cell: ({ row }) => <StatusBadge label={row.original.status} tone={toneForState(row.original.status)} dot={false} /> },
    { accessorKey: "progress", header: "%" },
    { accessorKey: "created_at", header: "الإنشاء" },
  ], []);

  return (
    <PageFrame
      title="الإعدادات"
      description="حالة المنصة، إعدادات الذكاء، والوسيط."
      eyebrow="النظام"
      headerActions={
        <>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => refreshData().catch(() => {})} disabled={settingsLoading}>
            تحديث
          </button>
          <StatusBadge label={healthStatus.status || "checking"} tone={toneForState(healthStatus.status)} />
        </>
      }
    >
      <ErrorBanner message={settingsError} />

      {/* System Health */}
      <SectionCard title="حالة النظام" description="صحة المنصة والخدمات الرئيسية.">
        {settingsLoading ? <LoadingSkeleton lines={4} /> : (
          <SummaryStrip items={[
            { label: "API Base", value: getApiBaseUrl() },
            { label: "Backend", value: healthStatus.status, tone: toneForState(healthStatus.status) },
            { label: "Readiness", value: readinessStatus.status, tone: toneForState(readinessStatus.status) },
            { label: "Models", value: runtimeStatus.model, tone: toneForState(runtimeStatus.model) },
            { label: "Scheduler", value: runtimeStatus.scheduler, tone: toneForState(runtimeStatus.scheduler) },
            { label: "AI", value: runtimeStatus.ai, tone: toneForState(runtimeStatus.ai) },
            { label: "Broker", value: runtimeStatus.broker, tone: toneForState(runtimeStatus.broker) },
          ]} />
        )}
      </SectionCard>

      <div className="command-grid">
        {/* Runtime Info */}
        <SectionCard className="col-span-6" title="Runtime" description="أدوار التشغيل والبيئة.">
          {settingsLoading ? <LoadingSkeleton lines={3} /> : (
            <div className="settings-group">
              <div className="settings-row">
                <span className="settings-row-label">Server Role</span>
                <span className="settings-row-value">{processSummary?.server_role || "-"}</span>
              </div>
              <div className="settings-row">
                <span className="settings-row-label">Process Mode</span>
                <span className="settings-row-value">{processSummary?.process_mode || "-"}</span>
              </div>
              <div className="settings-row">
                <span className="settings-row-label">Scheduler Role</span>
                <span className="settings-row-value">{processSummary?.scheduler_runner_role || "-"}</span>
              </div>
              <div className="settings-row">
                <span className="settings-row-label">Environment</span>
                <span className="settings-row-value">{envBootstrap?.mode || "-"}</span>
              </div>
              <div className="settings-row">
                <span className="settings-row-label">CL State</span>
                <span className="settings-row-value">{orchestrationSummary?.continuous_learning?.runtime_state || "-"}</span>
              </div>
            </div>
          )}
        </SectionCard>

        {/* Ollama / LLM Status */}
        <SectionCard className="col-span-6" title="Ollama / AI" description="حالة محرك الذكاء الاصطناعي المحلي.">
          <div className="settings-group">
            <div className="settings-row">
              <span className="settings-row-label">المزوّد النشط</span>
              <span className="settings-row-value">{llmStatus?.active_provider || "-"}</span>
            </div>
            <div className="settings-row">
              <span className="settings-row-label">الحالة الفعلية</span>
              <StatusBadge label={llmStatus?.effective_status || "checking"} tone={llmStatus?.effective_status === "ready" ? "positive" : "warning"} />
            </div>
            <div className="settings-row">
              <span className="settings-row-label">Ollama</span>
              <StatusBadge label={llmStatus?.ollama?.status || "checking"} tone={llmStatus?.ollama?.status === "ready" ? "positive" : "warning"} />
            </div>
            <div className="settings-row">
              <span className="settings-row-label">النموذج</span>
              <span className="settings-row-value">{llmStatus?.ollama?.model || llmStatus?.openai?.model || "-"}</span>
            </div>
            {llmMsg && <div className="info-banner">{llmMsg}</div>}
            <div className="form-actions">
              <button className="btn btn-secondary btn-sm" onClick={handleTestLlm} disabled={testingLlm}>{testingLlm ? "..." : "اختبار الاتصال"}</button>
            </div>
          </div>
        </SectionCard>

        {/* Alpaca Broker */}
        <SectionCard className="col-span-6" title="Alpaca Broker" description="إعدادات وسيط التداول.">
          <div className="settings-group">
            <div className="settings-row">
              <span className="settings-row-label">مفعّل</span>
              <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input type="checkbox" checked={alpacaForm.enabled} onChange={(e) => setAlpacaForm((p) => ({ ...p, enabled: e.target.checked }))} />
                <span className="text-sm">{alpacaForm.enabled ? "نعم" : "لا"}</span>
              </label>
            </div>
            <div className="settings-row">
              <span className="settings-row-label">Paper Mode</span>
              <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input type="checkbox" checked={alpacaForm.paper} onChange={(e) => setAlpacaForm((p) => ({ ...p, paper: e.target.checked }))} />
                <span className="text-sm">{alpacaForm.paper ? "ورقي" : "حي"}</span>
              </label>
            </div>
            <div className="settings-row">
              <span className="settings-row-label">API Key</span>
              <input className="form-input" style={{ width: "220px" }} type="password" placeholder="PK..." value={alpacaForm.apiKey} onChange={(e) => setAlpacaForm((p) => ({ ...p, apiKey: e.target.value }))} />
            </div>
            <div className="settings-row">
              <span className="settings-row-label">Secret Key</span>
              <input className="form-input" style={{ width: "220px" }} type="password" placeholder="..." value={alpacaForm.secretKey} onChange={(e) => setAlpacaForm((p) => ({ ...p, secretKey: e.target.value }))} />
            </div>
            {alpacaMsg && <div className="info-banner">{alpacaMsg}</div>}
            <div className="form-actions">
              <button className="btn btn-primary btn-sm" onClick={handleSaveAlpaca} disabled={savingAlpaca}>{savingAlpaca ? "..." : "حفظ"}</button>
              <button className="btn btn-secondary btn-sm" onClick={handleTestAlpaca} disabled={testingAlpaca}>{testingAlpaca ? "..." : "اختبار"}</button>
            </div>
          </div>
        </SectionCard>

        {/* Jobs */}
        <SectionCard className="col-span-6" title="Background Jobs" description="آخر الوظائف الخلفية.">
          <SummaryStrip compact items={[
            { label: "Running", value: jobCounts.running, tone: jobCounts.running ? "warning" : "neutral" },
            { label: "Pending", value: jobCounts.pending },
            { label: "Completed", value: jobCounts.completed, tone: "positive" },
            { label: "Failed", value: jobCounts.failed, tone: jobCounts.failed ? "negative" : "neutral" },
          ]} />
          <div style={{ marginTop: "var(--space-3)" }}>
            {jobsLoading ? <LoadingSkeleton lines={3} /> : (
              <DataTable columns={jobColumns} data={recentJobs} emptyTitle="لا توجد وظائف" compact />
            )}
          </div>
        </SectionCard>
      </div>
    </PageFrame>
  );
}
