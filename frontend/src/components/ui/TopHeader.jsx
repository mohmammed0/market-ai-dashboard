import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";

import { fetchHealth, fetchJobs, fetchSchedulerStatus } from "../../lib/api";
import StatusBadge from "./StatusBadge";
import SymbolWorkspaceBar from "./SymbolWorkspaceBar";


function schedulerTone(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "running") return "accent";
  if (normalized === "error" || normalized === "failed") return "negative";
  if (normalized === "disabled") return "warning";
  return "subtle";
}


export default function TopHeader({ navItems = [] }) {
  const location = useLocation();
  const [platformState, setPlatformState] = useState({
    api: "loading",
    scheduler: "loading",
    runningJobs: 0,
  });
  const today = useMemo(
    () =>
      new Intl.DateTimeFormat("ar-SA", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(new Date()),
    []
  );
  const activeItem = useMemo(() => {
    return navItems.find((item) => {
      if (item.path === "/") {
        return location.pathname === "/";
      }
      return location.pathname.startsWith(item.path);
    }) || navItems[0] || null;
  }, [location.pathname, navItems]);
  const sectionLabel = activeItem?.section || "نظرة عامة";
  const title = activeItem?.label || "لوحة التداول";
  const subtitle = activeItem?.meta || "مسار عمل هادئ وسريع.";

  useEffect(() => {
    let active = true;

    async function loadPlatformState() {
      const [healthResult, schedulerResult, jobsResult] = await Promise.allSettled([
        fetchHealth(),
        fetchSchedulerStatus(),
        fetchJobs({ limit: 10, status: "running" }, { forceFresh: true, cacheTtlMs: 0 }),
      ]);
      if (!active) {
        return;
      }
      setPlatformState({
        api: healthResult.status === "fulfilled" ? healthResult.value?.status || "ok" : "error",
        scheduler: schedulerResult.status === "fulfilled"
          ? schedulerResult.value?.runtime_state || (schedulerResult.value?.scheduler_running ? "running" : "idle")
          : "error",
        runningJobs: jobsResult.status === "fulfilled" ? jobsResult.value?.count || 0 : 0,
      });
    }

    loadPlatformState().catch(() => {});
    const timer = window.setInterval(() => {
      loadPlatformState().catch(() => {});
    }, 45000);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <header className="top-header">
      <div className="top-header-shell">
        <div className="top-header-main top-header-main-compact">
          <div className="top-header-copy">
            <div className="top-header-eyebrow">{sectionLabel}</div>
            <h2>{title}</h2>
            <p>{subtitle}</p>
            <div className="top-header-flow-strip">
              <span className="top-header-flow-chip">طرفية تشغيل موحدة</span>
              <span className="top-header-flow-chip">قرار + تنفيذ + مهام خلفية</span>
              <span className="top-header-flow-chip">PostgreSQL-first runtime</span>
            </div>
          </div>
          <div className="top-header-summary">
            <StatusBadge tone={platformState.api === "ok" ? "accent" : "negative"} label={`API ${platformState.api}`} />
            <StatusBadge tone={schedulerTone(platformState.scheduler)} label={`Scheduler ${platformState.scheduler}`} />
            <StatusBadge tone={platformState.runningJobs ? "warning" : "subtle"} label={`${platformState.runningJobs} jobs`} />
            <span className="top-header-date">{today}</span>
          </div>
        </div>
        <SymbolWorkspaceBar compact />
      </div>
    </header>
  );
}
