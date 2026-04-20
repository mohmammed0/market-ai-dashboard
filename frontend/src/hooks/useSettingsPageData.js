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
  const runtimeState = payload?.runtime_state;
  if (runtimeState === "delegated") {
    return isSchedulerActiveViaOwner(payload) ? "running" : "delegated";
  }
  if (runtimeState === "blocked" && isSchedulerActiveViaOwner(payload)) {
    return "running";
  }
  if (isSchedulerDelegated(payload)) {
    return isSchedulerActiveViaOwner(payload) ? "running" : "delegated";
  }
  return runtimeState || (payload?.scheduler_running ? "running" : payload?.scheduler_enabled ? "idle" : "disabled");
}

function isSchedulerDelegated(payload) {
  if (!payload) return false;
  if (payload?.runtime_state === "delegated" || payload?.delegated === true) return true;
  return Boolean(payload?.scheduler_enabled && !payload?.scheduler_role_allowed);
}

function latestSchedulerRunAgeMs(payload) {
  const recentRuns = Array.isArray(payload?.recent_runs) ? payload.recent_runs : [];
  const latestRun = recentRuns.find((item) => item?.ran_at)?.ran_at;
  if (!latestRun) return null;
  const ageMs = Date.now() - Date.parse(latestRun);
  return Number.isFinite(ageMs) && ageMs >= 0 ? ageMs : null;
}

function isSchedulerActiveViaOwner(payload) {
  if (!isSchedulerDelegated(payload)) return false;
  const ageMs = latestSchedulerRunAgeMs(payload);
  if (ageMs === null) return false;
  return ageMs <= 45 * 60 * 1000;
}

function resolveSchedulerDetail(payload) {
  if (!payload) return "Checking scheduler...";
  if (isSchedulerDelegated(payload) && isSchedulerActiveViaOwner(payload)) {
    const ownerRole = payload?.scheduler_runner_role || "automation";
    return `الجدولة تعمل عبر دور ${ownerRole}`;
  }
  if (isSchedulerDelegated(payload)) {
    const ownerRole = payload?.scheduler_runner_role || "automation";
    const ageMs = latestSchedulerRunAgeMs(payload);
    if (ageMs !== null) {
      const ageMinutes = Math.max(0, Math.round(ageMs / 60000));
      return `الجدولة مملوكة لدور ${ownerRole} (آخر تشغيل قبل ${ageMinutes} دقيقة)`;
    }
    return `الجدولة مملوكة لدور ${ownerRole}`;
  }
  return payload?.blocked_reason || `Jobs: ${payload?.jobs_count ?? 0}`;
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
        schedulerDetail: resolveSchedulerDetail(schedulerData),
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
