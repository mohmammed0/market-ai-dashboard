export default function MetricGrid({ children, className = "", compact = false }) {
  return (
    <div className={`metric-grid${compact ? " metric-grid-compact" : ""}${className ? ` ${className}` : ""}`}>
      {children}
    </div>
  );
}
