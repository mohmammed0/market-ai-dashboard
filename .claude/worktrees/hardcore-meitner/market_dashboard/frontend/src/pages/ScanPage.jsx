import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/PageFrame";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionCard from "../components/ui/SectionCard";
import SignalBadge from "../components/ui/SignalBadge";
import SymbolMultiPicker from "../components/ui/SymbolMultiPicker";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchUniversePresetSymbols, scanSymbols } from "../lib/api";
import {
  parseSymbolList,
  symbolListSchema,
  universePresetOptions,
  universePresetSizeOptions,
} from "../lib/forms";
import { t } from "../lib/i18n";


export default function ScanPage() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [presetLoading, setPresetLoading] = useState(false);
  const [presetInfo, setPresetInfo] = useState(null);
  const [error, setError] = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
    setValue,
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

  const watchedSymbols = watch("symbolsText");
  const watchedPreset = watch("universePreset");
  const requestedSymbols = parseSymbolList(watchedSymbols).length;
  const items = result?.items || [];

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
      const data = await scanSymbols({
        symbols: parseSymbolList(values.symbolsText),
        start_date: values.startDate,
        end_date: values.endDate,
      });
      setResult(data);
    } catch (requestError) {
      setResult(null);
      setError(requestError.message || "Scan request failed.");
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
      title="فحص السوق"
      description="ابنِ قائمة متابعة فعلية من السوق الأمريكي الكامل أو من رموزك المختارة، ثم نفّذ الفحص المرتب عليها."
      eyebrow="بحث قوائم المتابعة"
      headerActions={<StatusBadge label={`${requestedSymbols} رمز`} tone="subtle" />}
    >
      <FilterBar
        title="مدخلات الفحص"
        description="حمّل universe preset جاهزاً أو ابنِ قائمتك يدوياً بالـ symbol picker الموحد ثم شغّل الفحص."
        action={<StatusBadge label={loading ? "جارٍ الفحص" : (presetLoading ? "جارٍ تحميل الكون" : "جاهز")} tone={loading || presetLoading ? "warning" : "subtle"} />}
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
                symbols={parseSymbolList(watchedSymbols)}
                onChange={(symbols) => setValue("symbolsText", symbols.join(","), { shouldValidate: true, shouldDirty: true })}
                helperText="أضف الرموز فردياً أو استوردها من preset؛ نفس التجربة مستخدمة في الترتيب والتداول الورقي."
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
              {loading ? "جارٍ الفحص..." : "فحص"}
            </button>
          </div>

          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      <SectionCard
        title="نتائج الفحص المرتبة"
        description="عرض جدول احترافي لنتائج الفحص المرتبة القادمة من الباك إند."
      >
        {result ? (
          <SummaryStrip
            items={[
              { label: "Total Symbols", value: summary.total_symbols ?? requestedSymbols },
              { label: "Successful Results", value: summary.successful_results ?? 0 },
              { label: "Top Pick", value: summary.top_pick || "-" },
              { label: "Universe", value: presetInfo?.label || "Custom Symbols" },
            ]}
          />
        ) : null}

        {loading ? <LoadingSkeleton lines={8} /> : null}

        {!loading ? (
          <DataTable
            columns={columns}
            data={items}
            emptyTitle="No ranked scan results"
            emptyDescription="Submit comma-separated symbols to load ranked scan output."
          />
        ) : null}
      </SectionCard>
    </PageFrame>
  );
}
