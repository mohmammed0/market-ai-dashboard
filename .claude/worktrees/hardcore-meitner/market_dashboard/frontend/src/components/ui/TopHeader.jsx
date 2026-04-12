import { useMemo } from "react";
import { useLocation } from "react-router-dom";

import StatusBadge from "./StatusBadge";
import SymbolWorkspaceBar from "./SymbolWorkspaceBar";


export default function TopHeader({ navItems = [] }) {
  const location = useLocation();
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

  return (
    <header className="top-header">
      <div className="top-header-shell">
        <div className="top-header-main top-header-main-compact">
          <div className="top-header-copy">
            <div className="top-header-eyebrow">{sectionLabel}</div>
            <h2>{title}</h2>
            <p>{subtitle}</p>
          </div>
          <div className="top-header-summary">
            <StatusBadge tone="subtle" label={sectionLabel} />
            <span className="top-header-date">{today}</span>
          </div>
        </div>
        <SymbolWorkspaceBar compact />
      </div>
    </header>
  );
}
