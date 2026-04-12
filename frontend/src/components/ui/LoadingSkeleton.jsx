export default function LoadingSkeleton({ lines = 3 }) {
  return (
    <div className="skeleton-group" role="status" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="skeleton skeleton-line"
          style={i === lines - 1 ? { width: "60%" } : undefined}
        />
      ))}
    </div>
  );
}
