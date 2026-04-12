export default function SkeletonBlock({ lines = 3, className = "" }) {
  return (
    <div className={`loading-skeleton${className ? ` ${className}` : ""}`}>
      {Array.from({ length: lines }).map((_, index) => (
        <div key={index} className="loading-line" />
      ))}
    </div>
  );
}
