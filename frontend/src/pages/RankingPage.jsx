import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/ui/PageFrame";
import CandidateCard from "../components/ui/CandidateCard";
import DataTable from "../components/ui/DataTable";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import JobRunPanel from "../components/ui/JobRunPanel";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionCard from "../components/ui/SectionCard";
import SignalBadge from "../components/ui/SignalBadge";
import SymbolMultiPicker from "../components/ui/SymbolMultiPicker";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import useJobRunner from "../hooks/useJobRunner";
import { fetchRanking, fetchUniversePresetSymbols, scanSymbols } from "../lib/api";
import {
  parseSymbolList,
  symbolListSchema,
  universePresetOptions,
  universePresetSizeOptions,
} from "../lib/forms";
import { t } from "../lib/i18n";


const ACTIVE_JOB_STATUSES = new Set(["pending", "running"]);


export default function RankingPage() {
  const todayIso = new Date().toISOString().slice(0, 10);
  const [result, setResult] = useState(null);
  const [presetLoading, setPresetLoading] = useState(false);
  const [presetInfo, setPresetInfo] = useState(null);
  const [pageError, setPageError] = useState("");
  const [mode, setMode] = useState("ranking");
  const [searchParams] = useSearchParams();
  const {
    currentJob,
    recentJobs,
    loadingRecent,
    submitting,
    error: jobError,
    submit,
  } = useJobRunner("ranking_scan_batch", { recentLimit: 6 });

  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
    watch,
  } = useForm({
    resolver: zodResolver(symbolListSchema),
    defaultValues: {
      symbolsText: "AAPL,MSFT,NVDA,SPY",
      startDate: "2024-01-01",
      endDate: todayIso,
      universePreset: "CUSTOM",
      presetLimit: "50",
    },
  });

  useEffect(() => {
    const symbol = searchParams.get("symbol");
    if (symbol) {
      setValue("symbolsText", symbol.trim().toUpperCase(), { shouldValidate: true });
    }
    const urlMode = searchParams.get("mode");
    if (urlMode === "scan") {
      setMode("scan");
    }
  }, [searchParams, setValue]);

  useEffect(() => {
    if (currentJob?.status === "completed" && currentJob?.result) {
      setResult(currentJob.result);
    }
    if (currentJob?.status === "failed") {
      setResult(null);
    }
  }, [currentJob]);

  const watchedPreset = watch("universePreset");
  const requestedSymbols = parseSymbolList(watch("symbolsText")).length;
  const isWorking = submitting || ACTIVE_JOB_STATUSES.has(String(currentJob?.status || "").toLowerCase());

  const items = result?.items || [];
  const longItems = items.filter((item) => String(item.signal || "").toUpperCase() === "BUY");
  const shortItems = items.filter((item) => String(item.signal || "").toUpperCase() === "SELL");
  const overallItems = items.filter((item) => String(item.signal || "").toUpperCase() !== "ERROR");

  const columns = useMemo(
    () => [
      { accessorKey: "rank", header: "Rank" },
      { accessorKey: "instrument", header: "Instrument" },
      {
        accessorKey: "signal",
        header: "Signal",
        cell: ({ row }) => <SignalBadge signal={row.original.signal} />,
      },
      { accessorKey: "confidence", header: "Confidence" },
      {
        accessorKey: "best_setup",
        header: "Best Setup",
        cell: ({ row }) => row.original.best_setup || "-",
      },
      {
        accessorKey: "setup_type",
        header: "Setup Type",
        cell: ({ row }) => row.original.setup_type || "-",
      },
      {
        id: "score",
        header: "Score",
        cell: ({ row }) => row.original.enhanced_combined_score ?? row.original.combined_score ?? "-",
      },
      {
        accessorKey: "signal_quality",
        header: "الجودة",
        cell: ({ row }) => {
          const q = row.original.signal_quality;
          if (!q) return "-";
          const color = q === "HIGH" ? "var(--color-positive-text)" : q === "LOW" ? "var(--color-negative-text)" : "var(--color-warning-text)";
          return <span style={{ color, fontWeight: 600 }}>{q}</span>;
        },
      },
      {
        accessorKey: "signal_confidence",
        header: "ثقة الإشارة",
        cell: ({ row }) => row.original.signal_confidence != null ? `${row.original.signal_confidence}%` : "-",
      },
    ],
    []
  );

  async function onSubmit(values) {
    setPageError("");
    setResult(null);
    if (mode === "scan") {
      await submit(() => scanSymbols({
        symbols: parseSymbolList(values.symbolsText),
        start_date: values.startDate,
        end_date: values.endDate,
      }));
    } else {
      await submit(() => fetchRanking({
        symbols: parseSymbolList(values.symbolsText),
        start_date: values.startDate,
        end_date: values.endDate,
      }));
    }
  }

  async function loadUniversePreset() {
    if (watchedPreset === "CUSTOM") {
      setPresetInfo(null);
      return;
    }
    setPresetLoading(true);
    setPageError("");
    try {
      const data = await fetchUniversePresetSymbols({
        preset: watchedPreset,
        limit: Number(watch("presetLimit") || 50),
      });
      setValue("symbolsText", data.symbols.join(","), { shouldValidate: true, shouldDirty: true });
      setPresetInfo(data);
    } catch (requestError) {
      setPresetInfo(null);
      setPageError(requestError.message || "Universe preset load failed.");
    } finally {
      setPresetLoading(false);
    }
  }

  const summary = result?.summary || {};

  const pageTitle = mode === "scan" ? "فحص السوق" : "لوحة الترتيب";
  const pageDescription = mode === "scan"
    ? "الآن بنفس دورة jobs المقبولة: ترسل الفحص، تراقب التقدم، ثم تعود النتيجة المرتبة من دون تجميد الواجهة."
    : "لوحة ranking متوافقة بالكامل مع نظام jobs: إرسال واضح، تتبع آخر التشغيلات، ثم تسليم المرشحين بنفس منطق الترتيب الحالي.";
  const filterBarTitle = mode === "scan" ? "مدخلات الفحص" : "مدخلات الترتيب";
  const filterBarDescription = mode === "scan"
    ? "حمّل universe preset جاهزاً أو ابنِ قائمتك يدوياً بالـ symbol picker الموحد ثم شغّل الفحص كخلفية قابلة للتتبع."
    : "استخدم preset واسع أو ابْنِ قائمتك يدوياً بنفس symbol picker الموحد، ثم أرسل ranking scan كتشغيل خلفي قابل للتتبع.";
  const submitButtonLabel = mode === "scan" ? "فحص" : "تحديث الترتيب";
  const submitButtonLabelLoading = mode === "scan" ? "جارٍ الفحص..." : "جارٍ التحديث...";

  return (
    <PageFrame
      title={pageTitle}
      description={pageDescription}
      eyebrow={mode === "scan" ? "بحث قوائم المتابعة" : "ترتيب الإشارات"}
      headerActions={<StatusBadge label={`${requestedSymbols} رمز`} tone={mode === "scan" ? "subtle" : "accent"} />}
    >
      <FilterBar
        title={filterBarTitle}
        description={filterBarDescription}
        action={<StatusBadge label={isWorking ? (mode === "scan" ? "جارٍ الفحص" : "جارٍ التحديث") : (presetLoading ? "جارٍ تحميل الكون" : (mode === "scan" ? "جاهز" : "لوحة جاهزة"))} tone={isWorking || presetLoading ? "warning" : "subtle"} />}
      >
        <div className="mode-toggle" style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
          <button
            type="button"
            className={`toggle-button ${mode === "ranking" ? "active" : ""}`}
            onClick={() => setMode("ranking")}
            style={{
              padding: "var(--space-2) var(--space-4)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              backgroundColor: mode === "ranking" ? "var(--color-primary)" : "transparent",
              color: mode === "ranking" ? "white" : "inherit",
              cursor: "pointer",
            }}
          >
            الترتيب
          </button>
          <button
            type="button"
            className={`toggle-button ${mode === "scan" ? "active" : ""}`}
            onClick={() => setMode("scan")}
            style={{
              padding: "var(--space-2) var(--space-4)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              backgroundColor: mode === "scan" ? "var(--color-primary)" : "transparent",
              color: mode === "scan" ? "white" : "inherit",
              cursor: "pointer",
            }}
          >
            فحص سريع
          </button>
        </div>

        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid">
            <label className="field">
              <span>{t("Universe Preset")}</span>
              <select {...register("universePreset")}>
                {universePresetOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span>{t("Preset Size")}</span>
              <select {...register("presetLimit")}>
                {universePresetSizeOptions.map((size) => (
                  <option key={size} value={size}>{size}</option>
                ))}
              </select>
            </label>

            <div className="field field-span-2">
              <SymbolMultiPicker
                label={t("Symbols")}
                symbols={parseSymbolList(watch("symbolsText"))}
                onChange={(symbols) => setValue("symbolsText", symbols.join(","), { shouldValidate: true, shouldDirty: true })}
                helperText="كوّن القائمة يدوياً أو استورد universe preset ثم انتقل فوراً إلى المرشحين الأعلى."
                error={errors.symbolsText?.message}
              />
            </div>

            <label className="field">
              <span>{t("Start Date")}</span>
              <input type="date" max={todayIso} {...register("startDate")} />
            </label>

            <label className="field">
              <span>{t("End Date")}</span>
              <input type="date" max={todayIso} {...register("endDate")} />
            </label>
          </div>

          <div className="form-actions">
            <button className="primary-button" type="button" disabled={presetLoading || watchedPreset === "CUSTOM"} onClick={loadUniversePreset}>
              {presetLoading ? "جارٍ تحميل الكون..." : "تحميل الكون"}
            </button>
            <button className="primary-button" type="submit" disabled={isWorking}>
              {isWorking ? submitButtonLabelLoading : submitButtonLabel}
            </button>
          </div>

          <ErrorBanner message={pageError || jobError} />
        </form>
      </FilterBar>

      <JobRunPanel
        className="span-5"
        title="وظائف الترتيب"
        description="قبول ranking scan، التقدم الحالي، وآخر التشغيلات القابلة للمراجعة."
        currentJob={currentJob}
        recentJobs={recentJobs}
        loadingRecent={loadingRecent}
        submitting={submitting}
        error={pageError || jobError}
      />

      <SectionCard
        className="span-7"
        title="ملخص الترتيب"
        description="ملخص سريع لحالة الطلب وأفضل مرشح كما عاد من خدمة الترتيب في الباك إند."
      >
        {result ? (
          <SummaryStrip
            items={[
              { label: "Total Symbols", value: summary.total_symbols ?? "-" },
              { label: "Successful Results", value: summary.successful_results ?? "-" },
              { label: "Top Pick", value: summary.top_pick || "-" },
              { label: "Universe", value: presetInfo?.label || "Custom Symbols" },
            ]}
          />
        ) : (
          <EmptyState
            title={t("No ranking data yet")}
            description={t("Refresh ranking to populate long, short, and overall candidate sections.")}
          />
        )}
      </SectionCard>

      <SectionCard
        title="أفضل فرص الشراء اليوم"
        description="مرشحو الشراء فقط، مع استبعاد حالات الاحتفاظ من هذه اللوحة."
      >
        {isWorking ? <LoadingSkeleton lines={5} /> : null}
        {!isWorking && longItems.length ? (
          <div className="candidate-grid premium-candidate-grid">
            {longItems.map((item, index) => (
              <CandidateCard key={`${item.instrument || "long"}-${index}`} item={item} />
            ))}
          </div>
        ) : !isWorking ? (
          <EmptyState
            title={t("No BUY candidates")}
            description={t("No long setups were returned for the current request.")}
          />
        ) : null}
      </SectionCard>

      <SectionCard
        title="أفضل فرص البيع اليوم"
        description="مرشحو البيع فقط، مع استبعاد حالات الاحتفاظ من هذه اللوحة."
      >
        {isWorking ? <LoadingSkeleton lines={5} /> : null}
        {!isWorking && shortItems.length ? (
          <div className="candidate-grid premium-candidate-grid">
            {shortItems.map((item, index) => (
              <CandidateCard key={`${item.instrument || "short"}-${index}`} item={item} />
            ))}
          </div>
        ) : !isWorking ? (
          <EmptyState
            title={t("No SELL candidates")}
            description={t("No short setups were returned for the current request.")}
          />
        ) : null}
      </SectionCard>

      <SectionCard
        title="المرشحون المرتبون"
        description="النتائج المرتبة الشاملة، ويمكن أن تتضمن حالات الاحتفاظ مع الحفاظ على منطق الترتيب الحالي."
      >
        {isWorking ? <LoadingSkeleton lines={8} /> : null}
        {!isWorking ? (
          <DataTable
            columns={columns}
            data={overallItems}
            emptyTitle="No overall ranked candidates"
            emptyDescription="No ranked items were returned for the current request."
          />
        ) : null}
      </SectionCard>
    </PageFrame>
  );
}
