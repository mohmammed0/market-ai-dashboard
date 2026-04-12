import { t } from "../../lib/i18n";


export default function PageFrame({
  title,
  description,
  eyebrow,
  headerActions,
  children,
  className = "",
}) {
  return (
    <div className={`page-container ${className}`}>
      <div className="page-header">
        <div className="page-header-content">
          {eyebrow && <span className="page-header-eyebrow">{t(eyebrow)}</span>}
          {title && <h1>{t(title)}</h1>}
          {description && <p>{t(description)}</p>}
        </div>
        {headerActions && (
          <div className="page-header-actions">{headerActions}</div>
        )}
      </div>
      {children}
    </div>
  );
}
