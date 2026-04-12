import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/ui/PageFrame";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionCard from "../components/ui/SectionCard";
import SignalBadge from "../components/ui/SignalBadge";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import MetricCard from "../components/ui/MetricCard";
import TradingChart from "../components/ui/TradingChart";
import DecisionPanel from "../components/ui/DecisionPanel";
import SymbolPicker from "../components/ui/SymbolPicker";
import useDecisionSurface from "../hooks/useDecisionSurface";
import { analyzeSymbol, fetchSignalExplanation } from "../lib/api";
import { analyzeSchema } from "../lib/forms";
import { t } from "../lib/i18n";


function formatError(err) {
  const msg = String(err?.message || "").trim().toLowerCase();
  if (!msg) return "تعذر إكمال التحليل.";
  if (msg.includes("source data unavailable") || msg.includes("no local daily bar") || msg.includes("no data found"))
    return "بيانات هذا الرمز غير مكتملة. استخدم آخر جلسة تداول متاحة.";
  if (msg.includes("not enough data"))
    return "البيانات المتاحة غير كافية لإكمال التحليل.";
  return "تعذر إكمال التحليل. حاول مرة أخرى.";
}


export default function AnalyzePage() {
  const todayIso = new Date().toISOString().slice(0, 10);
  const [result, setResult] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchParams] = useSearchParams();

  const { control, register, handleSubmit, formState: { errors }, setValue, watch } = useForm({
    resolver: zodResolver(analyzeSchema),
    defaultValues: { symbol: "AAPL", startDate: "2024-01-01", endDate: todayIso },
  });

  const watchedSymbol = watch("symbol");
  const watchedStart = watch("startDate");
  const watchedEnd = watch("endDate");

  const { decision, loading: decisionLoading, error: decisionError } = useDecisionSurface({
    symbol: watchedSymbol,
    startDate: watchedStart,
    endDate: watchedEnd,
    enabled: Boolean(result),
  });

  // chartOption removed — TradingChart handles rendering internally from decision prop

  useEffect(() => {
    const symbol = searchParams.get("symbol");
    if (symbol) setValue("symbol", symbol.trim().toUpperCase(), { shouldValidate: true });
  }, [searchParams, setValue]);

  async function onSubmit(values) {
    setLoading(true);
    setError("");
    try {
      const instrument = values.symbol.trim().toUpperCase();
      const [analysisResult, explanationResult] = await Promise.allSettled([
        analyzeSymbol({ instrument, start_date: values.startDate, end_date: values.endDate }),
        fetchSignalExplanation({ symbol: instrument, start_date: values.startDate, end_date: values.endDate, include_dl: true, include_ensemble: true }),
      ]);
      if (analysisResult.status !== "fulfilled") throw analysisResult.reason;
      setResult(analysisResult.value);
      setExplanation(explanationResult.status === "fulfilled" ? explanationResult.value?.explanation : null);
    } catch (e) {
      setResult(null);
      setExplanation(null);
      setError(formatError(e));
    } finally {
      setLoading(false);
    }
  }

  const chartSummaryItems = result ? [
    { label: "الرمز", value: result.instrument, badge: "Analysis" },
    { label: "الإشارة", value: result.signal, tone: result.signal === "BUY" ? "positive" : result.signal === "SELL" ? "negative" : "warning" },
    { label: "الثقة", value: result.confidence ?? "-", badge: "%" },
    { label: "الإعداد", value: result.best_setup || "-" },
  ] : [];

  return (
    <PageFrame
      title="تحليل ذكي"
      description="تحليل شامل يبرز القرار والأدلة ومناطق السعر."
      eyebrow="الأبحاث"
      headerActions={result && <SignalBadge signal={result.signal} />}
    >
      {/* Analysis Form */}
      <SectionCard title="طلب التحليل" description="اختر الرمز والنطاق الزمني.">
        <form className="analyze-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid">
            <div className="field field-span-2">
              <Controller
                name="symbol"
                control={control}
                render={({ field }) => (
                  <SymbolPicker
                    label={t("Symbol")}
                    value={field.value}
                    onChange={field.onChange}
                    onSelect={(item) => field.onChange(item.symbol)}
                    placeholder="ابحث عن السهم"
                    error={errors.symbol?.message}
                  />
                )}
              />
            </div>
            <label className="field">
              <span>{t("Start Date")}</span>
              <input type="date" max={todayIso} {...register("startDate")} />
              {errors.startDate && <small style={{ color: "var(--color-negative-text)", fontSize: "var(--text-xs)" }}>{errors.startDate.message}</small>}
            </label>
            <label className="field">
              <span>{t("End Date")}</span>
              <input type="date" max={todayIso} {...register("endDate")} />
              {errors.endDate && <small style={{ color: "var(--color-negative-text)", fontSize: "var(--text-xs)" }}>{errors.endDate.message}</small>}
            </label>
          </div>
          <div className="form-actions">
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? "جارٍ التحليل..." : "تحليل"}
            </button>
          </div>
          <ErrorBanner message={error} />
        </form>
      </SectionCard>

      {loading && (
        <SectionCard title="جارٍ التحليل">
          <LoadingSkeleton lines={6} />
        </SectionCard>
      )}

      {result && (
        <>
          {/* Decision Surface + Chart */}
          <div className="command-grid">
            <TradingChart
              className="col-span-7"
              title="مساحة العمل"
              description="الرسم البياني والمناطق والمستويات."
              decision={decision}
              summaryItems={chartSummaryItems}
              loading={decisionLoading}
              height={460}
            />

            <DecisionPanel
              className="col-span-5"
              decision={decision}
              loading={decisionLoading}
              error={decisionError}
              title="القرار المهيكل"
              description="الموقف والأدلة والمخاطر والأهداف."
            />
          </div>

          {/* Quick Signal Summary */}
          <SectionCard
            title="لقطة التحليل"
            description="الإشارة الأساسية والمؤشرات الكمية."
            action={<SignalBadge signal={result.signal} />}
          >
            <SummaryStrip items={[
              { label: "Instrument", value: result.instrument },
              { label: "Signal", value: result.signal, tone: result.signal === "BUY" ? "positive" : "negative" },
              { label: "Enhanced", value: result.enhanced_signal || "-" },
              { label: "Best Setup", value: result.best_setup || "-" },
              { label: "Confidence", value: result.confidence ?? "-" },
              { label: "الجودة", value: result.signal_quality || "-", tone: result.signal_quality === "HIGH" ? "positive" : result.signal_quality === "LOW" ? "negative" : "warning" },
              { label: "Date", value: result.date ?? "-" },
            ]} />
          </SectionCard>

          {/* Scores */}
          <div className="command-grid">
            <SectionCard className="col-span-6" title="الدرجات الكمية" description="الطبقة الكلاسيكية.">
              <div className="result-grid">
                <MetricCard label="Technical Score" value={result.technical_score} tone="info" />
                <MetricCard label="Enhanced Score" value={result.enhanced_combined_score} tone="info" />
                <MetricCard label="Setup Type" value={result.setup_type || "-"} />
                <MetricCard label="MTF Score" value={result.mtf_score ?? "-"} />
                <MetricCard label="RS Score" value={result.rs_score ?? "-"} />
              </div>
            </SectionCard>

            <SectionCard className="col-span-6" title="طبقات النماذج" description="ML، DL، والتجميع.">
              {result.ai_error && <div className="warning-banner">{result.ai_error}</div>}
              <div className="result-grid">
                <MetricCard label="ML Signal" value={result.ml_output?.signal ?? "-"} tone={result.ml_output?.signal === "BUY" ? "positive" : "neutral"} />
                <MetricCard label="ML Confidence" value={result.ml_output?.confidence ?? "-"} />
                <MetricCard label="DL Signal" value={result.dl_output?.signal ?? "-"} tone={result.dl_output?.signal === "BUY" ? "positive" : "neutral"} />
                <MetricCard label="DL Confidence" value={result.dl_output?.confidence ?? "-"} />
                <MetricCard label="Smart Signal" value={result.ensemble_output?.signal ?? "-"} />
                <MetricCard label="Reasoning" value={result.ensemble_output?.reasoning ?? "-"} />
              </div>
            </SectionCard>
          </div>

          {/* Explanation */}
          <SectionCard title="شرح الإشارة" description="التفسير والعوامل الداعمة والمتعارضة.">
            {explanation ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                {explanation.summary && <div className="info-banner">{explanation.summary}</div>}
                <div className="result-grid">
                  <MetricCard label="Confidence Note" value={explanation.confidence_note || "-"} />
                  <MetricCard label="Supporting" value={(explanation.supporting_factors || []).join(", ") || "-"} />
                  <MetricCard label="Contradictions" value={(explanation.contradictory_factors || []).join(", ") || "-"} />
                  <MetricCard label="Invalidators" value={(explanation.invalidators || []).join(", ") || "-"} />
                </div>
              </div>
            ) : (
              <EmptyState title="لا يوجد شرح" description="سيظهر بعد اكتمال التحليل." />
            )}
          </SectionCard>

          {/* Signal Intelligence */}
          {(result.signal_confidence || result.signal_quality) && (
            <SectionCard title="ذكاء الإشارة" description="تحليل متقدم لجودة الإشارة وعوامل التأكيد.">
              <SummaryStrip items={[
                { label: "جودة الإشارة", value: result.signal_quality || "-", tone: result.signal_quality === "HIGH" ? "positive" : result.signal_quality === "LOW" ? "negative" : "warning" },
                { label: "ثقة الإشارة", value: result.signal_confidence != null ? `${result.signal_confidence}%` : "-", badge: "%" },
                { label: "التوصية", value: result.enhanced_recommendation || "-" },
              ]} />
              <div style={{ display: "flex", gap: "var(--space-4)", marginTop: "var(--space-4)", flexWrap: "wrap" }}>
                {result.confirmation_factors?.length > 0 && (
                  <div style={{ flex: "1 1 280px" }}>
                    <h4 style={{ fontSize: "var(--text-sm)", fontWeight: 600, marginBottom: "var(--space-2)", color: "var(--color-positive-text)" }}>عوامل التأكيد</h4>
                    <div className="tag-list">
                      {result.confirmation_factors.map((f, i) => (
                        <span className="tag-chip bullish-chip" key={`cf-${i}`}>{f}</span>
                      ))}
                    </div>
                  </div>
                )}
                {result.warning_factors?.length > 0 && (
                  <div style={{ flex: "1 1 280px" }}>
                    <h4 style={{ fontSize: "var(--text-sm)", fontWeight: 600, marginBottom: "var(--space-2)", color: "var(--color-warning-text)" }}>عوامل التحذير</h4>
                    <div className="tag-list">
                      {result.warning_factors.map((f, i) => (
                        <span className="tag-chip warning-chip" key={`wf-${i}`}>{f}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </SectionCard>
          )}
        </>
      )}

      {!result && !loading && !error && (
        <SectionCard title="النتيجة">
          <EmptyState
            title="لم يتم تحليل رمز بعد"
            description="أرسل رمزاً لبدء التحليل الشامل."
          />
        </SectionCard>
      )}
    </PageFrame>
  );
}
