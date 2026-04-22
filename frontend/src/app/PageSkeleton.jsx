export default function PageSkeleton() {
  return (
    <div style={{ padding: 16 }}>
      <div className="loading-skeleton">
        <div className="skeleton-line" style={{ height: 24, width: "40%", marginBottom: 16 }} />
        <div className="skeleton-line" />
        <div className="skeleton-line" />
        <div className="skeleton-line" />
        <div className="skeleton-line" style={{ width: "60%" }} />
      </div>
    </div>
  );
}
