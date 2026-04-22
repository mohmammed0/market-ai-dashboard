import { memo, useMemo } from "react";
import { Link } from "react-router-dom";

import DataTable from "../../components/ui/DataTable";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton";
import SectionCard from "../../components/ui/SectionCard";
import StatusBadge from "../../components/ui/StatusBadge";
import { exchangeTone, formatCompact, formatPercent, formatPrice, normalizeSymbol } from "./formatters";


function LiveMarketExplorerTable({
  bootLoading,
  explorerCount,
  explorerItems,
  favoriteSymbolSet,
  onSelectSymbol,
  onToggleFavoriteSymbol,
}) {
  const explorerColumns = useMemo(
    () => [
      {
        accessorKey: "symbol",
        header: "الرمز",
        cell: ({ row }) => (
          <button className="ticker-button" type="button" onClick={() => onSelectSymbol(row.original.symbol)}>
            <span className="market-ticker-stack market-ticker-stack-strong">
              <strong>{row.original.symbol}</strong>
              <small>{row.original.security_name || row.original.short_name || "-"}</small>
            </span>
          </button>
        ),
      },
      {
        accessorKey: "exchange",
        header: "السوق",
        cell: ({ row }) => <StatusBadge label={row.original.exchange || "Unknown"} tone={exchangeTone(row.original.exchange)} />,
      },
      {
        accessorKey: "price",
        header: "السعر",
        cell: ({ row }) => <strong className="table-metric">{formatPrice(row.original.price)}</strong>,
      },
      {
        accessorKey: "change_pct",
        header: "التغير %",
        cell: ({ row }) => (
          <span className={Number(row.original.change_pct || 0) >= 0 ? "quote-positive" : "quote-negative"}>
            {formatPercent(row.original.change_pct)}
          </span>
        ),
      },
      {
        accessorKey: "volume",
        header: "الحجم",
        cell: ({ row }) => <span className="market-number">{formatCompact(row.original.volume)}</span>,
      },
      {
        accessorKey: "market_cap",
        header: "القيمة السوقية",
        cell: ({ row }) => <span className="market-number">{formatCompact(row.original.market_cap)}</span>,
      },
      {
        accessorKey: "actions",
        header: "الإجراء",
        cell: ({ row }) => {
          const symbol = normalizeSymbol(row.original.symbol);
          return (
            <div className="market-action-links market-action-links-compact">
              <button className="inline-link" type="button" onClick={() => onToggleFavoriteSymbol(symbol)}>
                {favoriteSymbolSet.has(symbol) ? "مفضلة" : "أضف للمفضلة"}
              </button>
              <Link className="inline-link inline-link-chip" to={`/analyze?symbol=${encodeURIComponent(symbol)}`}>
                تحليل
              </Link>
              <Link className="inline-link inline-link-chip" to={`/trading?symbol=${encodeURIComponent(symbol)}`}>
                تداول
              </Link>
            </div>
          );
        },
      },
    ],
    [favoriteSymbolSet, onSelectSymbol, onToggleFavoriteSymbol]
  );

  return (
    <SectionCard
      title="جدول السوق"
      description="جدول موحد للكون الأمريكي مع انتقال مباشر إلى التحليل ومكتب التداول وإدارة المفضلة من نفس المكان."
      badge={explorerCount ? `${explorerCount} صف` : "Explorer"}
    >
      {bootLoading ? (
        <LoadingSkeleton lines={8} />
      ) : (
        <DataTable
          columns={explorerColumns}
          data={explorerItems}
          emptyTitle="لا توجد نتائج مطابقة"
          emptyDescription="وسّع شروط البحث أو بدّل السوق والفئة حتى تعثر على الرموز الأكثر صلة."
        />
      )}
    </SectionCard>
  );
}


export default memo(LiveMarketExplorerTable);
