const RECENT_SYMBOLS_KEY = "market-ai:recent-symbols";
const PINNED_SYMBOLS_KEY = "market-ai:pinned-symbols";
const SYMBOL_LIBRARY_EVENT = "market-ai:symbol-library-updated";
const MAX_RECENT_SYMBOLS = 10;
const MAX_PINNED_SYMBOLS = 12;

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function sanitizeSymbolItem(item) {
  const symbol = String(item?.symbol || "").trim().toUpperCase();
  if (!symbol) {
    return null;
  }
  return {
    symbol,
    security_name: String(item?.security_name || item?.short_name || "").trim(),
    exchange: String(item?.exchange || "").trim(),
    market_type: String(item?.market_type || item?.listing_category_label || "").trim(),
    listing_category: String(item?.listing_category || "").trim(),
    is_etf: Boolean(item?.is_etf),
  };
}

function readList(key) {
  if (!canUseStorage()) {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.map(sanitizeSymbolItem).filter(Boolean);
  } catch {
    return [];
  }
}

function writeList(key, items, maxItems) {
  if (!canUseStorage()) {
    return;
  }
  const normalized = [];
  const seen = new Set();
  for (const item of items) {
    const normalizedItem = sanitizeSymbolItem(item);
    if (!normalizedItem || seen.has(normalizedItem.symbol)) {
      continue;
    }
    seen.add(normalizedItem.symbol);
    normalized.push(normalizedItem);
    if (normalized.length >= maxItems) {
      break;
    }
  }
  window.localStorage.setItem(key, JSON.stringify(normalized));
  window.dispatchEvent(new CustomEvent(SYMBOL_LIBRARY_EVENT));
}

export function getRecentSymbols() {
  return readList(RECENT_SYMBOLS_KEY);
}

export function getPinnedSymbols() {
  return readList(PINNED_SYMBOLS_KEY);
}

export function rememberSymbol(item) {
  const nextItem = sanitizeSymbolItem(item);
  if (!nextItem) {
    return;
  }
  const existing = getRecentSymbols().filter((entry) => entry.symbol !== nextItem.symbol);
  writeList(RECENT_SYMBOLS_KEY, [nextItem, ...existing], MAX_RECENT_SYMBOLS);
}

export function pinSymbol(item) {
  const nextItem = sanitizeSymbolItem(item);
  if (!nextItem) {
    return;
  }
  const existing = getPinnedSymbols().filter((entry) => entry.symbol !== nextItem.symbol);
  writeList(PINNED_SYMBOLS_KEY, [nextItem, ...existing], MAX_PINNED_SYMBOLS);
}

export function unpinSymbol(symbol) {
  const normalized = String(symbol || "").trim().toUpperCase();
  writeList(
    PINNED_SYMBOLS_KEY,
    getPinnedSymbols().filter((entry) => entry.symbol !== normalized),
    MAX_PINNED_SYMBOLS
  );
}

export function togglePinnedSymbol(item) {
  const normalized = sanitizeSymbolItem(item);
  if (!normalized) {
    return;
  }
  if (getPinnedSymbols().some((entry) => entry.symbol === normalized.symbol)) {
    unpinSymbol(normalized.symbol);
    return;
  }
  pinSymbol(normalized);
}

export function isPinnedSymbol(symbol) {
  const normalized = String(symbol || "").trim().toUpperCase();
  return getPinnedSymbols().some((entry) => entry.symbol === normalized);
}

export function subscribeToSymbolLibrary(listener) {
  if (typeof window === "undefined") {
    return () => {};
  }
  window.addEventListener(SYMBOL_LIBRARY_EVENT, listener);
  return () => window.removeEventListener(SYMBOL_LIBRARY_EVENT, listener);
}
