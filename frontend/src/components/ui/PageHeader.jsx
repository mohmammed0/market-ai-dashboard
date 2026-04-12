import { translateNode } from "../../lib/i18n";


export default function PageHeader({ title, description, eyebrow, actions }) {
  return (
    <header className="page-header">
      <div className="page-header-content">
        {eyebrow && <span className="page-header-eyebrow">{translateNode(eyebrow)}</span>}
        {title && <h1>{translateNode(title)}</h1>}
        {description && <p>{translateNode(description)}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}
