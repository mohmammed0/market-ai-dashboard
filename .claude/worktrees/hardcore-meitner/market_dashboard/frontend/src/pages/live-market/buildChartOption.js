import { formatCompact } from "./formatters";


export function buildChartOption(chartPayload) {
  const items = chartPayload?.items || [];
  if (!items.length) {
    return null;
  }
  const hasCompare = Array.isArray(chartPayload?.compare_series) && chartPayload.compare_series.length > 0;
  const categories = items.map((item) => String(item.datetime || "").replace("T", " ").slice(0, 16));
  const volumeValues = items.map((item) => Number(item.volume || 0));
  const grid = hasCompare
    ? [
        { left: 50, right: 22, top: 28, height: "50%" },
        { left: 50, right: 22, top: "62%", height: "14%" },
        { left: 50, right: 22, top: "80%", height: "12%" },
      ]
    : [
        { left: 50, right: 22, top: 28, height: "60%" },
        { left: 50, right: 22, top: "74%", height: "14%" },
      ];
  const xAxis = grid.map((_, index) => ({
    type: "category",
    data: categories,
    boundaryGap: chartPayload?.mode !== "line",
    axisLine: { lineStyle: { color: "rgba(148, 163, 184, 0.16)" } },
    axisLabel: { color: "#8fa8c5", hideOverlap: true },
    splitLine: { show: false },
    axisTick: { show: false },
    gridIndex: index,
  }));
  const yAxis = [
    {
      scale: true,
      gridIndex: 0,
      axisLabel: { color: "#8fa8c5" },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.09)" } },
    },
    {
      scale: true,
      gridIndex: 1,
      axisLabel: { color: "#6f87a3", formatter: (value) => formatCompact(value) },
      splitLine: { show: false },
    },
  ];
  if (hasCompare) {
    yAxis.push({
      scale: true,
      gridIndex: 2,
      axisLabel: { color: "#8fa8c5", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.08)" } },
    });
  }
  const priceSeries = chartPayload?.mode === "line"
    ? {
        name: chartPayload.symbol,
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        showSymbol: false,
        smooth: true,
        lineStyle: { color: "#38bdf8", width: 2.6 },
        areaStyle: { color: "rgba(56, 189, 248, 0.12)" },
        data: items.map((item) => Number(item.price || item.close || 0)),
      }
    : {
        name: chartPayload.symbol,
        type: "candlestick",
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: "#16a34a",
          color0: "#ea580c",
          borderColor: "#22c55e",
          borderColor0: "#f97316",
        },
        data: items.map((item) => [
          Number(item.open || item.close || 0),
          Number(item.close || 0),
          Number(item.low || item.close || 0),
          Number(item.high || item.close || 0),
        ]),
      };
  const volumeSeries = {
    name: "الحجم",
    type: "bar",
    xAxisIndex: 1,
    yAxisIndex: 1,
    barMaxWidth: 10,
    itemStyle: {
      color: ({ dataIndex }) => {
        const current = items[dataIndex] || {};
        const openValue = Number(current.open ?? current.price ?? current.close ?? 0);
        const closeValue = Number(current.close ?? current.price ?? 0);
        return closeValue >= openValue ? "rgba(34, 197, 94, 0.75)" : "rgba(249, 115, 22, 0.75)";
      },
    },
    data: volumeValues,
  };
  const compareSeries = hasCompare
    ? chartPayload.compare_series.map((series) => ({
        name: series.symbol,
        type: "line",
        xAxisIndex: 2,
        yAxisIndex: 2,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2, opacity: 0.95 },
        emphasis: { focus: "series" },
        data: series.items.map((item) => Number(item.value || 0)),
      }))
    : [];
  return {
    backgroundColor: "transparent",
    animation: false,
    legend: {
      top: 0,
      right: 0,
      textStyle: { color: "#c9d8ea" },
      data: [chartPayload.symbol, "الحجم", ...(chartPayload.compare_series || []).map((item) => item.symbol)],
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      backgroundColor: "rgba(5, 11, 20, 0.94)",
      borderColor: "rgba(125, 211, 252, 0.16)",
      textStyle: { color: "#ecf6ff" },
    },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid,
    xAxis,
    yAxis,
    dataZoom: [
      { type: "inside", xAxisIndex: xAxis.map((_, index) => index), start: 55, end: 100 },
      { type: "slider", xAxisIndex: xAxis.map((_, index) => index), height: 20, bottom: 8, borderColor: "rgba(148, 163, 184, 0.08)", textStyle: { color: "#8fa8c5" } },
    ],
    series: [priceSeries, volumeSeries, ...compareSeries],
  };
}
