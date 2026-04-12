import {
  getSortedRowModel,
  flexRender,
  getCoreRowModel,
  useReactTable,
  getPaginationRowModel,
} from "@tanstack/react-table";
import { memo, useState } from "react";

import DataTableShell from "./DataTableShell";
import EmptyState from "./EmptyState";
import { translateNode } from "../../lib/i18n";


function columnText(column) {
  const header = column?.columnDef?.header;
  if (typeof header === "string") {
    return header;
  }
  const key = column?.columnDef?.accessorKey;
  return typeof key === "string" ? key : "";
}

function isNumericColumn(column) {
  if (column?.columnDef?.meta?.align === "numeric") {
    return true;
  }
  const text = `${columnText(column)} ${column?.columnDef?.accessorKey || ""}`.toLowerCase();
  return /(price|pnl|qty|quantity|return|drawdown|rate|value|equity|confidence|cash|power|volume|cap|exposure|pct|%|score|avg|market|filled|limit|cagr|profit|loss|factor|expectancy|hours|days|count|rank)/.test(text);
}


function DataTable({ columns, data, emptyTitle, emptyDescription }) {
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
  const sortableColumns = table.getAllLeafColumns().filter((column) => column.getCanSort?.()).length;

  if (!data.length) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  return (
    <DataTableShell rowCount={data.length} note={sortableColumns ? "يمكن فرز الأعمدة من العناوين" : "عرض جدولي مركز"}>
      <table className="data-table">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  onClick={header.column.getToggleSortingHandler?.()}
                  className={`${header.column.getCanSort?.() ? "sortable" : ""}${isNumericColumn(header.column) ? " align-numeric" : ""}`}
                >
                  {header.isPlaceholder
                    ? null
                    : <span className="table-header-label">{translateNode(flexRender(header.column.columnDef.header, header.getContext()))}</span>}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, index) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  data-row={index + 1}
                  className={isNumericColumn(cell.column) ? "align-numeric" : ""}
                >
                  {translateNode(flexRender(cell.column.columnDef.cell, cell.getContext()))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </DataTableShell>
  );
}

export default memo(DataTable);
