import { useCallback, useEffect, useState } from "react";

import {
  fetchAiStatus,
  fetchBrokerStatus,
  fetchHealth,
  fetchIntelligenceStatus,
  fetchJobs,
  fetchReadiness,
  fetchRuntimeSettings,
  fetchSchedulerStatus,
} from "../lib/api";


function resolveSchedulerState(payload) {
  return payload?.runtime_state || (payload?.scheduler_running ? "running" : payload?.scheduler_enabled ? "idle" : "disabled");
}


function resolveBrokerState(payload) {
  if (payload?.connected) return "connected";
  if (!payload?.enabled || payload?.provider === "none") return "disabled";
  if (!payload?.sdk_installed) return "error";
  if (!payload?.configured) return "warning";
  return "ready";
}


export default function useSettingsPageData() {
  const [healthStatus, setHealthStatus] = useState({ status: "loading", detail: "Checking backend..." });
  const [readinessStatus, setReadinessStatus] = useState({ status: "loading", detail: "Checking readiness..." });
  const [runtimeStatus, setRuntimeStatus] = useState({
    model: "loading",
    scheduler: "loading",
    schedulerDetail: "Checking scheduler...",
    ai: "loading",
    aiDetail: "Checking AI...",
    broker: "loading",
    brokerDetail: "Checking broker status...",
  });
  const [runtimeSettings, setRuntimeSettings] = useState(null);
  const [recentJobs, setRecentJobs] = useState([]);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState("");

  const refreshData = useCallback(async () => {
    setSettingsLoading(true);
    setJobsLoading(true);
    setSettingsError("");
    try {
      const [
        healthData,
        readinessData,
        intelligenceData,
        schedulerData,
        aiData,
        brokerData,
        runtimeData,
        jobsData,
      ] = await Promise.all([
        fetchHealth(),
        fetchReadiness(),
        fetchIntelligenceStatus(),
        fetchSchedulerStatus(),
        fetchAiStatus(),
        fetchBrokerStatus(),
        fetchRuntimeSettings(),
        fetchJobs({ limit: 20 }, { forceFresh: true, cacheTtlMs: 0 }),
      ]);

      setHealthStatus({ status: healthData.status || "ok", detail: "Backend reachable" });
      setReadinessStatus({
        status: readinessData.status || "ready",
        detail: readinessData.database?.status === "ok" ? "Database ready" : readinessData.database?.detail || "Database not ready",
      });
      setRuntimeStatus({
        model: intelligenceData.ml_ready || intelligenceData.dl_ready ? "ready" : "inactive",
        scheduler: resolveSchedulerState(schedulerData),
        schedulerDetail: schedulerData.blocked_reason || `Jobs: ${schedulerData.jobs_count ?? 0}`,
        ai: aiData.effective_status || "checking",
        aiDetail: aiData.effective_provider ? `Provider: ${aiData.effective_provider}` : "AI status unavailable",
        broker: resolveBrokerState(brokerData),
        brokerDetail: brokerData.detail || "Broker status unavailable",
      });
      setRuntimeSettings(runtimeData);
      setRecentJobs(jobsData?.items || []);
    } catch (requestError) {
      setSettingsError(requestError.message || "تعذر تحميل إعدادات التشغيل.");
    } finally {
      setSettingsLoading(false);
      setJobsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshData().catch(() => {});
  }, [refreshData]);

  return {
    healthStatus,
    readinessStatus,
    runtimeStatus,
    runtimeSettings,
    recentJobs,
    settingsLoading,
    jobsLoading,
    settingsError,
    refreshData,
  };
}
