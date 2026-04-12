import { Suspense, lazy, memo, useMemo } from "react";

import LoadingSkeleton from "./LoadingSkeleton";
import SectionHeader from "./SectionHeader";
import { applyChartTheme } from "../../lib/chartTheme";

const ReactECharts = lazy(() => import("./EChartsCore"));

function ChartCard({ title, description, option, height = 280, className = "", badge, action }) {
  const themedOption = useMemo(() => applyChartTheme(option), [option]);

  return (
    <div className={`panel result-panel chart-card${className ? ` ${className}` : ""}`}>
      <SectionHeader title={title} description={description} badge={badge} action={action} />
      <div className="chart-shell">
        <Suspense fallback={<LoadingSkeleton lines={4} />}>
          <ReactECharts option={themedOption} style={{ height }} notMerge lazyUpdate opts={{ renderer: "canvas" }} />
        </Suspense>
      </div>
    </div>
  );
}

export default memo(ChartCard);
