import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import PageFrame from "../components/ui/PageFrame";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchAlertsCenter, runAlertsCycle } from "../lib/api";
import { universePresetOptions, universePresetSizeOptions } from "../lib/forms";
import { t } from "../lib/i18n";


export default function AlertsCenterPage() {
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const { register, handleSubmit } = useForm({
    defaultValues: {
      preset: "ALL_US_EQUITIES",
      limit: 30,
      dryRun: true,
    },
  });

  async function loadHistory() {
    setLoading(true);
    try {
      setHistory(await fetchAlertsCenter({ limit: 120 }));
    } catch (requestError) {
      setError(requestError.message || "Alert history failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHistory();
  }, []);

  async function onSubmit(values) {
    setSubmitting(true);
    setError("");
    try {
      await runAlertsCycle({
        preset: values.preset,
        limit: Number(values.limit || 30),
        dryRun: Boolean(values.dryRun),
      });
      await loadHistory();
    } catch (requestError) {
      setError(requestError.message || "Alert cycle failed.");
    } finally {
      setSubmitting(false);
    }
  }

  const columns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "strategy_mode", header: "Mode" },
      { accessorKey: "alert_type", header: "Alert" },
      { accessorKey: "severity", header: "Severity" },
      { accessorKey: "message", header: "Reason" },
      { accessorKey: "created_at", header: "Time" },
    ],
    []
  );

  const severityCounts = (history?.items || []).reduce((acc, item) => {
    const key = item.severity || "info";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  return (
    <PageFrame
      title="Alerts Center"
      description="Price, volume, signal-change, and unusual-move alerts with manual and scheduled refresh support."
      eyebrow="Alerts Engine"
      headerActions={<StatusBadge label="Monitoring" tone="accent" />}
    >
      <FilterBar
        title="Manual Alert Cycle"
        description="Run the additive alert engine on a universe preset without disturbing the current trading flows."
        action={<StatusBadge label={submitting ? "Running" : "Alert Ready"} tone={submitting ? "warning" : "subtle"} />}
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
                  <option key={value} value={value}>{value} رمز</option>
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
              {submitting ? "جارٍ التشغيل..." : "تشغيل التنبيهات"}
            </button>
          </div>
          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      <div className="panel result-panel">
        <SectionHeader title="Alert Summary" description="Severity mix from the persisted local alert history." />
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : (
          <SummaryStrip
            items={[
              { label: "Total Alerts", value: history?.count ?? 0 },
              { label: "Critical", value: severityCounts.critical ?? 0, tone: "warning" },
              { label: "Warning", value: severityCounts.warning ?? 0, tone: "warning" },
              { label: "Info", value: severityCounts.info ?? 0 },
            ]}
          />
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader title="Alert History" description="Recent alerts with severity and reasons for faster triage." />
        {loading ? (
          <LoadingSkeleton lines={7} />
        ) : (
          <DataTable
            columns={columns}
            data={history?.items || []}
            emptyTitle="No alerts recorded"
            emptyDescription="Run the alert engine or let scheduler jobs populate this history."
          />
        )}
      </div>
    </PageFrame>
  );
}
