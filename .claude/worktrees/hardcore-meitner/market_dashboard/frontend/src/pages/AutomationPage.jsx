import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/PageFrame";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchAutomationStatus, runAutomationJob } from "../api/platform";
import { automationRunSchema, universePresetOptions } from "../lib/forms";
import { t } from "../lib/i18n";


function statusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "running") return "accent";
  if (normalized === "error" || normalized === "failed") return "warning";
  return "subtle";
}


export default function AutomationPage() {
  const [status, setStatus] = useState(null);
  const [lastRun, setLastRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(automationRunSchema),
    defaultValues: {
      jobName: "autonomous_cycle",
      preset: "ALL_US_EQUITIES",
      dryRun: true,
    },
  });

  async function loadStatus() {
    setLoading(true);
    try {
      setStatus(await fetchAutomationStatus({ limit: 25 }));
    } catch (requestError) {
      setError(requestError.message || "Automation status failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  async function onSubmit(values) {
    setSubmitting(true);
    setError("");
    try {
      const result = await runAutomationJob({
        job_name: values.jobName,
        preset: values.preset,
        dry_run: Boolean(values.dryRun),
      });
      setLastRun(result);
      await loadStatus();
    } catch (requestError) {
      setError(requestError.message || "Automation job failed.");
    } finally {
      setSubmitting(false);
    }
  }

  const continuousRunColumns = useMemo(
    () => [
      { accessorKey: "run_id", header: "Run ID" },
      { accessorKey: "status", header: "Status" },
      { accessorKey: "stage", header: "Stage" },
      { accessorKey: "started_at", header: "Started" },
      { accessorKey: "completed_at", header: "Completed" },
      { accessorKey: "duration_seconds", header: "Duration (s)" },
    ],
    []
  );

  const automationRunColumns = useMemo(
    () => [
      { accessorKey: "job_name", header: "Job" },
      { accessorKey: "status", header: "Status" },
      { accessorKey: "dry_run", header: "Dry Run", cell: ({ row }) => (row.original.dry_run ? "Yes" : "No") },
      { accessorKey: "started_at", header: "Started" },
      { accessorKey: "duration_seconds", header: "Duration (s)" },
      { accessorKey: "detail", header: "Detail" },
    ],
    []
  );

  const engineState = status?.continuous_learning?.state || {};
  const marketData = status?.market_data || {};
  const recentArtifacts = status?.continuous_learning?.recent_artifacts || [];
  const bestCandidate = engineState?.latest_metrics?.best_candidate?.candidate_name || engineState?.best_strategy_name || "-";

  return (
    <PageFrame
      title="المراقبة والأتمتة"
      description="لوحة تشغيل مختصرة تركز على حالة التعلم المستمر وطبقة البيانات والمهام الضرورية فقط."
      eyebrow="التشغيل الذاتي"
      headerActions={<StatusBadge label={engineState.active_stage || "idle"} tone={statusTone(engineState.runtime_status)} />}
    >
      <SectionCard
        title="محرك التعلم المستمر"
        description="حالة المحرك، آخر نجاح، المرشح الأفضل، وأثره الحالي على المختبر."
        action={<StatusBadge label={engineState.runtime_status || "idle"} tone={statusTone(engineState.runtime_status)} />}
      >
        <ErrorBanner message={error} />
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : (
          <>
            <SummaryStrip
              compact
              items={[
                { label: "Desired", value: engineState.desired_state || "-" },
                { label: "Runtime", value: engineState.runtime_status || "-" },
                { label: "Stage", value: engineState.active_stage || "-" },
                { label: "Last Success", value: engineState.last_success_at || "-" },
                { label: "Next Cycle", value: engineState.next_cycle_at || "-" },
                { label: "Best Candidate", value: bestCandidate },
              ]}
            />
            {engineState.last_failure_reason ? (
              <div className="status-message warning">{engineState.last_failure_reason}</div>
            ) : null}
          </>
        )}
      </SectionCard>

      <SectionCard
        className="span-7"
        title="دورات التعلم الأخيرة"
        description="آخر تشغيلات المحرك مع المرحلة الحالية ومدة التنفيذ."
      >
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : (
          <DataTable
            columns={continuousRunColumns}
            data={status?.continuous_learning?.recent_runs || []}
            emptyTitle="No continuous-learning runs"
            emptyDescription="Continuous-learning runs will appear here once the engine starts cycling."
          />
        )}
      </SectionCard>

      <SectionCard
        className="span-5"
        title="طبقة البيانات"
        description="سلسلة المزودات الحالية مع المزود الأساسي وحالة التهيئة."
        action={<StatusBadge label={marketData.primary_provider || "-"} tone="accent" />}
      >
        {loading ? (
          <LoadingSkeleton lines={5} />
        ) : (
          <>
            <SummaryStrip
              compact
              items={[
                { label: "Primary", value: marketData.primary_provider || "-" },
                { label: "Fallbacks", value: (marketData.provider_chain || []).slice(1).join(" -> ") || "-" },
                { label: "Artifacts", value: recentArtifacts.length },
                { label: "Scheduler Jobs", value: status?.scheduler?.jobs?.length ?? 0 },
              ]}
            />
            <div className="dashboard-feed-list">
              {(marketData.providers || []).map((provider) => (
                <div className="dashboard-feed-item" key={provider.name}>
                  <div className="dashboard-feed-copy">
                    <strong>{provider.name}</strong>
                    <p>{provider.detail}</p>
                  </div>
                  <StatusBadge label={provider.configured ? "configured" : "not ready"} tone={provider.configured ? "subtle" : "warning"} />
                </div>
              ))}
            </div>
          </>
        )}
      </SectionCard>

      <SectionCard
        title="تشغيل يدوي"
        description="اترك المراقبة في الأعلى، واستخدم هذا القسم فقط عند الحاجة إلى تشغيل مهمة محددة."
        action={<StatusBadge label={submitting ? "Running" : "Manual"} tone={submitting ? "warning" : "subtle"} />}
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid form-grid-compact">
            <label className="field">
              <span>{t("Job")}</span>
              <select {...register("jobName")}>
                <option value="autonomous_cycle">الدورة الذاتية</option>
                <option value="market_cycle">دورة السوق</option>
                <option value="alert_cycle">دورة التنبيهات</option>
                <option value="breadth_cycle">دورة الاتساع</option>
                <option value="retrain_cycle">دورة إعادة التدريب</option>
                <option value="daily_summary">الملخص اليومي</option>
              </select>
              {errors.jobName ? <small className="field-error">{errors.jobName.message}</small> : null}
            </label>
            <label className="field">
              <span>{t("Universe Preset")}</span>
              <select {...register("preset")}>
                {universePresetOptions.filter((item) => item.value !== "CUSTOM").map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="field checkbox-field">
              <span>{t("Dry Run")}</span>
              <input type="checkbox" {...register("dryRun")} />
            </label>
          </div>
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? "جارٍ التشغيل..." : "تشغيل مهمة الأتمتة"}
            </button>
          </div>
          {lastRun ? (
            <SummaryStrip
              compact
              items={[
                { label: "Job", value: lastRun.job_name },
                { label: "Status", value: lastRun.status },
                { label: "Dry Run", value: lastRun.dry_run ? "yes" : "no" },
                { label: "Artifacts", value: lastRun.artifacts?.length ?? 0 },
              ]}
            />
          ) : null}
          <ErrorBanner message={error} />
        </form>
      </SectionCard>

      <SectionCard title="سجل التشغيل" description="سجل مختصر لتشغيلات الأتمتة العامة.">
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : (
          <DataTable
            columns={automationRunColumns}
            data={status?.automation?.recent_runs || []}
            emptyTitle="No automation runs"
            emptyDescription="Scheduled or manual automation runs will appear here."
          />
        )}
      </SectionCard>
    </PageFrame>
  );
}
