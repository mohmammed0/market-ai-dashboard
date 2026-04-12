import { translateNode } from "../../lib/i18n";


export default function ResultCard({ label, value, hint, accent }) {
  return (
    <div className="metric-card">
      <span className="metric-card-label">{translateNode(label)}</span>
      <span className="metric-card-value" style={{ fontSize: "var(--text-md)" }}>{translateNode(value ?? "-")}</span>
      {hint && <span className="metric-card-detail">{translateNode(hint)}</span>}
    </div>
  );
}
