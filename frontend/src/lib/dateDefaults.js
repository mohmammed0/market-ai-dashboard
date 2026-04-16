export const DEFAULT_ANALYSIS_LOOKBACK_DAYS = 30;

function isoDate(value) {
  return new Date(value).toISOString().slice(0, 10);
}

export function buildRecentDateRange(days = DEFAULT_ANALYSIS_LOOKBACK_DAYS) {
  const today = new Date();
  const endDate = isoDate(today);
  const start = new Date(today);
  start.setDate(start.getDate() - Math.max(Number(days || DEFAULT_ANALYSIS_LOOKBACK_DAYS), 7));
  return {
    startDate: isoDate(start),
    endDate,
    todayIso: endDate,
  };
}
