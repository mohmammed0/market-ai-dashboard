import MetricGrid from "./MetricGrid";
import MetricCard from "./MetricCard";


export default function SummaryStrip({ items, className = "", compact = false }) {
  return (
    <MetricGrid className={`summary-strip panel-surface${className ? ` ${className}` : ""}`} compact={compact}>
      {items.map((item) => (
        <MetricCard
          key={item.label}
          label={item.label}
          value={item.value}
          detail={item.detail}
          tone={item.tone}
          badge={item.badge}
          delta={item.delta}
        />
      ))}
    </MetricGrid>
  );
}
