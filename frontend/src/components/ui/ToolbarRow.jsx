export default function ToolbarRow({ start, end, className = "", children }) {
  return (
    <div className={`toolbar-row${className ? ` ${className}` : ""}`}>
      {start ? <div className="toolbar-cluster toolbar-cluster-start">{start}</div> : null}
      {children}
      {end ? <div className="toolbar-cluster toolbar-cluster-end">{end}</div> : null}
    </div>
  );
}
