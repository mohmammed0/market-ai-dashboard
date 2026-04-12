import { useEffect, useState } from "react";

import PageFrame from "../components/PageFrame";
import ActionButton from "../components/ui/ActionButton";
import MetricCard from "../components/ui/MetricCard";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import { fetchAiStatus } from "../api/ai";
import { fetchBrokerStatus } from "../api/broker";
import { fetchIntelligenceStatus } from "../api/models";
import { fetchAutomationStatus, fetchHealth, fetchReadiness, fetchSchedulerStatus, getApiBaseUrl } from "../api/platform";
import {
  fetchRuntimeSettings,
  saveAlpacaSettings,
  saveOpenAISettings,
  testAlpacaSettings,
  testOpenAISettings,
} from "../api/settings";


function resolveSchedulerState(payload) {
  return payload?.runtime_state || (payload?.scheduler_running ? "running" : payload?.scheduler_enabled ? "idle" : "disabled");
}


function resolveBrokerState(payload) {
  if (payload?.connected) return "connected";
  if (!payload?.enabled || payload?.provider === "none") return "disabled";
  if (!payload?.sdk_installed) return "error";
  if (!payload?.configured) return "warning";
  return "ready";
}


export default function SettingsPage() {
  const [healthStatus, setHealthStatus] = useState({ status: "loading", detail: "Checking backend..." });
  const [readinessStatus, setReadinessStatus] = useState({ status: "loading", detail: "Checking readiness..." });
  const [runtimeStatus, setRuntimeStatus] = useState({
    model: "loading",
    scheduler: "loading",
    schedulerDetail: "Checking scheduler...",
    automation: "loading",
    continuousLearning: "loading",
    continuousLearningDetail: "Checking continuous learning...",
    ai: "loading",
    aiDetail: "Checking OpenAI...",
    broker: "loading",
    brokerDetail: "Checking broker status...",
  });
  const [runtimeSettings, setRuntimeSettings] = useState(null);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState("");
  const [openAiMessage, setOpenAiMessage] = useState("");
  const [alpacaMessage, setAlpacaMessage] = useState("");
  const [savingOpenAi, setSavingOpenAi] = useState(false);
  const [testingOpenAi, setTestingOpenAi] = useState(false);
  const [savingAlpaca, setSavingAlpaca] = useState(false);
  const [testingAlpaca, setTestingAlpaca] = useState(false);
  const [openAiForm, setOpenAiForm] = useState({ enabled: false, model: "gpt-5.4-mini", apiKey: "" });
  const [alpacaForm, setAlpacaForm] = useState({ enabled: false, paper: true, apiKey: "", secretKey: "", urlOverride: "" });

  function applyRuntimeSettings(data) {
    setRuntimeSettings(data);
    setOpenAiForm({
      enabled: Boolean(data?.openai?.enabled),
      model: data?.openai?.model || "gpt-5.4-mini",
      apiKey: "",
    });
    setAlpacaForm({
      enabled: Boolean(data?.broker?.alpaca?.enabled),
      paper: Boolean(data?.broker?.alpaca?.paper ?? true),
      apiKey: "",
      secretKey: "",
      urlOverride: data?.broker?.alpaca?.url_override || "",
    });
  }

  async function loadRuntimeConfiguration() {
    setSettingsLoading(true);
    setSettingsError("");
    try {
      const data = await fetchRuntimeSettings();
      applyRuntimeSettings(data);
    } catch (error) {
      setSettingsError(error.message || "تعذر تحميل إعدادات التشغيل.");
    } finally {
      setSettingsLoading(false);
    }
  }

  useEffect(() => {
    let active = true;

    fetchHealth()
      .then((data) => {
        if (active) {
          setHealthStatus({ status: data.status || "ok", detail: "Backend reachable" });
        }
      })
      .catch((error) => {
        if (active) {
          setHealthStatus({ status: "error", detail: error.message || "Backend unavailable" });
        }
      });

    fetchReadiness()
      .then((data) => {
        if (active) {
          setReadinessStatus({
            status: data.status || "ready",
            detail: data.database?.status === "ok" ? "Database ready" : data.database?.detail || "Database not ready",
          });
        }
      })
      .catch((error) => {
        if (active) {
          setReadinessStatus({ status: "error", detail: error.message || "Readiness unavailable" });
        }
      });

    fetchIntelligenceStatus()
      .then((data) => {
        if (active) {
          setRuntimeStatus((prev) => ({
            ...prev,
            model: data.ml_ready || data.dl_ready ? "ready" : "inactive",
          }));
        }
      })
      .catch(() => {});

    fetchSchedulerStatus()
      .then((data) => {
        if (active) {
          setRuntimeStatus((prev) => ({
            ...prev,
            scheduler: resolveSchedulerState(data),
            schedulerDetail: data.blocked_reason || `Jobs: ${data.jobs_count ?? 0}`,
          }));
        }
      })
      .catch(() => {});

    fetchAutomationStatus({ limit: 5 })
      .then((data) => {
        if (active) {
          setRuntimeStatus((prev) => ({
            ...prev,
            automation: data.automation?.recent_runs?.length ? "active" : "ready",
            continuousLearning: data.continuous_learning?.runtime?.runtime_state || "unknown",
            continuousLearningDetail:
              data.continuous_learning?.runtime?.blocked_reason
              || data.continuous_learning?.runtime?.owner?.worker_id
              || "Continuous learning status unavailable",
          }));
        }
      })
      .catch(() => {});

    fetchAiStatus()
      .then((data) => {
        if (active) {
          setRuntimeStatus((prev) => ({
            ...prev,
            ai: data.status || (data.enabled ? "ready" : "standby"),
            aiDetail: data.detail || "OpenAI status unavailable",
          }));
        }
      })
      .catch((error) => {
        if (active) {
          setRuntimeStatus((prev) => ({
            ...prev,
            ai: "error",
            aiDetail: error.message || "OpenAI status unavailable",
          }));
        }
      });

    fetchBrokerStatus()
      .then((data) => {
        if (active) {
          setRuntimeStatus((prev) => ({
            ...prev,
            broker: resolveBrokerState(data),
            brokerDetail: data.detail || "Broker status unavailable",
          }));
        }
      })
      .catch((error) => {
        if (active) {
          setRuntimeStatus((prev) => ({
            ...prev,
            broker: "error",
            brokerDetail: error.message || "Broker status unavailable",
          }));
        }
      });

    loadRuntimeConfiguration();

    return () => {
      active = false;
    };
  }, []);

  async function refreshSettingsAndStatuses() {
    await Promise.allSettled([
      loadRuntimeConfiguration(),
      fetchAiStatus().then((data) => {
        setRuntimeStatus((prev) => ({
          ...prev,
          ai: data.status || (data.enabled ? "ready" : "standby"),
          aiDetail: data.detail || "OpenAI status unavailable",
        }));
      }),
      fetchBrokerStatus().then((data) => {
        setRuntimeStatus((prev) => ({
          ...prev,
          broker: resolveBrokerState(data),
          brokerDetail: data.detail || "Broker status unavailable",
        }));
      }),
    ]);
  }

  async function handleSaveOpenAi() {
    setSavingOpenAi(true);
    setOpenAiMessage("");
    try {
      const response = await saveOpenAISettings({
        enabled: openAiForm.enabled,
        model: openAiForm.model,
        api_key: openAiForm.apiKey || undefined,
      });
      setOpenAiMessage(response.detail || "تم حفظ إعدادات OpenAI.");
      setOpenAiForm((prev) => ({ ...prev, apiKey: "" }));
      await refreshSettingsAndStatuses();
    } catch (error) {
      setOpenAiMessage(error.message || "تعذر حفظ إعدادات OpenAI.");
    } finally {
      setSavingOpenAi(false);
    }
  }

  async function handleClearOpenAiKey() {
    setSavingOpenAi(true);
    setOpenAiMessage("");
    try {
      const response = await saveOpenAISettings({
        enabled: openAiForm.enabled,
        model: openAiForm.model,
        clear_api_key: true,
      });
      setOpenAiMessage(response.detail || "تم حذف مفتاح OpenAI المحفوظ.");
      setOpenAiForm((prev) => ({ ...prev, apiKey: "" }));
      await refreshSettingsAndStatuses();
    } catch (error) {
      setOpenAiMessage(error.message || "تعذر حذف مفتاح OpenAI.");
    } finally {
      setSavingOpenAi(false);
    }
  }

  async function handleTestOpenAi() {
    setTestingOpenAi(true);
    setOpenAiMessage("");
    try {
      const response = await testOpenAISettings();
      setOpenAiMessage(response.detail || (response.ok ? "نجح اختبار OpenAI." : "فشل اختبار OpenAI."));
      await refreshSettingsAndStatuses();
    } catch (error) {
      setOpenAiMessage(error.message || "تعذر اختبار OpenAI.");
    } finally {
      setTestingOpenAi(false);
    }
  }

  async function handleSaveAlpaca() {
    setSavingAlpaca(true);
    setAlpacaMessage("");
    try {
      const response = await saveAlpacaSettings({
        enabled: alpacaForm.enabled,
        provider: "alpaca",
        paper: alpacaForm.paper,
        api_key: alpacaForm.apiKey || undefined,
        secret_key: alpacaForm.secretKey || undefined,
        url_override: alpacaForm.urlOverride,
      });
      setAlpacaMessage(response.detail || "تم حفظ إعدادات Alpaca.");
      setAlpacaForm((prev) => ({ ...prev, apiKey: "", secretKey: "" }));
      await refreshSettingsAndStatuses();
    } catch (error) {
      setAlpacaMessage(error.message || "تعذر حفظ إعدادات Alpaca.");
    } finally {
      setSavingAlpaca(false);
    }
  }

  async function handleClearAlpacaKeys() {
    setSavingAlpaca(true);
    setAlpacaMessage("");
    try {
      const response = await saveAlpacaSettings({
        enabled: alpacaForm.enabled,
        provider: "alpaca",
        paper: alpacaForm.paper,
        url_override: alpacaForm.urlOverride,
        clear_api_key: true,
        clear_secret_key: true,
      });
      setAlpacaMessage(response.detail || "تم حذف مفاتيح Alpaca المحفوظة.");
      setAlpacaForm((prev) => ({ ...prev, apiKey: "", secretKey: "" }));
      await refreshSettingsAndStatuses();
    } catch (error) {
      setAlpacaMessage(error.message || "تعذر حذف مفاتيح Alpaca.");
    } finally {
      setSavingAlpaca(false);
    }
  }

  async function handleTestAlpaca() {
    setTestingAlpaca(true);
    setAlpacaMessage("");
    try {
      const response = await testAlpacaSettings();
      setAlpacaMessage(response.detail || (response.ok ? "نجح اختبار Alpaca." : "فشل اختبار Alpaca."));
      await refreshSettingsAndStatuses();
    } catch (error) {
      setAlpacaMessage(error.message || "تعذر اختبار Alpaca.");
    } finally {
      setTestingAlpaca(false);
    }
  }

  const openAiSummary = runtimeSettings?.openai;
  const brokerSummary = runtimeSettings?.broker;
  const alpacaSummary = brokerSummary?.alpaca;
  const controlPlane = runtimeSettings?.control_plane;
  const processSummary = controlPlane?.process;
  const orchestrationSummary = controlPlane?.orchestration;
  const storageSummary = controlPlane?.storage;
  const envBootstrap = controlPlane?.environment_bootstrap;

  return (
    <PageFrame
      title="الإعدادات"
      description="إدارة مفاتيح OpenAI وAlpaca من داخل الواجهة، مع حالة تشغيل حقيقية وطبقة حفظ آمنة داخل التطبيق."
      eyebrow="إعدادات المنصة"
      headerActions={
        <>
          <ActionButton to="/operations" variant="secondary">العمليات</ActionButton>
          <StatusBadge label="تشغيلي" tone="accent" />
        </>
      }
    >
      <SectionCard
        className="settings-overview-card"
        title="ملخص التشغيل"
        description="حالة الوصول للباك إند وقاعدة البيانات والمهام الخلفية ومزودي الذكاء والوسيط."
      >
        <div className="summary-strip">
          <MetricCard label="رابط API" value={getApiBaseUrl()} detail="يستخدم نفس الأصل افتراضياً في الإنتاج." />
          <MetricCard label="سلامة الباك إند" value={healthStatus.status} detail={healthStatus.detail} tone="accent" />
          <MetricCard label="الجاهزية" value={readinessStatus.status} detail={readinessStatus.detail} tone={readinessStatus.status === "ready" ? "accent" : "warning"} />
          <MetricCard label="حالة النماذج" value={runtimeStatus.model} detail="جاهزية طبقة ML / DL الحالية." />
          <MetricCard label="المجدول" value={runtimeStatus.scheduler} detail={runtimeStatus.schedulerDetail} />
          <MetricCard label="الأتمتة" value={runtimeStatus.automation} detail="سجل تشغيل الدورة الذاتية." />
          <MetricCard label="التعلم المستمر" value={runtimeStatus.continuousLearning} detail={runtimeStatus.continuousLearningDetail} />
          <MetricCard label="الوسيط" value={runtimeStatus.broker} detail={runtimeStatus.brokerDetail} tone={runtimeStatus.broker === "connected" ? "accent" : runtimeStatus.broker === "error" || runtimeStatus.broker === "warning" ? "warning" : "default"} />
          <MetricCard label="OpenAI" value={runtimeStatus.ai} detail={runtimeStatus.aiDetail} tone={runtimeStatus.ai === "ready" ? "accent" : runtimeStatus.ai === "error" || runtimeStatus.ai === "warning" ? "warning" : "default"} />
        </div>
      </SectionCard>

      <SectionCard
        title="النظام وطبقة التخزين"
        description="الإعدادات المحفوظة من الواجهة تأخذ الأولوية على متغيرات البيئة، ولا يتم إرجاع القيم السرية الخام بعد الحفظ."
      >
        {settingsError ? <div className="status-message error">{settingsError}</div> : null}
        <div className="status-message">
          <strong>أولوية الإعدادات:</strong>
          يستخدم التطبيق الإعدادات المحفوظة من الواجهة أولاً، ثم يرجع إلى متغيرات البيئة كخيار احتياطي.
        </div>
        <div className="status-message warning">
          <strong>تنبيه أمني:</strong>
          إذا كنت استخدمت مفاتيح حقيقية سابقاً داخل `.env` أو على الخادم، فقم بتدويرها واستبدالها بعد هذا التحديث.
        </div>
        <div className="status-message">
          <strong>مخزن المفاتيح:</strong>
          {settingsLoading ? "جارٍ تحميل المسار..." : runtimeSettings?.key_store_path || "غير متاح"}.
        </div>
        <div className="summary-strip">
          <MetricCard label="الدور النشط" value={processSummary?.server_role || "-"} detail={processSummary?.process_mode || "غير متاح"} />
          <MetricCard label="المجدول" value={orchestrationSummary?.scheduler?.runtime_state || "-"} detail={orchestrationSummary?.scheduler?.blocked_reason || `Jobs ${orchestrationSummary?.scheduler?.jobs_count ?? 0}`} />
          <MetricCard label="التعلم المستمر" value={orchestrationSummary?.continuous_learning?.runtime_state || "-"} detail={orchestrationSummary?.continuous_learning?.owner?.worker_id || orchestrationSummary?.continuous_learning?.blocked_reason || "لا يوجد مالك نشط"} />
          <MetricCard label="قاعدة البيانات" value={storageSummary?.database?.path || storageSummary?.database?.driver || "-"} detail="المسار أو المحرك الفعلي قيد الاستخدام." />
        </div>
        <div className="status-message">
          <strong>تحميل البيئة:</strong>
          {envBootstrap?.mode || "غير متاح"} عبر {envBootstrap?.env_file_path || "بدون ملف .env"}.
        </div>
        <div className="status-message">
          <strong>مسارات التشغيل:</strong>
          artifacts: {storageSummary?.paths?.model_artifacts_dir || "-"} | logs: {storageSummary?.paths?.logs_dir || "-"} | cache: {storageSummary?.paths?.runtime_cache_dir || "-"}.
        </div>
      </SectionCard>

      <SectionCard
        title="OpenAI"
        description="أدخل المفتاح من الواجهة، ثم احفظه واختبره دون كشف القيمة الأصلية بعد التخزين."
        badge={<StatusBadge label={openAiSummary?.status || runtimeStatus.ai || "loading"} tone={openAiSummary?.runtime_enabled ? "accent" : "warning"} />}
      >
        <div className="form-grid">
          <label className="field checkbox-field">
            <span>تفعيل OpenAI</span>
            <input
              type="checkbox"
              checked={openAiForm.enabled}
              onChange={(event) => setOpenAiForm((prev) => ({ ...prev, enabled: event.target.checked }))}
            />
          </label>
          <label className="field">
            <span>النموذج</span>
            <input
              value={openAiForm.model}
              onChange={(event) => setOpenAiForm((prev) => ({ ...prev, model: event.target.value }))}
              placeholder="gpt-5.4-mini"
            />
          </label>
          <label className="field field-span-2">
            <span>مفتاح API الجديد</span>
            <input
              type="password"
              value={openAiForm.apiKey}
              onChange={(event) => setOpenAiForm((prev) => ({ ...prev, apiKey: event.target.value }))}
              placeholder="sk-..."
              autoComplete="new-password"
            />
          </label>
        </div>
        <div className="summary-strip">
          <MetricCard label="الحفظ الحالي" value={openAiSummary?.configured ? "موجود" : "غير محفوظ"} detail={openAiSummary?.api_key_masked || "لا يوجد مفتاح محفوظ"} />
          <MetricCard label="مصدر المفتاح" value={openAiSummary?.api_key_source || "-"} detail="ui_managed ثم environment ثم default." />
          <MetricCard label="مصدر التفعيل" value={openAiSummary?.enabled_source || "-"} detail={openAiSummary?.detail || "حالة OpenAI الحالية."} />
          <MetricCard label="SDK" value={openAiSummary?.sdk_installed ? "مثبت" : "غير مثبت"} detail={`Timeout ${openAiSummary?.timeout_seconds ?? 30}s`} />
        </div>
        {openAiMessage ? <div className={`status-message ${openAiSummary?.runtime_enabled ? "" : "warning"}`}>{openAiMessage}</div> : null}
        <div className="form-actions">
          <button className="primary-button" type="button" onClick={handleSaveOpenAi} disabled={savingOpenAi || settingsLoading}>
            {savingOpenAi ? "جارٍ الحفظ..." : "حفظ إعدادات OpenAI"}
          </button>
          <button className="secondary-button" type="button" onClick={handleTestOpenAi} disabled={testingOpenAi || settingsLoading}>
            {testingOpenAi ? "جارٍ الاختبار..." : "اختبار OpenAI"}
          </button>
          <button className="secondary-button" type="button" onClick={handleClearOpenAiKey} disabled={savingOpenAi || settingsLoading}>
            حذف المفتاح المحفوظ
          </button>
        </div>
      </SectionCard>

      <SectionCard
        title="الوسيط"
        description="حفظ مفاتيح الوسيط واختبار الاتصال من الواجهة، مع إبقاء التنفيذ الحي معطلاً افتراضياً."
        badge={<StatusBadge label={alpacaSummary?.status || runtimeStatus.broker || "loading"} tone={runtimeStatus.broker === "connected" ? "accent" : "warning"} />}
      >
        <div className="form-grid">
          <label className="field checkbox-field">
            <span>تفعيل Alpaca</span>
            <input
              type="checkbox"
              checked={alpacaForm.enabled}
              onChange={(event) => setAlpacaForm((prev) => ({ ...prev, enabled: event.target.checked }))}
            />
          </label>
          <label className="field">
            <span>وضع الحساب</span>
            <select
              value={alpacaForm.paper ? "paper" : "live"}
              onChange={(event) => setAlpacaForm((prev) => ({ ...prev, paper: event.target.value !== "live" }))}
            >
              <option value="paper">تجريبي Paper</option>
              <option value="live">مرئي فقط Live</option>
            </select>
          </label>
          <label className="field">
            <span>مفتاح Alpaca API</span>
            <input
              type="password"
              value={alpacaForm.apiKey}
              onChange={(event) => setAlpacaForm((prev) => ({ ...prev, apiKey: event.target.value }))}
              placeholder="PK..."
              autoComplete="new-password"
            />
          </label>
          <label className="field">
            <span>المفتاح السري لـ Alpaca</span>
            <input
              type="password"
              value={alpacaForm.secretKey}
              onChange={(event) => setAlpacaForm((prev) => ({ ...prev, secretKey: event.target.value }))}
              placeholder="..."
              autoComplete="new-password"
            />
          </label>
          <label className="field field-span-2">
            <span>رابط Alpaca اختياري</span>
            <input
              value={alpacaForm.urlOverride}
              onChange={(event) => setAlpacaForm((prev) => ({ ...prev, urlOverride: event.target.value }))}
              placeholder="اتركه فارغاً لاستخدام الإعداد الافتراضي"
            />
          </label>
        </div>
        <div className="summary-strip">
          <MetricCard label="مزود الوسيط" value={brokerSummary?.provider || "none"} detail={`المصدر: ${brokerSummary?.provider_source || "-"}`} />
          <MetricCard label="مفتاح Alpaca" value={alpacaSummary?.configured ? "موجود" : "غير محفوظ"} detail={alpacaSummary?.api_key_masked || "لا يوجد"} />
          <MetricCard label="إرسال الأوامر" value={brokerSummary?.order_submission_enabled ? "مفعل" : "معطل"} detail={`المصدر: ${brokerSummary?.order_submission_source || "-"}`} tone={brokerSummary?.order_submission_enabled ? "warning" : "default"} />
          <MetricCard label="التنفيذ الحي" value={brokerSummary?.live_execution_enabled ? "مفعل" : "معطل"} detail={`المصدر: ${brokerSummary?.live_execution_source || "-"}`} tone={brokerSummary?.live_execution_enabled ? "warning" : "accent"} />
        </div>
        <div className="status-message warning">
          <strong>حماية التنفيذ:</strong>
          اختيار وضع `live` هنا يغير سياق الاعتماد فقط، لكنه لا يفعّل التنفيذ الحي. يظل `Live Execution` معطلاً افتراضياً حتى لو كانت بيانات الاعتماد صحيحة.
        </div>
        {alpacaMessage ? <div className={`status-message ${runtimeStatus.broker === "connected" ? "" : "warning"}`}>{alpacaMessage}</div> : null}
        <div className="form-actions">
          <button className="primary-button" type="button" onClick={handleSaveAlpaca} disabled={savingAlpaca || settingsLoading}>
            {savingAlpaca ? "جارٍ الحفظ..." : "حفظ إعدادات Alpaca"}
          </button>
          <button className="secondary-button" type="button" onClick={handleTestAlpaca} disabled={testingAlpaca || settingsLoading}>
            {testingAlpaca ? "جارٍ الاختبار..." : "اختبار Alpaca"}
          </button>
          <button className="secondary-button" type="button" onClick={handleClearAlpacaKeys} disabled={savingAlpaca || settingsLoading}>
            حذف مفاتيح Alpaca
          </button>
        </div>
      </SectionCard>

      <SectionCard
        title="الحالة وبيئة التشغيل"
        description="ملاحظات تشغيلية مباشرة تساعد في فهم ما تغير في هذه النسخة."
      >
        <div className="status-message">
          أعطال الأخبار الخارجية لم تعد توقف مسار التحليل بالكامل. يمكن الآن لصفحات التحليل والفحص والترتيب
          إرجاع نتائج جزئية مع حقول بديلة للأخبار وملاحظة `ai_error` عند العمل في الوضع المتدهور.
        </div>
        <div className="status-message">
          التحليل لم يعد يعتمد على وجود `us_watchlist_source/` في الخادم فقط. عند غياب الملفات المحلية يستخدم
          التطبيق seed data متتبعة ثم يحاول جلب البيانات وإعادة تخزينها داخل `data/source_cache`.
        </div>
        <div className="status-message">
          تكامل الوسيط للقراءة فقط في هذه المرحلة. يبقى التداول التجريبي داخل المحاكي متاحاً حتى لو كان اتصال
          الوسيط معطلاً، كما يبقى التنفيذ الحي مطفأً افتراضياً خلف إعدادات صريحة.
        </div>
        <div className="status-message">
          تطبيق سطح المكتب المبني على PySide ما زال محفوظاً ويظل المسار الأكثر نضجاً حالياً، بينما تستمر منصة الويب
          بالاقتراب من نفس المستوى بدون كسر سلوكه الحالي.
        </div>
      </SectionCard>
    </PageFrame>
  );
}
