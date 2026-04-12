import clsx from "clsx";
import { translateNode } from "../../lib/i18n";


export default function SectionCard({
  title,
  description,
  action,
  children,
  footer,
  className = "",
  variant,
  flush = false,
}) {
  return (
    <section className={clsx("card", variant && `card--${variant}`, className)}>
      {(title || description || action) && (
        <div className="card-header">
          <div className="card-header-content">
            {title && <h3 className="card-title">{translateNode(title)}</h3>}
            {description && <p className="card-description">{translateNode(description)}</p>}
          </div>
          {action && <div className="card-header-action">{action}</div>}
        </div>
      )}
      <div className={flush ? "card-body-flush" : "card-body"}>
        {children}
      </div>
      {footer && <div className="card-footer">{footer}</div>}
    </section>
  );
}
