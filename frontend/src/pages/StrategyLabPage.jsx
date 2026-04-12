import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useSearchParams } from "react-router-dom";

import DecisionPanel from "../components/ui/DecisionPanel";
import PageFrame from "../components/ui/PageFrame";
import DataTable from "../components/ui/DataTable";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import JobRunPanel from "../components/ui/JobRunPanel";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import SectionCard from "../components/ui/SectionCard";
import TradingChart from "../components/ui/TradingChart";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import SymbolPicker from "../components/ui/SymbolPicker";
import useDecisionSurface from "../hooks/useDecisionSurface";
import useJobRunner from "../hooks/useJobRunner";
import {
  fetchGeneratedStrategyCandidates,
  fetchPromotionStatus,
  fetchStrategyLabHistory,
  runStrategyEvaluation,
} from "../lib/api";
import { strategyEvaluationSchema } from "../lib/forms";
import { t } from "../lib/i18n";


const ACTIVE_JOB_STATUSES = new Set(["pending", "running"]);
const TAB_KEYS = ["evaluation", "history", "candidates"];


export default function StrategyLabPage() {
  const todayIso = new Date().toISOString().slice(0, 10);
  const [searchParams] = useSearchParams();
  const [history, setHistory] = useState(null);
  const [generatedCandidates, setGeneratedCandidates] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [promotion, setPromotion] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [activeTab, setActiveTab] = useState("evaluation");
  const {
    currentJob,
    recentJobs,
    loadingRecent,
    submitting,
    error: jobError,
    submit,
  } = useJobRunner("strategy_evaluation", { recentLimit: 6 });

  const { control, register, handleSubmit, formState: { errors }, setValue, watch } = useForm({
    resolver: zodResolver(strategyEvaluationSchema),
    defaultValues: {
      instrument: "AAPL",
      startDate: "2024-01-01",
      endDate: todayIso,
      holdDays: 10,
      windows: 3,
    },
  });

  const watchedInstrument = String(watch("instrument") || "").trim().toUpperCase() || "AAPL";
  const watchedStartDate = watch("startDate");
  const watchedEndDate = watch("endDate");
  const {
    decision,
    loading: decisionLoading,
    error: decisionError,
    refreshDecision,
  } = useDecisionSurface({
    symbol: watchedInstrument,
    startDate: watchedStartDate,
    endDate: watchedEndDate,
    enabled: Boolean(watchedInstrument),
  });
  const generatedCount = generatedCandidates?.latest_candidates?.length ?? 0;
  const isWorking = submitting || ACTIVE_JOB_STATUSES.has(String(currentJob?.status || "").toLowerCase());

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
      setPageError(requestError.message || "Strategy lab failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadReferenceData().catch(() => {});
  }, []);

  useEffect(() => {
    const symbol = searchParams.get("symbol");
    const targetSymbol = symbol ? symbol.trim().toUpperCase() : "AAPL";
    setValue("instrument", targetSymbol, { shouldValidate: true });
  }, [searchParams, setValue]);

  useEffect(() => {
    if (currentJob?.status === "completed" && currentJob?.result) {
      setEvaluation(currentJob.result);
      loadReferenceData().catch(() => {});
      refreshDecision({ symbol: currentJob.result.instrument || watchedInstrument }).catch(() => {});
    }
    if (currentJob?.status === "failed") {
      setEvaluation(null);
    }
  }, [currentJob, refreshDecision, watchedInstrument]);

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

  async function onSubmit(values) {
    setPageError("");
    setEvaluation(null);
    await submit(() => runStrategyEvaluation({
      instrument: values.instrument.trim().toUpperCase(),
      start_date: values.startDate,
      end_date: values.endDate,
      hold_days: Number(values.holdDays),
      windows: Number(values.windows),
      include_modes: ["classic", "vectorbt", "ml", "dl", "ensemble"],
    }));
  }

  const chartSummaryItems = [
    { label: "الرمز", value: decision?.symbol || watchedInstrument, badge: "Instrument" },
    { label: "الموقف", value: decision?.stance || "-", tone: decision?.stance === "BUY" ? "accent" : decision?.stance === "SELL" ? "negative" : "warning" },
    { label: "الثقة", value: decision?.confidence ?? "-", badge: "%" },
    { label: "أفضل إعداد", value: decision?.best_setup || "-", badge: decision?.setup_type || "Setup" },
    { label: "أفضل استراتيجية", value: evaluation?.best_strategy || decision?.strategy_hooks?.latest_evaluation?.best_strategy || "-", badge: "Lab" },
  ];

  return (
    <PageFrame
      title="مختبر الاستراتيجية"
      description="مختبر productized يربط بين التقييمات، القرار القابل للشرح، والمرشحين المستمرين ضمن نفس مسار العمل."
      eyebrow="بحث الاستراتيجية"
      headerActions={<StatusBadge label={generatedCount ? `${generatedCount} مرشح` : "مختبر التقييم"} tone="accent" />}
    >
      {/* Lab Summary Metrics */}
      <SectionCard
        title="ملخص المختبر"
        description="حالة الترقية والمرشحين الآليين وسجل التقييم في نظرة واحدة."
      >
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : (
          <div className="result-grid">
            <MetricCard label="التشغيلات الموصى بها" value={promotion?.recommended?.length ?? 0} tone="info" />
            <MetricCard label="المرشحون النشطون" value={promotion?.active_candidates?.length ?? 0} tone="positive" />
            <MetricCard label="آخر تشغيل مرشح" value={generatedCandidates?.latest_run_id || "-"} />
            <MetricCard label="مرشحون مولّدون" value={generatedCount} tone={generatedCount > 0 ? "positive" : "neutral"} />
            <MetricCard label="صفوف السجل" value={history?.items?.length ?? 0} />
          </div>
        )}
      </SectionCard>

      {/* Evaluation Form */}
      <FilterBar
        title="تشغيل تقييم"
        description="أدخل الرمز والنطاق الزمني لتشغيل مقارنة جديدة عبر نظام jobs ثم راقب الملخص والنتيجة من نفس الصفحة."
        action={<StatusBadge label={isWorking ? "جارٍ التقييم" : "جاهز"} tone={isWorking ? "warning" : "neutral"} />}
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
                  onSelect={(item) => {
                    field.onChange(item.symbol);
                    refreshDecision({ symbol: item.symbol }).catch(() => {});
                  }}
                  placeholder="اختر الرمز الذي تريد تقييم الاستراتيجية عليه"
                  helperText="ابحث عن الرمز ثم شغّل المقارنة مباشرة."
                  error={errors.instrument?.message}
                />
              )}
            />
            <label className="field">
              <span>{t("Start Date")}</span>
              <input type="date" max={todayIso} {...register("startDate")} />
            </label>
            <label className="field">
              <span>{t("End Date")}</span>
              <input type="date" max={todayIso} {...register("endDate")} />
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
            <button className="btn btn-primary" type="submit" disabled={isWorking}>
              {isWorking ? "جارٍ التقييم..." : "تشغيل تقييم الاستراتيجية"}
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => refreshDecision({ symbol: watchedInstrument }).catch(() => {})}
              disabled={decisionLoading}
            >
              {decisionLoading ? "جارٍ تحديث القرار..." : "تحديث طبقة القرار"}
            </button>
          </div>
          <ErrorBanner message={pageError || jobError} />
        </form>
      </FilterBar>

      {/* Chart + Decision Panel in command-grid layout */}
      <div className="command-grid">
        <TradingChart
          className="col-span-7"
          title="مساحة عمل الاستراتيجية"
          description="الشارت والمناطق والمستويات مرتبطة مباشرة بمسار التقييم."
          decision={decision}
          summaryItems={chartSummaryItems}
          loading={decisionLoading}
          height={440}
        />
        <div className="col-span-5 strategy-side-stack">
          <DecisionPanel
            decision={decision}
            loading={decisionLoading}
            error={decisionError}
            title="قرار الأداة"
            description="لماذا هذه الأداة تستحق التقييم الآن، وما الذي يدعم أو يضعف الفكرة."
          />
          <JobRunPanel
            title="وظائف التقييم"
            description="قبول job، التقدم، وآخر تشغيلات التقييم المرسلة من هذه الصفحة."
            currentJob={currentJob}
            recentJobs={recentJobs}
            loadingRecent={loadingRecent}
            submitting={submitting}
            error={pageError || jobError}
          />
        </div>
      </div>

      {/* Tab Navigation */}
      <SectionCard
        title="نتائج المختبر"
        description="تنقل بين التقييم الحالي، السجل، والمرشحين المولّدين."
        action={
          <div className="tab-group">
            {TAB_KEYS.map((key) => (
              <button
                key={key}
                type="button"
                className={`btn ${activeTab === key ? "btn-primary" : "btn-ghost btn-xs"}`}
                onClick={() => setActiveTab(key)}
              >
                {key === "evaluation" ? "التقييم الحالي" : key === "history" ? "السجل" : "المرشحون"}
              </button>
            ))}
          </div>
        }
      >
        {/* Current Evaluation Tab */}
        {activeTab === "evaluation" && (
          <>
            {evaluation ? (
              <>
                <SummaryStrip
                  compact
                  items={[
                    { label: "أفضل استراتيجية", value: evaluation.best_strategy || "-", tone: "positive" },
                    { label: "الاستراتيجيات", value: evaluation.leaderboard?.length ?? 0 },
                    { label: "نوافذ Walk-Forward", value: evaluation.walk_forward?.length ?? 0, tone: (evaluation.walk_forward?.length ?? 0) > 0 ? "info" : "neutral" },
                    { label: "Config Hash", value: evaluation.config_hash ? evaluation.config_hash.slice(0, 12) : "-", badge: "Reproducibility" },
                    { label: "متتبع", value: evaluation.experiment_tracked ? "نعم" : "لا", tone: evaluation.experiment_tracked ? "accent" : "warning", badge: "MLflow" },
                    { label: "Run ID", value: evaluation.run_id ? evaluation.run_id.slice(0, 16) : "-" },
                  ]}
                />
                {evaluation.overfitting ? (
                  <div className="strategy-overfit-strip">
                    <div className="strategy-overfit-header">
                      <span className="strategy-overfit-title">تحليل الإفراط في التهيئة</span>
                      <StatusBadge label={evaluation.overfitting.overfit_flag ? "تحذير: إفراط" : "مقبول"} tone={evaluation.overfitting.overfit_flag ? "negative" : "positive"} />
                    </div>
                    <SummaryStrip
                      compact
                      items={[
                        { label: "درجة التهيئة", value: evaluation.overfitting.overfit_score ?? "-", tone: (evaluation.overfitting.overfit_score ?? 100) < 60 ? "negative" : "positive" },
                        { label: "تراجع OOS", value: evaluation.overfitting.oos_decay_pct != null ? `${evaluation.overfitting.oos_decay_pct}%` : "-", tone: Number(evaluation.overfitting.oos_decay_pct) > 30 ? "negative" : "positive" },
                        { label: "استقرار Win Rate", value: evaluation.overfitting.win_rate_stability ?? "-" },
                        { label: "عائد التدريب", value: evaluation.overfitting.train_return_pct != null ? `${evaluation.overfitting.train_return_pct}%` : "-" },
                        { label: "عائد OOS", value: evaluation.overfitting.oos_avg_return_pct != null ? `${evaluation.overfitting.oos_avg_return_pct}%` : "-" },
                      ]}
                    />
                  </div>
                ) : null}
                <DataTable
                  columns={leaderboardColumns}
                  data={evaluation.leaderboard || []}
                  emptyTitle="No comparison rows"
                  emptyDescription="Run a strategy evaluation to compare current modes."
                />
              </>
            ) : !isWorking ? (
              <EmptyState
                className="compact-empty"
                title={t("No strategy evaluation yet")}
                description={t("Run an evaluation to compare classic, VectorBT, and smart strategy paths.")}
              />
            ) : (
              <LoadingSkeleton lines={6} />
            )}
          </>
        )}

        {/* History Tab */}
        {activeTab === "history" && (
          <>
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
          </>
        )}

        {/* Generated Candidates Tab */}
        {activeTab === "candidates" && (
          <>
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
          </>
        )}
      </SectionCard>
    </PageFrame>
  );
}
