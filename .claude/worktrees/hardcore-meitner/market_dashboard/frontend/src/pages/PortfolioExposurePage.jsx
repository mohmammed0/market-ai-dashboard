import { useMemo } from "react";

import PageFrame from "../components/PageFrame";
import ChartCard from "../components/ui/ChartCard";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchPortfolioExposure } from "../api/execution";
import { useAsyncResource } from "../hooks/useAsyncResource";


export default function PortfolioExposurePage() {
  const { data, loading, error } = useAsyncResource(fetchPortfolioExposure);

  const sectorOption = useMemo(() => {
    if (!data?.by_sector?.length) {
      return null;
    }
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: data.by_sector.map((row) => row.sector),
        axisLabel: { color: "#9bb0c9", rotate: 20 },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#9bb0c9" },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)" } },
      },
      series: [
        {
          type: "bar",
          data: data.by_sector.map((row) => row.weight_pct),
          itemStyle: { color: "#38bdf8", borderRadius: [10, 10, 0, 0] },
        },
      ],
    };
  }, [data]);

  const positionsColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "strategy_mode", header: "Mode" },
      { accessorKey: "sector", header: "Sector" },
      { accessorKey: "market_cap_bucket", header: "Cap Bucket" },
      { accessorKey: "weight_pct", header: "Weight %" },
      { accessorKey: "market_value", header: "Market Value" },
      { accessorKey: "unrealized_pnl", header: "Unrealized PnL" },
    ],
    []
  );

  return (
    <PageFrame
      title="Portfolio Exposure"
      description="Symbol, sector, and market-cap concentration built from the current paper portfolio."
      eyebrow="Exposure Engine"
      headerActions={<StatusBadge label="Portfolio Lens" tone="accent" />}
    >
      <div className="panel result-panel">
        <SectionHeader title="Exposure Summary" description="Open-position concentration and portfolio warnings." />
        <ErrorBanner message={error} />
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : data ? (
          <>
            <SummaryStrip
              items={[
                { label: "Open Positions", value: data.summary?.open_positions ?? 0 },
                { label: "Total Market Value", value: data.summary?.total_market_value ?? 0 },
                { label: "Largest Position", value: `${data.summary?.largest_position_pct ?? 0}%` },
              ]}
            />
            {(data.warnings || []).length ? (
              <div className="risk-warning-list">
                {data.warnings.map((warning) => (
                  <div className="status-message warning" key={warning}>{warning}</div>
                ))}
              </div>
            ) : null}
          </>
        ) : null}
      </div>

      {sectorOption ? (
        <ChartCard
          title="Sector Exposure"
          description="Portfolio weight by sector from the paper-trading book."
          option={sectorOption}
        />
      ) : null}

      <div className="panel result-panel">
        <SectionHeader title="Open Positions" description="The current book enriched with sector and market-cap metadata." />
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : (
          <DataTable
            columns={positionsColumns}
            data={data?.positions || []}
            emptyTitle="No open positions"
            emptyDescription="Run the paper-trading workflow to create positions and exposure data."
          />
        )}
      </div>
    </PageFrame>
  );
}
