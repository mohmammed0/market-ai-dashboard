import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/PageFrame";
import DataTable from "../components/ui/DataTable";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import SymbolPicker from "../components/ui/SymbolPicker";
import {
  fetchGeneratedStrategyCandidates,
  fetchPromotionStatus,
  fetchStrategyLabHistory,
  runStrategyEvaluation,
} from "../lib/api";
import { strategyEvaluationSchema } from "../lib/forms";
import { t } from "../lib/i18n";


export default function StrategyLabPage() {
  const todayIso = new Date().toISOString().slice(0, 10);
  const [history, setHistory] = useState(null);
  const [generatedCandidates, setGeneratedCandidates] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [promotion, setPromotion] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const { control, register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(strategyEvaluationSchema),
    defaultValues: {
      instrument: "AAPL",
      startDate: "2024-01-01",
      endDate: todayIso,
      holdDays: 10,
      windows: 3,
    },
  });

  async function loadReferenceData() {
    setLoading(true);
    try {
      const [historyData, promotionData, generatedData] = await Promise.all([
        fetchStrategyLabHistory({ limit: 20 }),
        fetchPromotionStatus(),
        fetchGeneratedStrategyCandidates({ limit: 8 }),
      ]);
      setHistory(historyData);
      setPromotion(promotionData);
      setGeneratedCandidates(generatedData);
    } catch (requestError) {
      setError(requestError.message || "Strategy lab failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadReferenceData();
  }, []);

  async function onSubmit(values) {
    setSubmitting(true);
    setError("");
    try {
      const payload = await runStrategyEvaluation({
        instrument: values.instrument.trim().toUpperCase(),
        start_date: values.startDate,
        end_date: values.endDate,
        hold_days: Number(values.holdDays),
        windows: Number(values.windows),
        include_modes: ["classic", "vectorbt", "ml", "dl", "ensemble"],
      });
      setEvaluation(payload);
      await loadReferenceData();
    } catch (requestError) {
      setError(requestError.message || "Strategy evaluation failed.");
    } finally {
      setSubmitting(false);
    }
  }

  const leaderboardColumns = useMemo(
    () => [
      { accessorKey: "strategy", header: "Strategy" },
      { accessorKey: "robust_score", header: "Robust Score" },
      { accessorKey: "total_return_pct", header: "Total Return %" },
      { accessorKey: "win_rate_pct", header: "Win Rate %" },
      { accessorKey: "avg_trade_return_pct", header: "Avg Trade %" },
      { accessorKey: "max_drawdown_pct", header: "Max Drawdown %" },
      { accessorKey: "confidence", header: "Confidence" },
    ],
    []
  );

  const historyColumns = useMemo(
    () => [
      { accessorKey: "run_id", header: "Run ID" },
      { accessorKey: "instrument", header: "Instrument" },
      { accessorKey: "status", header: "Status" },
      { accessorKey: "started_at", header: "Started" },
      { accessorKey: "completed_at", header: "Completed" },
    ],
    []
  );

  const generatedColumns = useMemo(
    () => [
      { accessorKey: "candidate_name", header: "Candidate" },
      { accessorKey: "family", header: "Family" },
      { accessorKey: "anchor_symbol", header: "Anchor Symbol" },
      { accessorKey: "score", header: "Score" },
      { accessorKey: "policy_weight", header: "Policy Weight" },
      { accessorKey: "live_bias", header: "Live Bias" },
      {
        accessorKey: "metrics.total_return_pct",
        header: "Total Return %",
        cell: ({ row }) => row.original?.metrics?.total_return_pct ?? "-",
      },
      {
        accessorKey: "metrics.win_rate_pct",
        header: "Win Rate %",
        cell: ({ row }) => row.original?.metrics?.win_rate_pct ?? "-",
      },
    ],
    []
  );

  const generatedCount = generatedCandidates?.latest_candidates?.length ?? 0;

  return (
    <PageFrame
      title="مختبر الاستراتيجية"
      description="عرض أقصر يضع المرشحين الآليين وآخر مقارنة في الواجهة ويؤخر التفاصيل التاريخية."
      eyebrow="بحث الاستراتيجية"
      headerActions={<StatusBadge label={generatedCount ? `${generatedCount} مرشح` : "مختبر التقييم"} tone="accent" />}
    >
      <SectionCard
        title="ملخص المختبر"
        description="حالة الترقية والمرشحين الآليين وسجل التقييم في نظرة واحدة."
      >
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : (
          <SummaryStrip
            compact
            items={[
              { label: "Recommended Runs", value: promotion?.recommended?.length ?? 0 },
              { label: "Active Candidates", value: promotion?.active_candidates?.length ?? 0 },
              { label: "Latest Candidate Run", value: generatedCandidates?.latest_run_id || "-" },
              { label: "Generated Candidates", value: generatedCount },
              { label: "History Rows", value: history?.items?.length ?? 0 },
            ]}
          />
        )}
      </SectionCard>

      <SectionCard
        className="span-5"
        title="تشغيل تقييم"
        description="أدخل الرمز والنطاق الزمني لتشغيل مقارنة جديدة."
        action={<StatusBadge label={submitting ? "جارٍ التقييم" : "جاهز"} tone={submitting ? "warning" : "subtle"} />}
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid form-grid-compact">
            <Controller
              name="instrument"
              control={control}
              render={({ field }) => (
                <SymbolPicker
                  label="الأداة"
                  value={field.value}
                  onChange={field.onChange}
                  onSelect={(item) => field.onChange(item.symbol)}
                  placeholder="اختر الرمز الذي تريد تقييم الاستراتيجية عليه"
                  helperText="ابحث عن الرمز ثم شغّل المقارنة مباشرة."
                  error={errors.instrument?.message}
                />
              )}
            />
            <label className="field">
              <span>{t("Start Date")}</span>
              <input type="date" {...register("startDate")} />
            </label>
            <label className="field">
              <span>{t("End Date")}</span>
              <input type="date" {...register("endDate")} />
            </label>
            <label className="field">
              <span>أيام الاحتفاظ</span>
              <input type="number" min="1" {...register("holdDays")} />
            </label>
            <label className="field">
              <span>نوافذ التقييم</span>
              <input type="number" min="2" max="6" {...register("windows")} />
            </label>
          </div>
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? "جارٍ التقييم..." : "تشغيل تقييم الاستراتيجية"}
            </button>
          </div>
          <ErrorBanner message={error} />
        </form>
      </SectionCard>

      <SectionCard
        className="span-7"
        title="أحدث مقارنة"
        description="آخر ترتيب متين للاستراتيجيات بعد تشغيل التقييم."
        action={<StatusBadge label={evaluation?.best_strategy || "بدون تقييم"} tone="subtle" />}
      >
        {evaluation ? (
          <>
            <SummaryStrip
              compact
              items={[
                { label: "Run ID", value: evaluation.run_id },
                { label: "Best Strategy", value: evaluation.best_strategy || "-" },
                { label: "Strategies", value: evaluation.leaderboard?.length ?? 0 },
              ]}
            />
            <DataTable
              columns={leaderboardColumns}
              data={evaluation.leaderboard || []}
              emptyTitle="No comparison rows"
              emptyDescription="Run a strategy evaluation to compare current modes."
            />
          </>
        ) : (
          <EmptyState
            className="compact-empty"
            title={t("No strategy evaluation yet")}
            description={t("Run an evaluation to compare classic, VectorBT, and smart strategy paths.")}
          />
        )}
      </SectionCard>

      <SectionCard
        title="مرشحون من المحرك المستمر"
        description="أفضل ما وصل من دورة التعلم المستمر إلى مختبر الاستراتيجية."
      >
        {loading ? (
          <LoadingSkeleton lines={5} />
        ) : generatedCount ? (
          <DataTable
            columns={generatedColumns}
            data={generatedCandidates.latest_candidates}
            emptyTitle="No generated candidates"
            emptyDescription="The continuous learning engine will publish its latest ranked candidates here."
          />
        ) : (
          <EmptyState
            className="compact-empty"
            title={t("No generated candidates yet")}
            description={t("Continuous learning candidates will appear here after the first completed autonomous cycle.")}
          />
        )}
      </SectionCard>

      <SectionCard title="سجل التقييم" description="آخر تشغيلات المختبر المحفوظة بدون تفاصيل زائدة.">
        {loading ? (
          <LoadingSkeleton lines={7} />
        ) : (
          <DataTable
            columns={historyColumns}
            data={history?.items || []}
            emptyTitle="No evaluations yet"
            emptyDescription="Evaluation history will appear here after runs are completed."
          />
        )}
      </SectionCard>
    </PageFrame>
  );
}
