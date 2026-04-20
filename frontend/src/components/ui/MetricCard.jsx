import { memo } from "react";
import clsx from "clsx";
import { translateNode } from "../../lib/i18n";


function MetricCard({
  label,
  value,
  detail,
  tone,
  badge,
  delta,
  icon,
  className,
  onClick,
}) {
  return (
    <div
      className={clsx(
        "metric-card",
        tone && `metric-card--${tone}`,
        onClick && "metric-card--clickable",
        className
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className="metric-card-top">
        <span className="metric-card-label">{translateNode(label)}</span>
        {badge && <span className="metric-chip">{translateNode(badge)}</span>}
      </div>
      <span className="metric-card-value">{translateNode(value ?? "-")}</span>
      {(detail || delta) && (
        <div className="metric-card-bottom">
          {detail && <span className="metric-card-detail">{translateNode(detail)}</span>}
          {delta && (
            <span className={clsx("metric-card-delta", Number(delta) >= 0 ? "text-positive" : "text-negative")}>
              {Number(delta) >= 0 ? "+" : ""}{delta}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default memo(MetricCard);
