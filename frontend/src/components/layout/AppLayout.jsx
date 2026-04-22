import { NavLink, useLocation } from "react-router-dom";

import { getStoredUser, logout } from "../../api/auth";
import { useAppData } from "../../store/AppDataStore";

const NAV_ITEMS = [
  {
    path: "/",
    label: "لوحة التحكم",
    section: "الرئيسية",
    hint: "ملخص السوق والمحفظة والذكاء",
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
    path: "/ai-market",
    label: "محطة التحليل",
    section: "الرئيسية",
    hint: "إشارة الذكاء والتحليل الفني",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 20V10" />
        <path d="M18 20V4" />
        <path d="M6 20v-4" />
      </svg>
    ),
  },
  {
    path: "/live-market",
    label: "السوق المباشر",
    section: "الرئيسية",
    hint: "طرفية السوق الحية",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
        <polyline points="16 7 22 7 22 13" />
      </svg>
    ),
  },
  {
    path: "/trading",
    label: "مكتب التداول",
    section: "الرئيسية",
    hint: "المحفظة، الأوامر، والصفقات عبر الوسيط",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 6h18" />
        <path d="M7 12h10" />
        <path d="M10 18h4" />
      </svg>
    ),
  },
  {
    path: "/ai-news",
    label: "أخبار السوق",
    section: "الرئيسية",
    hint: "التغذية الخبرية والتحليل السريع",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10l6 6v8a2 2 0 0 1-2 2z" />
        <polyline points="7 3 7 8 15 8" />
        <line x1="9" y1="13" x2="15" y2="13" />
        <line x1="9" y1="17" x2="13" y2="17" />
      </svg>
    ),
  },
  {
    path: "/ai-chat",
    label: "المحلل الذكي",
    section: "التحليل",
    hint: "محادثة وتحليل تفاعلي",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        <line x1="9" y1="10" x2="15" y2="10" />
        <line x1="9" y1="14" x2="13" y2="14" />
      </svg>
    ),
  },
  {
    path: "/watchlist",
    label: "قائمة المتابعة",
    section: "التحليل",
    hint: "الرموز المراقبة والمرشحة",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <line x1="9" y1="9" x2="15" y2="9" />
        <line x1="9" y1="12" x2="15" y2="12" />
        <line x1="9" y1="15" x2="13" y2="15" />
      </svg>
    ),
  },
  {
    path: "/ranking",
    label: "ترتيب الأسهم",
    section: "التحليل",
    hint: "الترتيب والبحث في الفرص",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <line x1="8" y1="6" x2="21" y2="6" />
        <line x1="8" y1="12" x2="21" y2="12" />
        <line x1="8" y1="18" x2="21" y2="18" />
        <line x1="3" y1="6" x2="3.01" y2="6" />
        <line x1="3" y1="12" x2="3.01" y2="12" />
        <line x1="3" y1="18" x2="3.01" y2="18" />
      </svg>
    ),
  },
  {
    path: "/knowledge",
    label: "مركز المعرفة",
    section: "التحليل",
    hint: "بحث الأبحاث والملاحظات",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </svg>
    ),
  },
  {
    path: "/breadth",
    label: "مسح السوق",
    section: "التحليل",
    hint: "اتساع السوق والزخم",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
  {
    path: "/multi-chart",
    label: "الشارتات",
    section: "التحليل",
    hint: "مقارنة عدة رسوم بيانية",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="2" width="9" height="9" rx="1" />
        <rect x="13" y="2" width="9" height="9" rx="1" />
        <rect x="2" y="13" width="9" height="9" rx="1" />
        <rect x="13" y="13" width="9" height="9" rx="1" />
      </svg>
    ),
  },
  {
    path: "/macro",
    label: "الاقتصاد الكلي",
    section: "التحليل",
    hint: "الأنظمة الاقتصادية والمؤشرات",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="2" y1="12" x2="22" y2="12" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
    ),
  },
  {
    path: "/fundamentals",
    label: "التحليل الأساسي",
    section: "التحليل",
    hint: "SEC EDGAR والبيانات المالية",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
        <line x1="8" y1="21" x2="16" y2="21" />
        <line x1="12" y1="17" x2="12" y2="21" />
      </svg>
    ),
  },
  {
    path: "/backtest",
    label: "الاختبار التاريخي",
    section: "الاستراتيجية",
    hint: "اختبار الاستراتيجيات والمقارنة",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
    ),
  },
  {
    path: "/strategy-lab",
    label: "مختبر الاستراتيجية",
    section: "الاستراتيجية",
    hint: "التجارب والمقارنات",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19h16" />
        <path d="M7 16l3-8 4 4 3-7" />
      </svg>
    ),
  },
  {
    path: "/risk",
    label: "لوحة المخاطر",
    section: "الاستراتيجية",
    hint: "حدود الانكشاف والمخاطر",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7l8-4z" />
        <path d="M12 8v5" />
        <circle cx="12" cy="16" r="0.6" fill="currentColor" />
      </svg>
    ),
  },
  {
    path: "/portfolio-exposure",
    label: "انكشاف المحفظة",
    section: "الاستراتيجية",
    hint: "التوزيع القطاعي والتمركز",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3v18" />
        <path d="M5 9h14" />
        <path d="M5 15h9" />
      </svg>
    ),
  },
  {
    path: "/alerts-center",
    label: "التنبيهات",
    section: "التنفيذ",
    hint: "الإشعارات والإشارات الحرجة",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
    ),
  },
  {
    path: "/trade-journal",
    label: "سجل التداول",
    section: "التنفيذ",
    hint: "مراجعة الصفقات وجودة التنفيذ",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </svg>
    ),
  },
  {
    path: "/automation",
    label: "الأتمتة",
    section: "التنفيذ",
    hint: "الدورات والمهام المجدولة",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 6v6l4 2" />
        <circle cx="12" cy="12" r="9" />
      </svg>
    ),
  },
  {
    path: "/diagnostics/auto-trading",
    label: "تشخيص التداول",
    section: "التنفيذ",
    hint: "سلسلة القرار من الإشارة حتى التنفيذ",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="M7 14l4-4 3 3 5-6" />
      </svg>
    ),
  },
  {
    path: "/broker",
    label: "الوسيط",
    section: "التنفيذ",
    hint: "حالة الاتصال وتنفيذ Alpaca",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="7" width="20" height="14" rx="2" />
        <path d="M16 3v8" />
        <path d="M8 3v8" />
      </svg>
    ),
  },
  {
    path: "/operations",
    label: "العمليات",
    section: "المنصة",
    hint: "سجل التشغيل وحالة الخدمات",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2v4" />
        <path d="M12 18v4" />
        <path d="M4.93 4.93l2.83 2.83" />
        <path d="M16.24 16.24l2.83 2.83" />
        <path d="M2 12h4" />
        <path d="M18 12h4" />
        <path d="M4.93 19.07l2.83-2.83" />
        <path d="M16.24 7.76l2.83-2.83" />
      </svg>
    ),
  },
  {
    path: "/model-lab",
    label: "مختبر النماذج",
    section: "المنصة",
    hint: "تدريب ومراقبة ML/DL",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2l8 4-8 4-8-4 8-4z" />
        <path d="M4 10l8 4 8-4" />
        <path d="M4 18l8 4 8-4" />
      </svg>
    ),
  },
  {
    path: "/brain",
    label: "لوحة الدماغ",
    section: "المنصة",
    hint: "مركز الإشراف الذكي",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M9 3a3 3 0 0 0-3 3v1a3 3 0 0 0 0 6v1a3 3 0 0 0 3 3h1v4" />
        <path d="M15 3a3 3 0 0 1 3 3v1a3 3 0 0 1 0 6v1a3 3 0 0 1-3 3h-1v4" />
      </svg>
    ),
  },
  {
    path: "/settings",
    label: "الإعدادات",
    section: "المنصة",
    hint: "تهيئة النظام والوسيط والإشعارات",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    ),
  },
];

const NAV_SECTIONS = [
  { label: "الرئيسية", paths: ["/", "/ai-market", "/live-market", "/trading", "/ai-news"] },
  { label: "التحليل", paths: ["/ranking", "/knowledge"] },
  { label: "التنفيذ", paths: ["/broker", "/diagnostics/auto-trading"] },
  { label: "المنصة", paths: ["/brain", "/settings"] },
];

function PlatformStatusDots() {
  const { data: aiStatus } = useAppData("aiStatus");
  const canonicalAiStatus = aiStatus?.effective_status || aiStatus?.status || "checking";
  const aiProvider = aiStatus?.effective_provider || aiStatus?.active_provider || "unavailable";
  const aiOk = canonicalAiStatus === "ready" || canonicalAiStatus === "running" || canonicalAiStatus === "ok";

  return (
    <div
      className="tv-status-indicator"
      data-testid="topbar-ai-status"
      title={`AI: ${aiProvider} (${canonicalAiStatus})`}
    >
      <span className={`tv-status-dot ${aiOk ? "tv-status-dot--ok" : "tv-status-dot--warn"}`} />
      <span className="tv-status-label">AI</span>
      <span className="tv-status-meta">{aiProvider}</span>
    </div>
  );
}

function resolveNavSections() {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.paths
      .map((path) => NAV_ITEMS.find((item) => item.path === path))
      .filter(Boolean),
  })).filter((section) => section.items.length > 0);
}

export default function AppLayout({ children }) {
  const location = useLocation();
  const user = getStoredUser();
  const navSections = resolveNavSections();

  const activeItem = NAV_ITEMS.find((item) => {
    if (item.path === "/") return location.pathname === "/";
    return location.pathname.startsWith(item.path);
  });

  return (
    <div className="tv-shell" dir="rtl">
      <aside className="tv-sidebar">
        <div className="tv-sidebar-brand">
          <div className="tv-sidebar-brand-mark" title="Market AI">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
              <polyline points="16 7 22 7 22 13" />
            </svg>
          </div>
          <div className="tv-sidebar-brand-copy">
            <strong>Market AI</strong>
            <span>مساحة التحليل والتداول</span>
          </div>
        </div>

        <div className="tv-sidebar-nav">
          {navSections.map((section) => (
            <div key={section.label} className="tv-nav-section">
              <div className="tv-nav-section-label">{section.label}</div>
              <div className="tv-nav-section-items">
                {section.items.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === "/"}
                    className={({ isActive }) => `tv-nav-item${isActive ? " active" : ""}`}
                    title={item.label}
                  >
                    <span className="tv-nav-icon">{item.icon}</span>
                    <span className="tv-nav-copy">
                      <strong>{item.label}</strong>
                      {item.hint ? <small>{item.hint}</small> : null}
                    </span>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="tv-sidebar-footer">
          <div className="tv-user-pill">
            <span className="tv-user-avatar">{String(user?.username || "A").slice(0, 1).toUpperCase()}</span>
            <div className="tv-user-copy">
              <strong>{user?.username || "guest"}</strong>
              <small>{user?.role || "operator"}</small>
            </div>
          </div>
          <button className="tv-nav-item tv-nav-item--logout" title="تسجيل خروج" onClick={logout} type="button">
            <span className="tv-nav-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </span>
            <span className="tv-nav-copy">
              <strong>تسجيل خروج</strong>
              <small>إنهاء الجلسة الحالية</small>
            </span>
          </button>
        </div>
      </aside>

      <div className="tv-main">
        <header className="tv-topbar">
          <div className="tv-topbar-heading">
            <span className="tv-topbar-kicker">مركز التحكم</span>
            <div className="tv-topbar-title-row">
              <span className="tv-topbar-brand">Market AI</span>
              {activeItem ? (
                <>
                  <span className="tv-topbar-sep">/</span>
                  <span className="tv-topbar-page">{activeItem.label}</span>
                </>
              ) : null}
            </div>
            {activeItem?.hint ? <span className="tv-topbar-hint">{activeItem.hint}</span> : null}
          </div>

          <div className="tv-topbar-panel">
            <PlatformStatusDots />
            <div className="tv-shell-chip">
              <span>وضع الواجهة</span>
              <strong>ويب + سطح المكتب</strong>
            </div>
            <div className="tv-topbar-date">
              {new Intl.DateTimeFormat("ar-SA", {
                weekday: "short",
                month: "short",
                day: "numeric",
              }).format(new Date())}
            </div>
          </div>
        </header>

        <main className="tv-content">{children}</main>
      </div>
    </div>
  );
}
