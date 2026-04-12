import { translateNode } from "../../lib/i18n";


export default function DataTableShell({ rowCount, note, children }) {
  return (
    <div className="table-wrap data-table-shell">
      <div className="data-table-toolbar">
        <div className="data-table-toolbar-copy">
          <strong>{translateNode(rowCount)}</strong>
          <span>{translateNode("Rows")}</span>
        </div>
        {note ? <div className="data-table-toolbar-note">{translateNode(note)}</div> : null}
      </div>
      <div className="data-table-container">
        {children}
      </div>
    </div>
  );
}
