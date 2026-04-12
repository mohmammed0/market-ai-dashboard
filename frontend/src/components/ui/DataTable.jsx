import {
  getSortedRowModel,
  flexRender,
  getCoreRowModel,
  useReactTable,
  getPaginationRowModel,
} from "@tanstack/react-table";
import { memo, useState } from "react";
import clsx from "clsx";
import { translateNode } from "../../lib/i18n";


function columnText(column) {
  const header = column?.columnDef?.header;
  if (typeof header === "string") return header;
  const key = column?.columnDef?.accessorKey;
  return typeof key === "string" ? key : "";
}

function isNumericColumn(column) {
  if (column?.columnDef?.meta?.align === "numeric") return true;
  const text = `${columnText(column)} ${column?.columnDef?.accessorKey || ""}`.toLowerCase();
  return /(price|pnl|qty|quantity|return|drawdown|rate|value|equity|confidence|cash|power|volume|cap|exposure|pct|%|score|avg|market|filled|limit|cagr|profit|loss|factor|expectancy|hours|days|count|rank)/.test(text);
}


function DataTable({
  columns,
  data = [],
  emptyTitle,
  emptyDescription,
  className,
  compact = false,
  maxHeight,
}) {
  const [sorting, setSorting] = useState([]);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  if (!data.length) {
    return (
      <div className="empty-state">
        <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <span className="empty-state-title">{translateNode(emptyTitle || "No data")}</span>
        {emptyDescription && <span className="empty-state-text">{translateNode(emptyDescription)}</span>}
      </div>
    );
  }

  return (
    <div
      className={clsx("table-container", className)}
      style={maxHeight ? { maxHeight, overflow: "auto" } : undefined}
    >
      <table className={clsx("data-table", compact && "data-table--compact")}>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  onClick={header.column.getToggleSortingHandler?.()}
                  className={clsx(
                    header.column.getCanSort?.() && "sortable",
                    isNumericColumn(header.column) && "align-numeric"
                  )}
                >
                  {header.isPlaceholder
                    ? null
                    : translateNode(flexRender(header.column.columnDef.header, header.getContext()))}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  className={clsx(isNumericColumn(cell.column) && "align-numeric")}
                >
                  {translateNode(flexRender(cell.column.columnDef.cell, cell.getContext()))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default memo(DataTable);
