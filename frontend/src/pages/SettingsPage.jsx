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
  fetchTelegramStatus,
  saveTelegramSettings,
  testTelegramConnection,
  fetchAutoTradingConfig,
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
  const [alpacaForm, setAlpacaForm] = useState({ enabled: false, paper: true, tradingMode: "cash", apiKey: "", secretKey: "", urlOverride: "", autoTrading: false, orderSubmission: false, cycleMinutes: 30 });

  // Telegram state
  const [telegramForm, setTelegramForm] = useState({ botToken: "", chatId: "" });
  const [telegramStatus, setTelegramStatus] = useState(null);
  const [telegramMsg, setTelegramMsg] = useState("");
  const [savingTelegram, setSavingTelegram] = useState(false);
  const [testingTelegram, setTestingTelegram] = useState(false);

  // Auto-trading status
  const [autoTradingInfo, setAutoTradingInfo] = useState(null);

  useEffect(() => {
    if (!runtimeSettings) return;
    setAlpacaForm({
      enabled: Boolean(runtimeSettings?.broker?.alpaca?.enabled),
      paper: Boolean(runtimeSettings?.broker?.alpaca?.paper ?? true),
      tradingMode: runtimeSettings?.broker?.trading_mode === "margin" ? "margin" : "cash",
      apiKey: "",
      secretKey: "",
      urlOverride: runtimeSettings?.broker?.alpaca?.url_override || "",
      autoTrading: Boolean(runtimeSettings?.broker?.auto_trading_enabled),
      orderSubmission: Boolean(runtimeSettings?.broker?.order_submission_enabled),
      cycleMinutes: Number(runtimeSettings?.broker?.auto_trading_cycle_minutes ?? 30),
    });
  }, [runtimeSettings]);

  useEffect(() => {
    fetchAiStatus().then(setLlmStatus).catch(() => {});
    fetchTelegramStatus().then(setTelegramStatus).catch(() => {});
    fetchAutoTradingConfig().then(setAutoTradingInfo).catch(() => {});
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
      const r = await saveAlpacaSettings({
        enabled: alpacaForm.enabled,
        provider: "alpaca",
        paper: alpacaForm.paper,
        trading_mode: alpacaForm.tradingMode,
        api_key: alpacaForm.apiKey || undefined,
        secret_key: alpacaForm.secretKey || undefined,
        url_override: alpacaForm.urlOverride,
        auto_trading_enabled: alpacaForm.autoTrading,
        order_submission_enabled: alpacaForm.orderSubmission,
        auto_trading_cycle_minutes: Number(alpacaForm.cycleMinutes || 30),
      });
      setAlpacaMsg(r.detail || "تم الحفظ بنجاح"); setAlpacaForm((p) => ({ ...p, apiKey: "", secretKey: "" })); await refreshData();
      fetchAutoTradingConfig().then(setAutoTradingInfo).catch(() => {});
    } catch (e) { setAlpacaMsg(e.message || "فشل الحفظ"); }
    finally { setSavingAlpaca(false); }
  }

  async function handleTestAlpaca() {
    setTestingAlpaca(true); setAlpacaMsg("");
    try { const r = await testAlpacaSettings(); setAlpacaMsg(r.detail || (r.ok ? "اختبار ناجح" : "فشل الاختبار")); }
    catch (e) { setAlpacaMsg(e.message || "فشل الاختبار"); }
    finally { setTestingAlpaca(false); }
  }

  async function handleSaveTelegram() {
    setSavingTelegram(true); setTelegramMsg("");
    try {
      const r = await saveTelegramSettings({
        bot_token: telegramForm.botToken,
        chat_id: telegramForm.chatId,
      });
      setTelegramMsg(r.detail || "تم حفظ اعدادات تيليجرام بنجاح");
      setTelegramForm({ botToken: "", chatId: "" });
      fetchTelegramStatus().then(setTelegramStatus).catch(() => {});
    } catch (e) { setTelegramMsg(e.message || "فشل حفظ اعدادات تيليجرام"); }
    finally { setSavingTelegram(false); }
  }

  async function handleTestTelegram() {
    setTestingTelegram(true); setTelegramMsg("");
    try {
      const r = await testTelegramConnection();
      setTelegramMsg(r.detail || (r.ok ? "تم ارسال رسالة تجريبية بنجاح" : "فشل ارسال الرسالة"));
    } catch (e) { setTelegramMsg(e.message || "فشل ارسال الرسالة التجريبية"); }
    finally { setTestingTelegram(false); }
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
      description="مساحة إعدادات موحدة لحالة المنصة، الذكاء، الوسيط، الإشعارات، والمهام الخلفية."
      eyebrow="Platform"
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
            { label: "عنوان API", value: getApiBaseUrl() },
            { label: "الخلفية", value: healthStatus.status, tone: toneForState(healthStatus.status) },
            { label: "الجاهزية", value: readinessStatus.status, tone: toneForState(readinessStatus.status) },
            { label: "النماذج", value: runtimeStatus.model, tone: toneForState(runtimeStatus.model) },
            { label: "الجدولة", value: runtimeStatus.scheduler, tone: toneForState(runtimeStatus.scheduler) },
            { label: "الذكاء", value: runtimeStatus.ai, tone: toneForState(runtimeStatus.ai) },
            { label: "الوسيط", value: runtimeStatus.broker, tone: toneForState(runtimeStatus.broker) },
          ]} />
        )}
      </SectionCard>

      {/* Auto-Trading Status Banner */}
      {autoTradingInfo && (
        <div className={`settings-banner ${autoTradingInfo.ready ? "settings-banner--positive" : "settings-banner--warning"}`}>
          <div className="settings-banner-header">
            <div className="settings-banner-title">
              <span className="settings-banner-dot" />
              <span style={{ fontWeight: 700, color: "var(--tv-text)", fontSize: 14 }}>
                التداول التلقائي: {autoTradingInfo.auto_trading_enabled ? (autoTradingInfo.ready ? "جاهز ونشط" : "مفعل (غير مكتمل)") : "معطل"}
              </span>
            </div>
            <div className="settings-banner-meta">
              <span>Alpaca: {autoTradingInfo.alpaca_configured ? "مفعل" : "غير مفعل"}</span>
              <span>الاوامر: {autoTradingInfo.order_submission_enabled ? "مفعل" : "معطل"}</span>
              <span>الوضع: {autoTradingInfo.alpaca_paper ? "ورقي" : "حقيقي"}</span>
              <span>النمط: {autoTradingInfo.trading_mode === "margin" ? "مارجن" : "كاش"}</span>
              <span>الدورة: {autoTradingInfo.cycle_minutes || 30} دقيقة</span>
            </div>
          </div>
        </div>
      )}

      <div className="command-grid">
        {/* Runtime Info */}
        <SectionCard className="col-span-6" title="بيئة التشغيل" description="ادوار التشغيل والبيئة.">
          {settingsLoading ? <LoadingSkeleton lines={3} /> : (
            <div className="settings-group">
              <div className="settings-row">
                <span className="settings-row-label">دور الخادم</span>
                <span className="settings-row-value">{processSummary?.server_role || "-"}</span>
              </div>
              <div className="settings-row">
                <span className="settings-row-label">وضع العملية</span>
                <span className="settings-row-value">{processSummary?.process_mode || "-"}</span>
              </div>
              <div className="settings-row">
                <span className="settings-row-label">دور المجدول</span>
                <span className="settings-row-value">{processSummary?.scheduler_runner_role || "-"}</span>
              </div>
              <div className="settings-row">
                <span className="settings-row-label">البيئة</span>
                <span className="settings-row-value">{envBootstrap?.mode || "-"}</span>
              </div>
              <div className="settings-row">
                <span className="settings-row-label">حالة التعلم المستمر</span>
                <span className="settings-row-value">{orchestrationSummary?.continuous_learning?.runtime_state || "-"}</span>
              </div>
            </div>
          )}
        </SectionCard>

        {/* Ollama / LLM Status */}
        <SectionCard className="col-span-6" title="Ollama / الذكاء" description="حالة محرك الذكاء الاصطناعي المحلي.">
          <div className="settings-group">
            <div className="settings-row">
              <span className="settings-row-label">المزود النشط</span>
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
              <span className="settings-row-value">{llmStatus?.ollama?.model || "-"}</span>
            </div>
            {llmMsg && <div className="info-banner">{llmMsg}</div>}
            <div className="form-actions">
              <button className="btn btn-secondary btn-sm" onClick={handleTestLlm} disabled={testingLlm}>{testingLlm ? "..." : "اختبار الاتصال"}</button>
            </div>
          </div>
        </SectionCard>

        {/* Alpaca Broker */}
        <SectionCard className="col-span-6" title="وسيط Alpaca" description="اعدادات وسيط التداول.">
          <div className="settings-group">
            <div className="settings-row">
              <span className="settings-row-label">مفعل</span>
              <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input type="checkbox" checked={alpacaForm.enabled} onChange={(e) => setAlpacaForm((p) => ({ ...p, enabled: e.target.checked }))} />
                <span className="text-sm">{alpacaForm.enabled ? "نعم" : "لا"}</span>
              </label>
            </div>
            <div className="settings-row">
              <span className="settings-row-label">الوضع الورقي</span>
              <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input type="checkbox" checked={alpacaForm.paper} onChange={(e) => setAlpacaForm((p) => ({ ...p, paper: e.target.checked }))} />
                <span className="text-sm">{alpacaForm.paper ? "ورقي" : "حي"}</span>
              </label>
            </div>
            <div className="settings-row">
              <span className="settings-row-label">نمط التداول</span>
              <select
                className="form-input"
                style={{ width: "180px" }}
                value={alpacaForm.tradingMode}
                onChange={(e) => setAlpacaForm((p) => ({ ...p, tradingMode: e.target.value }))}
              >
                <option value="cash">Cash Only</option>
                <option value="margin">Margin / Short</option>
              </select>
            </div>
            <div className="settings-row">
              <span className="settings-row-label">مفتاح API</span>
              <input className="form-input" style={{ width: "220px" }} type="password" placeholder="PK..." value={alpacaForm.apiKey} onChange={(e) => setAlpacaForm((p) => ({ ...p, apiKey: e.target.value }))} />
            </div>
            <div className="settings-row">
              <span className="settings-row-label">المفتاح السري</span>
              <input className="form-input" style={{ width: "220px" }} type="password" placeholder="..." value={alpacaForm.secretKey} onChange={(e) => setAlpacaForm((p) => ({ ...p, secretKey: e.target.value }))} />
            </div>
            <div className="settings-row" style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--space-3)", marginTop: "var(--space-2)" }}>
              <span className="settings-row-label" style={{ fontWeight: 600 }}>إرسال الأوامر</span>
              <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input type="checkbox" checked={alpacaForm.orderSubmission} onChange={(e) => setAlpacaForm((p) => ({ ...p, orderSubmission: e.target.checked }))} />
                <span className="text-sm">{alpacaForm.orderSubmission ? "مفعل" : "معطل"}</span>
              </label>
            </div>
            <div className="settings-row">
              <span className="settings-row-label" style={{ fontWeight: 600, color: "var(--accent-primary)" }}>التداول التلقائي</span>
              <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input type="checkbox" checked={alpacaForm.autoTrading} onChange={(e) => setAlpacaForm((p) => ({ ...p, autoTrading: e.target.checked }))} />
                <span className="text-sm" style={{ color: alpacaForm.autoTrading ? "var(--accent-success)" : "inherit" }}>{alpacaForm.autoTrading ? "مفعل" : "معطل"}</span>
              </label>
            </div>
            <div className="settings-row">
              <span className="settings-row-label">كل كم دقيقة يفحص السوق</span>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                <input
                  className="form-input"
                  style={{ width: "110px" }}
                  type="number"
                  min="1"
                  max="720"
                  step="1"
                  value={alpacaForm.cycleMinutes}
                  onChange={(e) => setAlpacaForm((p) => ({ ...p, cycleMinutes: e.target.value }))}
                />
                <span className="text-sm">دقيقة</span>
              </div>
            </div>
            {alpacaForm.autoTrading && (
              <div className="info-banner" style={{ background: "var(--surface-success, #e8f5e9)", borderRadius: 8, padding: "var(--space-2) var(--space-3)" }}>
                التداول التلقائي مفعل — النظام سيفحص السوق كل {Number(alpacaForm.cycleMinutes || 30)} دقيقة
                ويبدأ دورة التداول الورقي تلقائيًا على الفرص المكتشفة في البيئة التجريبية. نمط التنفيذ الحالي:{" "}
                <strong>{alpacaForm.tradingMode === "margin" ? "مارجن / شورت مسموح" : "كاش فقط"}</strong>.
              </div>
            )}
            {alpacaMsg && <div className="info-banner">{alpacaMsg}</div>}
            <div className="form-actions">
              <button className="btn btn-primary btn-sm" onClick={handleSaveAlpaca} disabled={savingAlpaca}>{savingAlpaca ? "..." : "حفظ"}</button>
              <button className="btn btn-secondary btn-sm" onClick={handleTestAlpaca} disabled={testingAlpaca}>{testingAlpaca ? "..." : "اختبار"}</button>
            </div>
          </div>
        </SectionCard>

        {/* Telegram Notifications */}
        <SectionCard className="col-span-6" title="اشعارات تيليجرام" description="ربط بوت تيليجرام لاستقبال اشعارات التداول والتنبيهات.">
          <div className="settings-group">
            <div className="settings-row">
              <span className="settings-row-label">الحالة</span>
              <StatusBadge
                label={telegramStatus?.configured ? "متصل" : "غير مفعل"}
                tone={telegramStatus?.configured ? "positive" : "neutral"}
              />
            </div>
            {telegramStatus?.configured && (
              <div className="settings-row">
                <span className="settings-row-label">البوت</span>
                <span className="settings-row-value" style={{ fontSize: 12 }}>{telegramStatus?.bot_username || "متصل"}</span>
              </div>
            )}
            <div className="settings-row">
              <span className="settings-row-label">رمز البوت</span>
              <input
                className="form-input"
                style={{ width: "280px" }}
                type="password"
                placeholder="123456:ABC-DEF..."
                value={telegramForm.botToken}
                onChange={(e) => setTelegramForm((p) => ({ ...p, botToken: e.target.value }))}
              />
            </div>
            <div className="settings-row">
              <span className="settings-row-label">معرّف المحادثة</span>
              <input
                className="form-input"
                style={{ width: "180px" }}
                type="text"
                placeholder="-100123456789"
                value={telegramForm.chatId}
                onChange={(e) => setTelegramForm((p) => ({ ...p, chatId: e.target.value }))}
              />
            </div>

            <div className="info-banner" style={{ background: "var(--surface-info, rgba(33,150,243,0.08))", borderRadius: 8, padding: "var(--space-2) var(--space-3)", fontSize: 12, lineHeight: 1.8 }}>
              <strong>انواع الاشعارات:</strong><br />
              1. اشارات التداول الجديدة<br />
              2. تنفيذ الاوامر على Alpaca<br />
              3. تفعيل وقف الخسارة المتحرك<br />
              4. ملخص التداول التلقائي<br />
              5. ملخص يومي للمحفظة<br />
              6. اشعار فتح السوق<br />
              7. تنبيهات الاسهم
            </div>

            {telegramMsg && <div className="info-banner">{telegramMsg}</div>}
            <div className="form-actions">
              <button className="btn btn-primary btn-sm" onClick={handleSaveTelegram} disabled={savingTelegram}>
                {savingTelegram ? "..." : "حفظ"}
              </button>
              <button className="btn btn-secondary btn-sm" onClick={handleTestTelegram} disabled={testingTelegram || !telegramStatus?.configured}>
                {testingTelegram ? "..." : "ارسال رسالة تجريبية"}
              </button>
            </div>
          </div>
        </SectionCard>

        {/* Jobs */}
        <SectionCard className="col-span-6" title="المهام الخلفية" description="اخر الوظائف الخلفية.">
          <SummaryStrip compact items={[
            { label: "قيد التشغيل", value: jobCounts.running, tone: jobCounts.running ? "warning" : "neutral" },
            { label: "بانتظار التنفيذ", value: jobCounts.pending },
            { label: "مكتملة", value: jobCounts.completed, tone: "positive" },
            { label: "فاشلة", value: jobCounts.failed, tone: jobCounts.failed ? "negative" : "neutral" },
          ]} />
          <div style={{ marginTop: "var(--space-3)" }}>
            {jobsLoading ? <LoadingSkeleton lines={3} /> : (
              <DataTable columns={jobColumns} data={recentJobs} emptyTitle="لا توجد وظائف" compact />
            )}
          </div>
        </SectionCard>

        {/* Trailing Stop Config */}
        <SectionCard className="col-span-6" title="وقف الخسارة المتحرك" description="اعدادات الوقف التلقائي للمراكز المفتوحة.">
          <div className="settings-group">
            <div className="settings-row">
              <span className="settings-row-label">النسبة الافتراضية</span>
              <span className="settings-row-value" style={{ fontWeight: 700, color: "#FF9800" }}>5.0%</span>
            </div>
            <div className="settings-row">
              <span className="settings-row-label">فترة المراقبة</span>
              <span className="settings-row-value">كل 5 دقائق</span>
            </div>
            <div className="settings-row">
              <span className="settings-row-label">الية العمل</span>
              <span className="settings-row-value" style={{ fontSize: 12 }}>يتتبع اعلى سعر — عند انخفاض 5% من القمة يغلق المركز تلقائيا</span>
            </div>
            <div className="info-banner" style={{ background: "rgba(255,152,0,0.08)", borderRadius: 8, padding: "var(--space-2) var(--space-3)", fontSize: 12 }}>
              وقف الخسارة المتحرك يعمل تلقائيا على كل المراكز الجديدة — يتم فحص الاسعار كل 5 دقائق، واذا انخفض السعر 5% من اعلى نقطة وصلها يتم اغلاق المركز وارسال اشعار تيليجرام
            </div>
          </div>
        </SectionCard>
      </div>
    </PageFrame>
  );
}
