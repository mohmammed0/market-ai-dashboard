const CHART_COLORS = {
  textPrimary: "#F5F7FA",
  textSecondary: "#A7B0BC",
  textMuted: "#7C8794",
  border: "#202833",
  positive: "#22C55E",
  negative: "#EF4444",
  warning: "#F59E0B",
  info: "#60A5FA",
  line: "#D9E0E8",
};

function asArray(value) {
  if (value === undefined || value === null) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function mergeAxis(axis, extra = {}) {
  return {
    axisLine: {
      lineStyle: { color: "rgba(124, 135, 148, 0.22)" },
      ...(axis?.axisLine || {}),
    },
    axisTick: {
      show: false,
      ...(axis?.axisTick || {}),
    },
    axisLabel: {
      color: CHART_COLORS.textMuted,
      fontSize: 11,
      ...(axis?.axisLabel || {}),
    },
    splitLine: {
      lineStyle: { color: "rgba(124, 135, 148, 0.08)" },
      ...(axis?.splitLine || {}),
    },
    ...extra,
    ...(axis || {}),
  };
}

function themedSeries(series = []) {
  return (series || []).map((item, index) => {
    const fallbackColor = index === 0 ? CHART_COLORS.line : CHART_COLORS.info;
    const isLine = item?.type === "line";
    return {
      animation: false,
      lineStyle: isLine
        ? {
            width: 2.4,
            color: fallbackColor,
            ...(item?.lineStyle || {}),
          }
        : item?.lineStyle,
      itemStyle: item?.type === "bar"
        ? {
            color: fallbackColor,
            borderRadius: 6,
            ...(item?.itemStyle || {}),
          }
        : item?.itemStyle,
      areaStyle: isLine && item?.areaStyle
        ? {
            opacity: 0.12,
            ...(item.areaStyle || {}),
          }
        : item?.areaStyle,
      ...(item || {}),
    };
  });
}

export function applyChartTheme(option = {}) {
  const xAxes = asArray(option.xAxis);
  const yAxes = asArray(option.yAxis);

  return {
    backgroundColor: "transparent",
    textStyle: {
      color: CHART_COLORS.textSecondary,
      fontFamily: "Inter, system-ui, sans-serif",
      ...(option.textStyle || {}),
    },
    color: option.color || [
      CHART_COLORS.line,
      CHART_COLORS.info,
      CHART_COLORS.positive,
      CHART_COLORS.warning,
      CHART_COLORS.negative,
    ],
    animationDuration: 220,
    grid: {
      left: 28,
      right: 18,
      top: 24,
      bottom: 22,
      containLabel: true,
      ...(option.grid || {}),
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(11, 15, 20, 0.96)",
      borderColor: "rgba(43, 53, 66, 0.95)",
      borderWidth: 1,
      textStyle: {
        color: CHART_COLORS.textPrimary,
        fontSize: 12,
      },
      axisPointer: {
        type: "line",
        lineStyle: {
          color: "rgba(167, 176, 188, 0.25)",
        },
      },
      ...(option.tooltip || {}),
    },
    legend: option.legend
      ? {
          icon: "roundRect",
          itemWidth: 10,
          itemHeight: 10,
          textStyle: {
            color: CHART_COLORS.textSecondary,
            ...(option.legend?.textStyle || {}),
          },
          ...option.legend,
        }
      : undefined,
    xAxis: xAxes.length <= 1
      ? mergeAxis(xAxes[0], { splitLine: { show: false, ...(xAxes[0]?.splitLine || {}) } })
      : xAxes.map((axis) => mergeAxis(axis, { splitLine: { show: false, ...(axis?.splitLine || {}) } })),
    yAxis: yAxes.length <= 1
      ? mergeAxis(yAxes[0])
      : yAxes.map((axis) => mergeAxis(axis)),
    dataZoom: asArray(option.dataZoom).map((item) => ({
      borderColor: "rgba(43, 53, 66, 0.82)",
      fillerColor: "rgba(96, 165, 250, 0.08)",
      handleStyle: {
        color: "#11161D",
        borderColor: CHART_COLORS.border,
      },
      textStyle: {
        color: CHART_COLORS.textMuted,
      },
      ...(item || {}),
    })),
    series: themedSeries(option.series),
    ...option,
  };
}
