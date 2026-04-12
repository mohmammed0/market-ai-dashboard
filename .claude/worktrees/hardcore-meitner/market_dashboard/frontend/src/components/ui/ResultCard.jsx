import { translateNode } from "../../lib/i18n";


export default function ResultCard({ label, value, hint, accent = null }) {
  return (
    <div className={`result-item${accent ? ` ${accent}` : ""}`}>
      <span className="result-label">{translateNode(label)}</span>
      <strong>{translateNode(value ?? "-")}</strong>
      {hint ? <small className="minor-text">{translateNode(hint)}</small> : null}
    </div>
  );
}
