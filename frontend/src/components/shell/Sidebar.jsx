import { useState } from "react";
import { NavLink } from "react-router-dom";
import { t } from "../../lib/i18n";
import { logout, getStoredUser } from "../../api/auth";

const SECTION_ORDER = ["الأساسي", "التحليل", "النظام"];

const SECTION_ICONS = {
  "الأساسي": "M4 5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5z",
  "التحليل": "M9.663 17h4.674M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 1 1 7.072 0l-.548.547A3.374 3.374 0 0 0 14 18.469V19a2 2 0 1 1-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z",
  "النظام": "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z",
};

const NAV_ICONS = {
  "/": "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6",
  "/kpis": "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
  "/live-market": "M13 7h8m0 0v8m0-8l-8 8-4-4-6 6",
  "/analyze": "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01",
  "/scan": "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  "/ranking": "M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12",
  "/paper-trading": "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2",
  "/alerts-center": "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9",
  "/portfolio-exposure": "M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z",
  "/risk": "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
  "/ai-news": "M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2",
  "/breadth": "M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z",
  "/strategy-lab": "M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z",
  "/trade-journal": "M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253",
  "/automation": "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",
  "/backtest": "M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z",
  "/model-lab": "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4",
  "/broker": "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z",
  "/operations": "M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01",
  "/settings": "M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z",
};

function groupNav(items) {
  const groups = {};
  for (const item of items) {
    const section = item.section || "الأساسي";
    if (!groups[section]) groups[section] = [];
    groups[section].push(item);
  }
  return SECTION_ORDER
    .filter((s) => groups[s])
    .map((s) => [s, groups[s]]);
}

function NavIcon({ path }) {
  const d = NAV_ICONS[path] || "M4 6h16M4 12h16M4 18h16";
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export default function Sidebar({ items, open, onClose }) {
  const groupedItems = groupNav(items);
  const [expandedSections, setExpandedSections] = useState({});

  const toggleSection = (section) => {
    setExpandedSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  return (
    <>
      {/* Mobile overlay */}
      {open && (
        <div className="sidebar-overlay" onClick={onClose} aria-hidden="true" />
      )}

      <aside className={`app-sidebar${open ? " open" : ""}`}>
        {/* Brand */}
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="sidebar-brand-text">
            <h1>Market AI</h1>
            <span>Trading Command Center</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="sidebar-nav">
          {groupedItems.map(([section, sectionItems]) => {
            const primaryItems = sectionItems.filter((item) => item.priority === "primary");
            const secondaryItems = sectionItems.filter((item) => item.priority === "secondary");
            const hasSecondary = secondaryItems.length > 0;
            const isExpanded = expandedSections[section];

            return (
              <div className="sidebar-section" key={section}>
                <div className="sidebar-section-label">{t(section)}</div>
                {primaryItems.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === "/"}
                    className={({ isActive }) =>
                      `sidebar-link${isActive ? " active" : ""}`
                    }
                    onClick={onClose}
                  >
                    <NavIcon path={item.path} />
                    <span>{t(item.label)}</span>
                  </NavLink>
                ))}
                {hasSecondary && (
                  <>
                    {isExpanded &&
                      secondaryItems.map((item) => (
                        <NavLink
                          key={item.path}
                          to={item.path}
                          end={item.path === "/"}
                          className={({ isActive }) =>
                            `sidebar-link secondary${isActive ? " active" : ""}`
                          }
                          onClick={onClose}
                          style={{ paddingRight: "calc(var(--space-4) + var(--space-2))" }}
                        >
                          <NavIcon path={item.path} />
                          <span>{t(item.label)}</span>
                        </NavLink>
                      ))}
                    <button
                      type="button"
                      onClick={() => toggleSection(section)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: "100%",
                        padding: "var(--space-2) var(--space-4)",
                        marginTop: "var(--space-1)",
                        background: "transparent",
                        border: "none",
                        color: "var(--color-text-secondary)",
                        cursor: "pointer",
                        fontSize: "0.75rem",
                        fontWeight: "500",
                      }}
                    >
                      {isExpanded ? "إخفاء المزيد" : "عرض المزيد"}
                    </button>
                  </>
                )}
              </div>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="sidebar-footer">
          <div style={{ padding: "var(--space-3) var(--space-4)", borderTop: "1px solid var(--color-border)" }}>
            <div style={{ fontSize: "0.75rem", color: "var(--color-text-tertiary)", marginBottom: "var(--space-2)" }}>
              {getStoredUser()?.username || "مستخدم"}
            </div>
            <button
              onClick={logout}
              style={{
                width: "100%",
                padding: "var(--space-2)",
                background: "transparent",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                color: "var(--color-text-secondary)",
                cursor: "pointer",
                fontSize: "0.8125rem",
              }}
            >
              تسجيل خروج
            </button>
          </div>
          <div className="sidebar-status">
            <span className="sidebar-status-dot" />
            <span>Platform Active</span>
          </div>
        </div>
      </aside>
    </>
  );
}
