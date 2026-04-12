import { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { fetchHealth, fetchSchedulerStatus } from "../../lib/api";
import { t } from "../../lib/i18n";


function StatusDot({ status }) {
  const color = status === "ok" || status === "running"
    ? "var(--color-positive)"
    : status === "error" || status === "failed"
      ? "var(--color-negative)"
      : "var(--color-warning)";

  return (
    <span
      className="status-dot"
      style={{ background: color }}
      aria-label={status}
    />
  );
}


export default function Header({ navItems = [], onMenuToggle }) {
  const location = useLocation();
  const [platform, setPlatform] = useState({
    api: "loading",
    scheduler: "loading",
  });

  const today = useMemo(
    () => new Intl.DateTimeFormat("ar-SA", {
      weekday: "short",
      month: "short",
      day: "numeric",
    }).format(new Date()),
    []
  );

  const activeItem = useMemo(() => {
    return navItems.find((item) => {
      if (item.path === "/") return location.pathname === "/";
      return location.pathname.startsWith(item.path);
    }) || navItems[0];
  }, [location.pathname, navItems]);

  useEffect(() => {
    let active = true;

    async function poll() {
      const [h, s] = await Promise.allSettled([
        fetchHealth(),
        fetchSchedulerStatus(),
      ]);
      if (!active) return;
      setPlatform({
        api: h.status === "fulfilled" ? (h.value?.status || "ok") : "error",
        scheduler: s.status === "fulfilled"
          ? (s.value?.runtime_state || (s.value?.scheduler_running ? "running" : "idle"))
          : "error",
      });
    }

    poll();
    const timer = setInterval(poll, 30000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  return (
    <header className="app-header">
      {/* Mobile menu button */}
      <button className="btn btn-icon btn-ghost mobile-menu-btn" onClick={onMenuToggle} aria-label="Menu">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Breadcrumb / Page Title */}
      <div className="header-left">
        <div className="header-breadcrumb">
          <span>{t(activeItem?.section || "نظرة عامة")}</span>
          <span className="header-breadcrumb-sep">/</span>
          <span className="header-breadcrumb-current">{t(activeItem?.label || "لوحة التداول")}</span>
        </div>
      </div>

      {/* Right side: status + date */}
      <div className="header-right">
        <div className="header-status-group">
          <div className="status-badge status-badge--positive" style={platform.api !== "ok" ? { background: "var(--color-negative-soft)", color: "var(--color-negative-text)", borderColor: "rgba(239,68,68,0.2)" } : {}}>
            <StatusDot status={platform.api} />
            <span>API</span>
          </div>
          <div className={`status-badge status-badge--${platform.scheduler === "running" ? "info" : "neutral"}`}>
            <StatusDot status={platform.scheduler} />
            <span>Scheduler</span>
          </div>
        </div>
        <span className="divider-vertical" style={{ height: "20px" }} />
        <span className="text-xs text-secondary">{today}</span>
      </div>
    </header>
  );
}
