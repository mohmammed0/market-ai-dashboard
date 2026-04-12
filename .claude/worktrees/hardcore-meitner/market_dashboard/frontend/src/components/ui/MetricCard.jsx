import { memo } from "react";
import StatusBadge from "./StatusBadge";
import StatChange from "./StatChange";
import { translateNode } from "../../lib/i18n";


function resolveDeltaTone(value) {
  if (value === null || value === undefined || value === "") {
    return "neutral";
  }
  const numeric = Number(String(value).replace(/[^\d.-]/g, ""));
  if (!Number.isNaN(numeric)) {
    if (numeric > 0) return "positive";
    if (numeric < 0) return "negative";
  }
  return "neutral";
}


function MetricCard({ label, value, detail, tone = "default", badge, delta }) {
  return (
    <div className={`metric-card metric-${tone}`}>
      <div className="metric-card-topline">
        <span>{translateNode(label)}</span>
        {badge ? <StatusBadge label={badge} tone={tone === "warning" ? "warning" : "subtle"} /> : null}
      </div>
      <strong>{translateNode(value ?? "-")}</strong>
      <div className="metric-card-footer">
        {detail ? <small>{translateNode(detail)}</small> : <span />}
        {delta ? <StatChange value={delta} tone={resolveDeltaTone(delta)} /> : null}
      </div>
    </div>
  );
}

export default memo(MetricCard);
