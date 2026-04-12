import { t } from "../../lib/i18n";


export default function ErrorBanner({ message, title }) {
  if (!message) return null;

  return (
    <div className="error-banner">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <div className="error-banner-content">
        <strong>{t(title || "Request Issue")}</strong>
        <span>{t(message)}</span>
      </div>
    </div>
  );
}
