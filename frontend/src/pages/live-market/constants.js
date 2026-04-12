export const DEFAULT_SYMBOL = "AAPL";
export const TIMEFRAME_OPTIONS = ["1S", "5S", "15S", "30S", "1M", "5M", "15M", "30M", "1H", "4H", "1D", "1W", "1MTH"];
export const RANGE_OPTIONS = ["TODAY", "5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"];
export const MICRO_TIMEFRAMES = new Set(["1S", "5S", "15S", "30S"]);
export const POLL_INTERVAL_MS = {
  "1S": 4000,
  "5S": 5000,
  "15S": 7000,
  "30S": 8000,
  "1M": 12000,
  "5M": 18000,
  "15M": 22000,
  "30M": 25000,
  "1H": 30000,
  "4H": 45000,
  "1D": 60000,
  "1W": 75000,
  "1MTH": 90000,
};
export const EMPTY_ITEMS = [];
