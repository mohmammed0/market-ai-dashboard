import { translateNode } from "../../lib/i18n";


export default function EmptyState({ title, description, className = "" }) {
  return (
    <div className={`empty-state${className ? ` ${className}` : ""}`}>
      <strong>{translateNode(title)}</strong>
      <p>{translateNode(description)}</p>
    </div>
  );
}
