import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/PageFrame";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import FilterBar from "../components/ui/FilterBar";
import ResultCard from "../components/ui/ResultCard";
import SectionCard from "../components/ui/SectionCard";
import SignalBadge from "../components/ui/SignalBadge";
import SymbolPicker from "../components/ui/SymbolPicker";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { analyzeSymbol, fetchSignalExplanation } from "../lib/api";
import { analyzeSchema } from "../lib/forms";
import { t } from "../lib/i18n";


function formatAnalyzeErrorMessage(requestError) {
  const message = String(requestError?.message || "").trim();
  const normalized = message.toLowerCase();

  if (!message) {
    return "تعذر إكمال التحليل الآن. حاول مرة أخرى بعد قليل.";
  }

  if (
    normalized.includes("source data unavailable")
    || normalized.includes("no local daily bar")
    || normalized.includes("no completed session")
    || normalized.includes("no data found")
  ) {
    return "بيانات هذا الرمز غير مكتملة لهذا اليوم بعد. استخدم آخر جلسة تداول متاحة أو جرّب مرة أخرى لاحقاً.";
  }

  if (normalized.includes("not enough data")) {
    return "البيانات المتاحة ضمن هذا النطاق غير كافية لإكمال التحليل لهذا الرمز.";
  }

  return "تعذر إكمال التحليل الآن. حاول مرة أخرى بعد قليل.";
}


export default function AnalyzePage() {
  const todayIso = new Date().toISOString().slice(0, 10);
  const [result, setResult] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchParams] = useSearchParams();

  const {
    control,
    register,
    handleSubmit,
    formState: { errors },
    setValue,
  } = useForm({
    resolver: zodResolver(analyzeSchema),
    defaultValues: {
      symbol: "AAPL",
      startDate: "2024-01-01",
      endDate: todayIso,
    },
  });

  useEffect(() => {
    const symbol = searchParams.get("symbol");
    if (symbol) {
      setValue("symbol", symbol.trim().toUpperCase(), { shouldValidate: true });
    }
  }, [searchParams, setValue]);

  async function onSubmit(values) {
    setLoading(true);
    setError("");

    try {
      const instrument = values.symbol.trim().toUpperCase();
      const [analysisResult, explanationResult] = await Promise.allSettled([
        analyzeSymbol({
          instrument,
          start_date: values.startDate,
          end_date: values.endDate,
        }),
        fetchSignalExplanation({
          symbol: instrument,
          start_date: values.startDate,
          end_date: values.endDate,
          include_dl: true,
          include_ensemble: true,
        }),
      ]);
      if (analysisResult.status !== "fulfilled") {
        throw analysisResult.reason;
      }
      setResult(analysisResult.value);
      setExplanation(
        explanationResult.status === "fulfilled"
          ? explanationResult.value?.explanation || null
          : null
      );
    } catch (requestError) {
      setResult(null);
      setExplanation(null);
      setError(formatAnalyzeErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageFrame
      title="تحليل سهم"
      description="تجربة تحليل أقصر تبرز القرار أولاً ثم تعرض ما يدعمه فقط."
      eyebrow="مساحة الأبحاث"
      headerActions={<StatusBadge label={result?.signal || "سهم واحد"} tone="accent" />}
    >
      <FilterBar
        title="طلب التحليل"
        description="اختر الرمز والنطاق الزمني ثم ابدأ التحليل من دون ضوضاء إضافية."
        action={<StatusBadge label={loading ? "جارٍ التحليل" : "جاهز"} tone={loading ? "warning" : "subtle"} />}
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid form-grid-compact">
            <Controller
              name="symbol"
              control={control}
              render={({ field }) => (
                <SymbolPicker
                  label={t("Symbol")}
                  value={field.value}
                  onChange={field.onChange}
                  onSelect={(item) => field.onChange(item.symbol)}
                  placeholder="ابحث عن السهم أو الشركة ثم اختر الرمز"
                  helperText="نفس أداة البحث المستخدمة في بقية المنصة."
                  error={errors.symbol?.message}
                />
              )}
            />

            <label className="field analyze-date-field">
              <span>{t("Start Date")}</span>
              <input className="analyze-date-input" type="date" max={todayIso} {...register("startDate")} />
              {errors.startDate ? <small className="field-error">{errors.startDate.message}</small> : null}
            </label>

            <label className="field analyze-date-field">
              <span>{t("End Date")}</span>
              <input className="analyze-date-input" type="date" max={todayIso} {...register("endDate")} />
              {errors.endDate ? <small className="field-error">{errors.endDate.message}</small> : null}
            </label>
          </div>

          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={loading}>
              {loading ? "جارٍ التحليل..." : "تحليل"}
            </button>
          </div>

          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      {loading ? (
        <SectionCard title="جارٍ التحليل" description="يتم تجهيز النتيجة وشرح الإشارة.">
          <LoadingSkeleton lines={6} />
        </SectionCard>
      ) : null}

      {result ? (
        <>
          <SectionCard
            title="لقطة القرار"
            description="ملخص سريع للإشارة والتاريخ والإعداد الأفضل قبل النزول إلى التفاصيل."
            action={<SignalBadge signal={result.signal} />}
          >
            <SummaryStrip
              compact
              items={[
                { label: "Instrument", value: result.instrument ?? "-" },
                { label: "Signal", value: <SignalBadge signal={result.signal} /> },
                { label: "Enhanced", value: <SignalBadge signal={result.enhanced_signal} /> },
                { label: "Best Setup", value: result.best_setup || "-" },
                { label: "Confidence", value: result.confidence ?? "-" },
                { label: "Date", value: result.date ?? "-" },
              ]}
            />
          </SectionCard>

          <SectionCard
            className="span-5"
            title="الدرجات الأساسية"
            description="الطبقة الكلاسيكية التي تقود النتيجة النهائية."
          >
            <div className="result-grid">
              <ResultCard label="Technical Score" value={result.technical_score} />
              <ResultCard label="Enhanced Score" value={result.enhanced_combined_score} />
              <ResultCard label="Setup Type" value={result.setup_type || "-"} />
              <ResultCard label="MTF Score" value={result.mtf_score ?? "-"} />
              <ResultCard label="RS Score" value={result.rs_score ?? "-"} />
            </div>
          </SectionCard>

          <SectionCard
            className="span-7"
            title="طبقات النماذج"
            description="مخرجات ML وDL والتجميع في مساحة واحدة مختصرة."
            action={<StatusBadge label={result.enhanced_signal || result.signal || "-"} tone="subtle" />}
          >
            {result.ai_error ? <div className="status-message warning">{result.ai_error}</div> : null}
            <div className="result-grid">
              <ResultCard label="ML Signal" value={result.ml_output?.signal ?? "-"} />
              <ResultCard label="ML Confidence" value={result.ml_output?.confidence ?? "-"} />
              <ResultCard label="ML Buy Prob" value={result.ml_output?.prob_buy ?? "-"} />
              <ResultCard label="DL Signal" value={result.dl_output?.signal ?? "-"} />
              <ResultCard label="DL Confidence" value={result.dl_output?.confidence ?? "-"} />
              <ResultCard label="Smart Signal" value={result.ensemble_output?.signal ?? "-"} />
              <ResultCard label="Smart Reasoning" value={result.ensemble_output?.reasoning ?? "-"} />
            </div>
          </SectionCard>

          <SectionCard
            title="شرح الإشارة"
            description="تفسير موجز للعوامل الداعمة والمخالفة ومتى تضعف الفكرة."
          >
            {explanation ? (
              <div className="result-grid">
                <ResultCard label="Summary" value={explanation.summary} />
                <ResultCard label="Confidence Note" value={explanation.confidence_note} />
                <ResultCard label="Supporting Factors" value={(explanation.supporting_factors || []).join(" | ")} />
                <ResultCard label="Contradictions" value={(explanation.contradictory_factors || []).join(" | ")} />
                <ResultCard label="Invalidators" value={(explanation.invalidators || []).join(" | ")} />
              </div>
            ) : (
              <EmptyState
                className="compact-empty"
                title={t("No explanation loaded")}
                description={t("The backend explanation layer will populate here after a completed analysis request.")}
              />
            )}
          </SectionCard>
        </>
      ) : !loading && !error ? (
        <SectionCard title="نتيجة التحليل" description="ستظهر النتيجة هنا بعد إرسال الطلب.">
          <EmptyState
            title={t("No analysis loaded yet")}
            description={t("Submit a symbol to fetch a ranked analysis payload from the backend.")}
          />
        </SectionCard>
      ) : null}
    </PageFrame>
  );
}
