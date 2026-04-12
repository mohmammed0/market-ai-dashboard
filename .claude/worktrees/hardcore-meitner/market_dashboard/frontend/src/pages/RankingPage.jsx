import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/PageFrame";
import CandidateCard from "../components/ui/CandidateCard";
import DataTable from "../components/ui/DataTable";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionCard from "../components/ui/SectionCard";
import SignalBadge from "../components/ui/SignalBadge";
import SymbolMultiPicker from "../components/ui/SymbolMultiPicker";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchRanking, fetchUniversePresetSymbols } from "../lib/api";
import {
  parseSymbolList,
  symbolListSchema,
  universePresetOptions,
  universePresetSizeOptions,
} from "../lib/forms";
import { t } from "../lib/i18n";


export default function RankingPage() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [presetLoading, setPresetLoading] = useState(false);
  const [presetInfo, setPresetInfo] = useState(null);
  const [error, setError] = useState("");
  const [searchParams] = useSearchParams();

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
      endDate: "2026-04-02",
      universePreset: "CUSTOM",
      presetLimit: "50",
    },
  });

  const watchedPreset = watch("universePreset");
  const requestedSymbols = parseSymbolList(watch("symbolsText")).length;

  useEffect(() => {
    const symbol = searchParams.get("symbol");
    if (symbol) {
      setValue("symbolsText", symbol.trim().toUpperCase(), { shouldValidate: true });
    }
  }, [searchParams, setValue]);

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
    ],
    []
  );

  async function onSubmit(values) {
    setLoading(true);
    setError("");

    try {
      const data = await fetchRanking({
        symbols: parseSymbolList(values.symbolsText),
        start_date: values.startDate,
        end_date: values.endDate,
      });
      setResult(data);
    } catch (requestError) {
      setResult(null);
      setError(requestError.message || "Ranking request failed.");
    } finally {
      setLoading(false);
    }
  }

  async function loadUniversePreset() {
    if (watchedPreset === "CUSTOM") {
      setPresetInfo(null);
      return;
    }
    setPresetLoading(true);
    setError("");
    try {
      const data = await fetchUniversePresetSymbols({
        preset: watchedPreset,
        limit: Number(watch("presetLimit") || 50),
      });
      setValue("symbolsText", data.symbols.join(","), { shouldValidate: true, shouldDirty: true });
      setPresetInfo(data);
    } catch (requestError) {
      setPresetInfo(null);
      setError(requestError.message || "Universe preset load failed.");
    } finally {
      setPresetLoading(false);
    }
  }

  const summary = result?.summary || {};

  return (
    <PageFrame
      title="لوحة الترتيب"
      description="حوّل الكون السوقي الواسع أو قائمتك المخصصة إلى لوحة مرشحين أوضح وأسهل في التنفيذ."
      eyebrow="ترتيب الإشارات"
      headerActions={<StatusBadge label={`${requestedSymbols} رمز`} tone="accent" />}
    >
      <FilterBar
        title="مدخلات الترتيب"
        description="استخدم preset واسع أو ابْنِ قائمتك يدوياً بنفس symbol picker الموحد، ثم حمّل أفضل المرشحين مباشرة."
        action={<StatusBadge label={loading ? "جارٍ التحديث" : (presetLoading ? "جارٍ تحميل الكون" : "لوحة جاهزة")} tone={loading || presetLoading ? "warning" : "subtle"} />}
      >
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
              <input type="date" {...register("startDate")} />
            </label>

            <label className="field">
              <span>{t("End Date")}</span>
              <input type="date" {...register("endDate")} />
            </label>
          </div>

          <div className="form-actions">
            <button className="primary-button" type="button" disabled={presetLoading || watchedPreset === "CUSTOM"} onClick={loadUniversePreset}>
              {presetLoading ? "جارٍ تحميل الكون..." : "تحميل الكون"}
            </button>
            <button className="primary-button" type="submit" disabled={loading}>
              {loading ? "جارٍ التحديث..." : "تحديث الترتيب"}
            </button>
          </div>

          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      <SectionCard
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
        {loading ? <LoadingSkeleton lines={5} /> : null}
        {!loading && longItems.length ? (
          <div className="candidate-grid premium-candidate-grid">
            {longItems.map((item, index) => (
              <CandidateCard key={`${item.instrument || "long"}-${index}`} item={item} />
            ))}
          </div>
        ) : !loading ? (
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
        {loading ? <LoadingSkeleton lines={5} /> : null}
        {!loading && shortItems.length ? (
          <div className="candidate-grid premium-candidate-grid">
            {shortItems.map((item, index) => (
              <CandidateCard key={`${item.instrument || "short"}-${index}`} item={item} />
            ))}
          </div>
        ) : !loading ? (
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
        {loading ? <LoadingSkeleton lines={8} /> : null}
        {!loading ? (
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
