import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import PageFrame from "../components/ui/PageFrame";
import ChartCard from "../components/ui/ChartCard";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchBreadthOverview, fetchDynamicWatchlists, fetchEventsCalendar } from "../lib/api";
import { universePresetOptions, universePresetSizeOptions } from "../lib/forms";
import { t } from "../lib/i18n";


export default function BreadthPage() {
  const [breadth, setBreadth] = useState(null);
  const [watchlists, setWatchlists] = useState(null);
  const [events, setEvents] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const { register, handleSubmit, watch } = useForm({
    defaultValues: { preset: "ALL_US_EQUITIES", limit: 40 },
  });

  async function loadData(values = { preset: "ALL_US_EQUITIES", limit: 40 }) {
    setLoading(true);
    try {
      const [breadthData, watchlistData, eventData] = await Promise.all([
        fetchBreadthOverview({ preset: values.preset, limit: Number(values.limit || 40) }),
        fetchDynamicWatchlists({ preset: values.preset, limit: Number(values.limit || 24) }),
        fetchEventsCalendar({ symbols: ["AAPL", "MSFT", "NVDA", "SPY"], limit: 12 }),
      ]);
      setBreadth(breadthData);
      setWatchlists(watchlistData);
      setEvents(eventData);
    } catch (requestError) {
      setError(requestError.message || "Breadth overview failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function onSubmit(values) {
    setSubmitting(true);
    setError("");
    await loadData(values);
    setSubmitting(false);
  }

  const sectorOption = useMemo(() => {
    const ranking = breadth?.sector_rotation?.ranking || [];
    if (!ranking.length) {
      return null;
    }
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: ranking.map((row) => row.sector),
        axisLabel: { color: "#9bb0c9", rotate: 25 },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#9bb0c9" },
        splitLine: { lineStyle: { color: "rgba(148,163,184,0.12)" } },
      },
      series: [
        {
          type: "bar",
          data: ranking.map((row) => row.change_pct ?? 0),
          itemStyle: { color: "#22c55e", borderRadius: [10, 10, 0, 0] },
        },
      ],
    };
  }, [breadth]);

  const watchlistColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "change_pct", header: "Change %" },
      { accessorKey: "volume_ratio", header: "Volume Ratio" },
      { accessorKey: "strategy_mode", header: "Mode" },
      { accessorKey: "signal", header: "Signal" },
      { accessorKey: "confidence", header: "Confidence" },
    ],
    []
  );

  const eventColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "event_type", header: "Event" },
      { accessorKey: "event_at", header: "Event Time" },
      { accessorKey: "source", header: "Source" },
    ],
    []
  );

  return (
    <PageFrame
      title="Breadth & Sectors"
      description="Advance/decline breadth, sector rotation, dynamic watchlists, and event awareness for broader market context."
      eyebrow="Market Context"
      headerActions={<StatusBadge label="Breadth View" tone="accent" />}
    >
      <FilterBar
        title="Breadth Universe"
        description="Run the market breadth and sector rotation view over a shared universe preset."
        action={<StatusBadge label={submitting ? "Refreshing" : watch("preset")} tone={submitting ? "warning" : "subtle"} />}
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid form-grid-compact">
            <label className="field">
              <span>{t("Universe Preset")}</span>
              <select {...register("preset")}>
                {universePresetOptions.filter((item) => item.value !== "CUSTOM").map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("Universe Size")}</span>
              <select {...register("limit")}>
                {universePresetSizeOptions.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? "جارٍ التحديث..." : "تحديث الاتساع"}
            </button>
          </div>
          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      <div className="panel result-panel">
        <SectionHeader title="Breadth Summary" description="Advancers, decliners, highs/lows, and breadth ratio from the selected universe sample." />
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : breadth ? (
          <SummaryStrip
            items={[
              { label: "Sample Size", value: breadth.breadth?.sample_size ?? 0 },
              { label: "Advancers", value: breadth.breadth?.advancing ?? 0, tone: "accent" },
              { label: "Decliners", value: breadth.breadth?.declining ?? 0, tone: "warning" },
              { label: "Breadth Ratio", value: breadth.breadth?.breadth_ratio ?? 0 },
              { label: "New Highs", value: breadth.breadth?.new_highs_sample ?? 0 },
              { label: "New Lows", value: breadth.breadth?.new_lows_sample ?? 0 },
            ]}
          />
        ) : null}
      </div>

      {sectorOption ? (
        <ChartCard
          title="Sector Rotation"
          description="Relative strength ranking across major sector ETFs."
          option={sectorOption}
        />
      ) : null}

      <div className="panel result-panel">
        <SectionHeader title="Dynamic Watchlists" description="Momentum, unusual-volume, and signal-focused watchlists that refresh from backend intelligence." />
        {loading ? (
          <LoadingSkeleton lines={7} />
        ) : (
          <DataTable
            columns={watchlistColumns}
            data={[
              ...(watchlists?.momentum_leaders || []),
              ...(watchlists?.unusual_volume || []),
              ...(watchlists?.signal_focus || []),
            ]}
            emptyTitle="No watchlist rows"
            emptyDescription="Watchlist data will appear here after the breadth view refreshes."
          />
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader title="Upcoming Events" description="Event awareness is real only when the active provider can supply it." />
        {loading ? (
          <LoadingSkeleton lines={5} />
        ) : (
          <DataTable
            columns={eventColumns}
            data={events?.items || []}
            emptyTitle="No events available"
            emptyDescription={events?.note || "The active provider did not expose upcoming events."}
          />
        )}
      </div>
    </PageFrame>
  );
}
