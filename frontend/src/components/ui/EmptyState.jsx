import { translateNode } from "../../lib/i18n";


export default function EmptyState({ title, description, icon, action, className = "" }) {
  return (
    <div className={`empty-state${className ? ` ${className}` : ""}`}>
      {icon || (
        <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" />
        </svg>
      )}
      {title && <span className="empty-state-title">{translateNode(title)}</span>}
      {description && <span className="empty-state-text">{translateNode(description)}</span>}
      {action && <div style={{ marginTop: "var(--space-3)" }}>{action}</div>}
    </div>
  );
}
