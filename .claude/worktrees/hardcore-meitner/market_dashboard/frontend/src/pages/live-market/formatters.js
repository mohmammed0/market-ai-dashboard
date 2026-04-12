const MARKET_LOCALE = "ar-SA-u-nu-latn";

const numberFormatter = new Intl.NumberFormat(MARKET_LOCALE, { maximumFractionDigits: 0 });
const compactFormatter = new Intl.NumberFormat(MARKET_LOCALE, { notation: "compact", maximumFractionDigits: 1 });
const priceFormatter = new Intl.NumberFormat(MARKET_LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });


export function normalizeSymbol(value) {
  return String(value || "").trim().toUpperCase();
}


export function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return numberFormatter.format(Number(value));
}


export function formatCompact(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return compactFormatter.format(Number(value));
}


export function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `$${priceFormatter.format(Number(value))}`;
}


export function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const amount = Number(value);
  return `${amount >= 0 ? "+" : ""}${priceFormatter.format(amount)}%`;
}


export function formatUnsignedPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${priceFormatter.format(Number(value))}%`;
}


export function formatDelta(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const amount = Number(value);
  return `${amount >= 0 ? "+" : "-"}$${priceFormatter.format(Math.abs(amount))}`;
}


export function sessionTone(label) {
  if (label === "الجلسة النظامية") {
    return "accent";
  }
  if (label === "ما قبل الافتتاح" || label === "ما بعد الإغلاق") {
    return "warning";
  }
  return "subtle";
}


export function exchangeTone(exchange) {
  const normalized = String(exchange || "").toUpperCase();
  if (normalized.includes("NASDAQ")) {
    return "accent";
  }
  if (normalized.includes("NYSE")) {
    return "warning";
  }
  return "subtle";
}
