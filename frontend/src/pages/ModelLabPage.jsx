import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/ui/PageFrame";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import ResultCard from "../components/ui/ResultCard";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchTrainingDashboard, fetchTrainingWorkflowTemplates, startTrainingJob } from "../lib/api";
import { buildRecentDateRange } from "../lib/dateDefaults";
import { parseSymbolList, trainingSchema } from "../lib/forms";
import { t } from "../lib/i18n";


function formatTemplateSymbols(symbols) {
  return Array.isArray(symbols) && symbols.length ? symbols.join(", ") : "—";
}


export default function ModelLabPage() {
  const { startDate: defaultStartDate, todayIso } = buildRecentDateRange();
  const [dashboard, setDashboard] = useState(null);
  const [templatesPayload, setTemplatesPayload] = useState(null);
  const [lastTrainResult, setLastTrainResult] = useState(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [trainMode, setTrainMode] = useState("ml");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(trainingSchema),
    defaultValues: {
      symbolsText: "AAPL,MSFT,NVDA,SPY",
      startDate: defaultStartDate,
      endDate: todayIso,
      horizonDays: 5,
      runOptuna: false,
    },
  });

  async function refreshRuns() {
    setLoadingRuns(true);
    try {
      setDashboard(await fetchTrainingDashboard(25));
    } catch (requestError) {
      setError(requestError.message || "تعذر تحميل تشغيلات النماذج.");
    } finally {
      setLoadingRuns(false);
    }
  }

  async function refreshTemplates(modelType = trainMode) {
    setTemplatesLoading(true);
    try {
      const payload = await fetchTrainingWorkflowTemplates(modelType);
      setTemplatesPayload(payload);
      const items = Array.isArray(payload?.items) ? payload.items : [];
      setSelectedTemplateId((current) => (
        items.some((item) => item.template_id === current)
          ? current
          : String(payload?.default_template_id || items[0]?.template_id || "")
      ));
    } catch (requestError) {
      setError(requestError.message || "تعذر تحميل قوالب التدريب.");
    } finally {
      setTemplatesLoading(false);
    }
  }

  useEffect(() => {
    refreshRuns();
  }, []);

  useEffect(() => {
    refreshTemplates(trainMode).catch(() => {});
  }, [trainMode]);

  const templates = Array.isArray(templatesPayload?.items) ? templatesPayload.items : [];
  const selectedTemplate = useMemo(
    () => templates.find((item) => item.template_id === selectedTemplateId) || templates[0] || null,
    [selectedTemplateId, templates]
  );

  useEffect(() => {
    if (!selectedTemplate?.defaults) {
      return;
    }
    const defaults = selectedTemplate.defaults;
    setValue("symbolsText", formatTemplateSymbols(defaults.symbols), { shouldValidate: true });
    setValue("startDate", defaults.start_date || defaultStartDate, { shouldValidate: true });
    setValue("endDate", defaults.end_date || todayIso, { shouldValidate: true });
    setValue("horizonDays", Number(defaults.horizon_days || 5), { shouldValidate: true });
    setValue("runOptuna", Boolean(defaults.run_optuna), { shouldValidate: true });
  }, [selectedTemplate?.template_id, setValue, defaultStartDate, todayIso]);

  const columns = useMemo(
    () => [
      { accessorKey: "run_id", header: "معرّف التشغيل" },
      { accessorKey: "model_type", header: "النوع" },
      { accessorKey: "model_name", header: "النموذج" },
      { accessorKey: "status", header: "الحالة" },
      { accessorKey: "duration_seconds", header: "المدة (ث)" },
      {
        accessorKey: "metrics.validation_macro_f1",
        header: "F1 التحقق",
        cell: ({ row }) => row.original.metrics?.validation_macro_f1 ?? "-",
      },
      {
        accessorKey: "metrics.test_accuracy",
        header: "دقة الاختبار",
        cell: ({ row }) => row.original.metrics?.test_accuracy ?? "-",
      },
      {
        accessorKey: "artifact_path",
        header: "الـ Artifact",
        cell: ({ row }) => row.original.artifact_path || "-",
      },
      {
        accessorKey: "is_active",
        header: "نشط",
        cell: ({ row }) => (row.original.is_active ? "نعم" : "لا"),
      },
    ],
    []
  );

  const jobColumns = useMemo(
    () => [
      { accessorKey: "job_id", header: "معرّف المهمة" },
      { accessorKey: "model_type", header: "النوع" },
      { accessorKey: "status", header: "الحالة" },
      { accessorKey: "requested_at", header: "طُلبت في" },
      { accessorKey: "started_at", header: "بدأت في" },
      { accessorKey: "completed_at", header: "اكتملت في" },
      { accessorKey: "duration_seconds", header: "المدة (ث)" },
      {
        accessorKey: "result_summary",
        header: "النتائج",
        cell: ({ row }) =>
          row.original.result_summary?.validation_macro_f1 || row.original.result_summary?.test_accuracy
            ? `F1 ${row.original.result_summary?.validation_macro_f1 ?? "-"} | Acc ${row.original.result_summary?.test_accuracy ?? "-"}`
            : "-",
      },
      { accessorKey: "run_id", header: "معرّف التشغيل" },
      { accessorKey: "artifact_path", header: "الـ Artifact" },
      { accessorKey: "error_message", header: "الخطأ" },
    ],
    []
  );

  async function onSubmit(values) {
    setSubmitting(true);
    setError("");
    try {
      const workflowDefaults = selectedTemplate?.defaults || {};
      const payload = {
        model_type: trainMode,
        template_id: selectedTemplate?.template_id || null,
        symbols: parseSymbolList(values.symbolsText),
        start_date: values.startDate,
        end_date: values.endDate,
        horizon_days: values.horizonDays,
        buy_threshold: Number(workflowDefaults.buy_threshold ?? 0.02),
        sell_threshold: Number(workflowDefaults.sell_threshold ?? -0.02),
      };
      const data = await startTrainingJob(
        trainMode === "dl"
          ? {
              ...payload,
              sequence_length: Number(workflowDefaults.sequence_length ?? 20),
              epochs: Number(workflowDefaults.epochs ?? 8),
              hidden_size: Number(workflowDefaults.hidden_size ?? 48),
              learning_rate: Number(workflowDefaults.learning_rate ?? 0.001),
            }
          : {
              ...payload,
              run_optuna: Boolean(values.runOptuna),
              trial_count: Number(workflowDefaults.trial_count ?? 8),
            }
      );
      setLastTrainResult(data);
      await refreshRuns();
    } catch (requestError) {
      setError(requestError.message || "فشل طلب التدريب.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageFrame
      title="مختبر النماذج"
      description="درّب وافحص تشغيلات ML وDL المتوازية من دون تغيير محركات الإشارة الكلاسيكية."
      eyebrow="الذكاء"
      headerActions={<StatusBadge label={trainMode.toUpperCase()} tone="accent" />}
    >
      <FilterBar
        title="طلب التدريب"
        description="مهام تدريب في الخلفية لتحديث النماذج بأمان من دون تعطيل عملية الـ API."
        action={<StatusBadge label={submitting ? "جارٍ الإرسال" : "المنصة جاهزة"} tone={submitting ? "warning" : "subtle"} />}
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <label className="field">
            <span>وضع التدريب</span>
            <select value={trainMode} onChange={(event) => setTrainMode(event.target.value)}>
              <option value="ml">ML أساسي</option>
              <option value="dl">تعلم عميق</option>
            </select>
          </label>

          <label className="field">
            <span>Workflow</span>
            <select value={selectedTemplateId} onChange={(event) => setSelectedTemplateId(event.target.value)} disabled={templatesLoading || templates.length === 0}>
              {templates.map((item) => (
                <option key={item.template_id} value={item.template_id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          {templatesLoading ? (
            <LoadingSkeleton lines={3} />
          ) : selectedTemplate ? (
            <>
              <div className="info-banner">
                <strong>{selectedTemplate.label}</strong>
                <span>{selectedTemplate.description}</span>
              </div>
              <SummaryStrip
                compact
                items={[
                  { label: "الرموز", value: selectedTemplate.defaults?.symbols?.length ?? 0, detail: formatTemplateSymbols(selectedTemplate.defaults?.symbols), badge: "Universe" },
                  { label: "الأفق", value: selectedTemplate.defaults?.horizon_days ?? "-", badge: "Days" },
                  { label: "الشراء", value: selectedTemplate.defaults?.buy_threshold ?? "-", badge: "Threshold" },
                  { label: "البيع", value: selectedTemplate.defaults?.sell_threshold ?? "-", badge: "Threshold" },
                  { label: "Highlights", value: (selectedTemplate.highlights || []).join(" • ") || "-", badge: trainMode.toUpperCase() },
                ]}
              />
            </>
          ) : null}

          <label className="field">
            <span>{t("Symbols")}</span>
            <textarea className="field-textarea" {...register("symbolsText")} />
            {errors.symbolsText ? <small className="field-error">{errors.symbolsText.message}</small> : null}
          </label>

          <label className="field">
            <span>{t("Start Date")}</span>
            <input type="date" {...register("startDate")} />
          </label>

          <label className="field">
            <span>{t("End Date")}</span>
            <input type="date" {...register("endDate")} />
          </label>

          <label className="field">
            <span>أيام الأفق</span>
            <input type="number" min="1" {...register("horizonDays")} />
          </label>

          {trainMode === "ml" ? (
            <label className="field checkbox-field">
              <span>ضبط Optuna</span>
              <input type="checkbox" {...register("runOptuna")} />
            </label>
          ) : null}

          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? "جارٍ الإرسال..." : `بدء مهمة تدريب ${trainMode === "ml" ? "ML" : "DL"}`}
            </button>
          </div>

          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      <div className="panel result-panel">
        <SectionHeader
          title="لوحة حالة التدريب"
          description="ملخص الحالات الجارية والمنتهية وآخر تشغيلات ML وDL النشطة."
        />
        {loadingRuns ? (
          <LoadingSkeleton lines={5} />
        ) : dashboard ? (
          <>
            <SummaryStrip
              items={[
                { label: "منتظرة", value: dashboard.status_counts?.queued ?? 0 },
                { label: "قيد التشغيل", value: dashboard.status_counts?.running ?? 0, tone: "warning" },
                { label: "مكتملة", value: dashboard.status_counts?.completed ?? 0 },
                { label: "فاشلة", value: dashboard.status_counts?.failed ?? 0, tone: "warning" },
                { label: "أحدث ML", value: dashboard.latest_runs?.ml?.model_name || "-", badge: dashboard.latest_runs?.ml?.run_id || "ML" },
                { label: "أحدث DL", value: dashboard.latest_runs?.dl?.model_name || "-", badge: dashboard.latest_runs?.dl?.run_id || "DL" },
              ]}
            />
            <div className="result-grid">
              <ResultCard label="أحدث مهمة" value={dashboard.latest_job?.job_id || "-"} />
              <ResultCard label="آخر حالة" value={dashboard.latest_job?.status || "-"} />
              <ResultCard label="أحدث تشغيل" value={dashboard.latest_job?.run_id || "-"} />
              <ResultCard label="مرجع الـ Artifact" value={dashboard.latest_job?.artifact_path || "-"} />
            </div>
          </>
        ) : null}
      </div>

      <div className="panel result-panel">
        <SectionHeader
          title="آخر طلب تدريب"
          description="أحدث مهمة تدريب أُرسلت من هذه الصفحة إلى الخلفية."
        />
        {lastTrainResult ? (
          <>
            <SummaryStrip
              items={[
                { label: "معرّف المهمة", value: lastTrainResult.job?.job_id || "-" },
                { label: "نوع النموذج", value: lastTrainResult.job?.model_type || "-" },
                { label: "الحالة", value: lastTrainResult.job?.status || "-" },
                { label: "Workflow", value: lastTrainResult.workflow_template?.label || "-", badge: lastTrainResult.workflow_template?.template_id || "template" },
              ]}
            />
            <div className="result-grid">
              <ResultCard label="مقبول" value={lastTrainResult.accepted ? "نعم" : "لا"} />
              <ResultCard label="وضع التنفيذ" value="مهمة خلفية" />
              <ResultCard label="PID" value={lastTrainResult.job?.pid ?? "-"} />
            </div>
          </>
        ) : (
          <div className="empty-state">
            <strong>لا توجد مهمة تدريب مرسلة بعد</strong>
            <p>ابدأ مهمة تدريب في الخلفية لإنتاج مخرجات النماذج من دون تعطيل عملية الـ API الرئيسية.</p>
          </div>
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader
          title="مهام التدريب"
          description="المهام المنتظرة والجارية والمكتملة في الخلفية."
        />
        {loadingRuns ? <LoadingSkeleton lines={8} /> : <DataTable columns={jobColumns} data={dashboard?.jobs || []} emptyTitle="لا توجد مهام تدريب بعد" emptyDescription="ستظهر مهام التدريب هنا بعد إرسالها." />}
      </div>

      <div className="panel result-panel">
        <SectionHeader
          title="سجل النماذج"
          description="آخر تشغيلات ML وDL المسجلة في كتالوج النماذج."
        />
        {loadingRuns ? <LoadingSkeleton lines={8} /> : <DataTable columns={columns} data={[...(dashboard?.runs?.ml_runs || []), ...(dashboard?.runs?.dl_runs || [])]} emptyTitle="لا توجد تشغيلات نماذج بعد" emptyDescription="ستظهر تشغيلات النماذج المكتملة هنا بعد إنشائها." />}
      </div>
    </PageFrame>
  );
}
