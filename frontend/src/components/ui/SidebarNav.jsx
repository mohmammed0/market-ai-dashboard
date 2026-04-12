import { NavLink } from "react-router-dom";
import { t } from "../../lib/i18n";


const SECTION_ORDER = ["نظرة عامة", "السوق", "التداول", "الذكاء", "النظام"];


function groupNav(items) {
  const groups = {};
  for (const item of items) {
    const section = item.section || "Platform";
    groups[section] = groups[section] || [];
    groups[section].push(item);
  }
  return Object.entries(groups).sort((a, b) => SECTION_ORDER.indexOf(a[0]) - SECTION_ORDER.indexOf(b[0]));
}

function NavIcon({ path }) {
  const icons = {
    "/": "M3 10h18M6 5h12M7 15h4m6 0h0",
    "/kpis": "M6 17V9m6 8V5m6 12v-6",
    "/live-market": "M4 16l4-5 4 3 6-8",
    "/analyze": "M4 18l5-5m0 0 4-4m-4 4H5m4 0v4",
    "/scan": "M10 10a4 4 0 1 0 0.001 0M14 14l4 4",
    "/ranking": "M7 7h10M7 12h7M7 17h4",
    "/paper-trading": "M5 7h14M7 12h10M9 17h6",
    "/alerts-center": "M12 4l7 12H5l7-12z",
    "/portfolio-exposure": "M4 12h6V4H4zm10 8h6V4h-6zM4 20h6v-4H4z",
    "/risk": "M12 3l8 4v5c0 5.25-3.438 9.688-8 11-4.562-1.312-8-5.75-8-11V7l8-4z",
    "/ai-news": "M4 6h16M4 11h10M4 16h7",
    "/breadth": "M4 15h4V9H4zm6 0h4V5h-4zm6 0h4v-7h-4z",
    "/strategy-lab": "M4 18h16M6 14l3-3 3 2 6-6",
    "/trade-journal": "M6 4h12v16H6z",
    "/automation": "M12 4v4m0 8v4m8-8h-4M8 12H4m11.314-5.314-2.828 2.828M9.514 14.486l-2.828 2.828m0-10.828 2.828 2.828m5.8 5.8 2.828 2.828",
    "/backtest": "M4 17l4-5 3 2 5-7 4 3",
    "/model-lab": "M7 7h10v10H7z",
    "/broker": "M5 8h14v8H5z",
    "/operations": "M12 5v14M5 12h14",
    "/settings": "M12 8.5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7z",
  };
  const d = icons[path] || "M4 12h16";
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}


export default function SidebarNav({ items }) {
  const groupedItems = groupNav(items);

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">MA</div>
        <div>
          <h1>Market AI</h1>
          <p>طرفية بحث وتداول ورقي</p>
        </div>
      </div>

      <nav className="nav">
        {groupedItems.map(([section, sectionItems]) => (
          <div className="nav-group" key={section}>
            <div className="nav-group-label">{t(section)}</div>
            <div className="nav-group-items">
              {sectionItems.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === "/"}
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                >
                  <NavIcon path={item.path} />
                  <span className="nav-link-title">{t(item.label)}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
