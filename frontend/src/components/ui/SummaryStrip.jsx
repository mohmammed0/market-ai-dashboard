import MetricCard from "./MetricCard";
import clsx from "clsx";


export default function SummaryStrip({ items, className = "", compact = false }) {
  return (
    <div className={clsx("summary-strip", compact && "summary-strip--compact", className)}>
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
    </div>
  );
}
