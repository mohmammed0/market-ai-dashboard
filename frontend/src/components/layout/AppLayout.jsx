import { NavLink, useLocation } from "react-router-dom";
import { getStoredUser, logout } from "../../api/auth";
import { useAppData } from "../../store/AppDataStore";

const NAV_ITEMS = [
  {
    path: "/",
    label: "لوحة القيادة",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
  {
    path: "/live-market",
    label: "السوق المباشر",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
        <polyline points="16 7 22 7 22 13" />
      </svg>
    ),
  },
  {
    path: "/ai-news",
    label: "أخبار الذكاء",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10l6 6v8a2 2 0 01-2 2z" />
        <polyline points="17 21 17 13 7 13 7 21" />
        <polyline points="7 3 7 8 15 8" />
      </svg>
    ),
  },
  {
    path: "/paper-trading",
    label: "التداول الورقي",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
        <rect x="9" y="3" width="6" height="4" rx="1" />
        <line x1="9" y1="12" x2="15" y2="12" />
        <line x1="9" y1="16" x2="12" y2="16" />
      </svg>
    ),
  },
  {
    path: "/backtest",
    label: "الاختبار التاريخي",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="7 12 3 8 7 4" />
        <path d="M21 12H3" />
        <polyline points="7 20 3 16 7 12" />
      </svg>
    ),
  },
  {
    path: "/strategy-lab",
    label: "مختبر الاستراتيجية",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2v-4M9 21H5a2 2 0 01-2-2v-4m0 0h18" />
      </svg>
    ),
  },
  {
    path: "/settings",
    label: "الإعدادات",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" />
      </svg>
    ),
  },
];

function PlatformStatusDots() {
  const { data: aiStatus } = useAppData("aiStatus");
  const { data: brokerStatus } = useAppData("brokerStatus");

  const aiOk = aiStatus?.status === "running" || aiStatus?.status === "ready" || aiStatus?.status === "ok";
  const brokerOk = brokerStatus?.connected === true || brokerStatus?.status === "connected" || brokerStatus?.status === "ok";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div className="tv-status-indicator" title={`AI: ${aiStatus?.status || "..."}`}>
        <span className={`tv-status-dot ${aiOk ? "tv-status-dot--ok" : "tv-status-dot--warn"}`} />
        <span className="tv-status-label">AI</span>
      </div>
      <div className="tv-status-indicator" title={`Broker: ${brokerStatus?.status || "..."}`}>
        <span className={`tv-status-dot ${brokerOk ? "tv-status-dot--ok" : "tv-status-dot--warn"}`} />
        <span className="tv-status-label">Broker</span>
      </div>
    </div>
  );
}

export default function AppLayout({ children }) {
  const location = useLocation();
  const user = getStoredUser();

  const activeItem = NAV_ITEMS.find((item) => {
    if (item.path === "/") return location.pathname === "/";
    return location.pathname.startsWith(item.path);
  });

  return (
    <div className="tv-shell" dir="rtl">
      {/* Left icon sidebar - positioned on right in RTL */}
      <aside className="tv-sidebar">
        {/* Logo mark */}
        <div className="tv-sidebar-logo" title="Market AI">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="var(--tv-accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
            <polyline points="16 7 22 7 22 13" />
          </svg>
        </div>

        <div className="tv-sidebar-divider" />

        {/* Nav items */}
        <nav className="tv-sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) => `tv-nav-item${isActive ? " active" : ""}`}
              title={item.label}
            >
              {item.icon}
              <span className="tv-nav-tooltip">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Logout */}
        <button
          className="tv-nav-item"
          title="تسجيل خروج"
          onClick={logout}
          style={{ marginBottom: 8 }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          <span className="tv-nav-tooltip">تسجيل خروج</span>
        </button>
      </aside>

      {/* Main content area */}
      <div className="tv-main">
        {/* Top bar */}
        <header className="tv-topbar">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span className="tv-topbar-brand">Market AI</span>
            {activeItem && (
              <>
                <span className="tv-topbar-sep">/</span>
                <span className="tv-topbar-page">{activeItem.label}</span>
              </>
            )}
          </div>

          <div style={{ flex: 1 }} />

          <PlatformStatusDots />

          <div className="tv-topbar-date">
            {new Intl.DateTimeFormat("ar-SA", {
              weekday: "short",
              month: "short",
              day: "numeric",
            }).format(new Date())}
          </div>

          <div className="tv-topbar-user" title={user?.username}>
            {user?.username?.[0]?.toUpperCase() || "U"}
          </div>
        </header>

        {/* Page content */}
        <main className="tv-content">
          {children}
        </main>
      </div>
    </div>
  );
}
