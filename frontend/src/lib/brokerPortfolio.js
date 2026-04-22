function toNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeText(value, fallback = "") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function normalizeEnumText(value, fallback = "") {
  const text = normalizeText(value, fallback);
  if (!text) return fallback;
  const parts = text.split(".");
  return parts[parts.length - 1] || fallback;
}

const TERMINAL_ORDER_STATUSES = new Set([
  "filled",
  "canceled",
  "cancelled",
  "expired",
  "rejected",
  "replaced",
  "suspended",
]);

export function normalizeBrokerPosition(item = {}) {
  return {
    symbol: normalizeText(item.symbol, "-"),
    side: normalizeEnumText(item.side, "").toUpperCase(),
    quantity: toNumber(item.qty),
    qty: toNumber(item.qty),
    avg_entry_price: toNumber(item.avg_entry_price),
    current_price: toNumber(item.current_price),
    market_value: toNumber(item.market_value),
    cost_basis: toNumber(item.cost_basis),
    unrealized_pnl: toNumber(item.unrealized_pnl),
    unrealized_pnl_pct: toNumber(item.unrealized_pnl_pct),
    change_today_pct: toNumber(item.change_today_pct),
    realized_pnl: 0,
    stop_loss_price: null,
    trailing_stop_pct: null,
    trailing_stop_price: null,
    high_water_mark: null,
  };
}

export function normalizeBrokerOrder(item = {}) {
  const rawStatus = normalizeEnumText(item.status).toLowerCase();
  return {
    id: normalizeText(item.id, ""),
    client_order_id: normalizeText(item.client_order_id, ""),
    symbol: normalizeText(item.symbol, "-"),
    side: normalizeEnumText(item.side, "").toUpperCase(),
    order_type: normalizeEnumText(item.type || item.order_type, "").toUpperCase(),
    type: normalizeEnumText(item.type || item.order_type, "").toUpperCase(),
    status: rawStatus ? rawStatus.toUpperCase() : "UNKNOWN",
    raw_status: rawStatus,
    quantity: toNumber(item.qty),
    qty: toNumber(item.qty),
    filled_qty: toNumber(item.filled_qty),
    filled_avg_price: toNumber(item.filled_avg_price),
    submitted_at: item.submitted_at || null,
    updated_at: item.updated_at || null,
  };
}

export function isOpenBrokerOrder(order = {}) {
  const normalized = order.raw_status ? order : normalizeBrokerOrder(order);
  if (!normalized.raw_status) return false;
  if (TERMINAL_ORDER_STATUSES.has(normalized.raw_status)) return false;
  return true;
}

export function normalizeBrokerTrade(item = {}) {
  const order = item.raw_status ? item : normalizeBrokerOrder(item);
  const isFilled = order.filled_qty > 0 || order.raw_status === "filled" || order.raw_status === "partially_filled";
  if (!isFilled) return null;
  return {
    id: order.id,
    symbol: order.symbol,
    side: order.side,
    quantity: order.filled_qty || order.quantity,
    price: order.filled_avg_price,
    realized_pnl: 0,
    created_at: order.updated_at || order.submitted_at,
    status: order.status,
  };
}

export function buildBrokerPortfolioSnapshot(summary) {
  if (!summary?.connected || !summary?.account) {
    return null;
  }

  const positions = (summary.positions || []).map(normalizeBrokerPosition);
  const orders = (summary.orders || []).map(normalizeBrokerOrder);
  const openOrders = orders.filter(isOpenBrokerOrder);
  const trades = orders
    .map(normalizeBrokerTrade)
    .filter(Boolean)
    .sort((a, b) => {
      const aTime = Date.parse(a.created_at || "") || 0;
      const bTime = Date.parse(b.created_at || "") || 0;
      return bTime - aTime;
    });

  const totalMarketValue = positions.reduce((sum, item) => sum + toNumber(item.market_value), 0);
  const totalUnrealizedPnl = positions.reduce((sum, item) => sum + toNumber(item.unrealized_pnl), 0);
  const investedCost = positions.reduce((sum, item) => sum + toNumber(item.cost_basis), 0);
  const totalEquity = toNumber(summary.account.equity || summary.account.portfolio_value);
  const cashBalance = toNumber(summary.account.cash);

  return {
    source: "broker",
    mode: summary.mode || "live",
    account: summary.account,
    positions,
    items: positions,
    orders,
    open_orders: openOrders,
    trades,
    summary: {
      total_equity: totalEquity,
      portfolio_value: totalEquity || toNumber(summary.account.portfolio_value),
      cash_balance: cashBalance,
      total_market_value: totalMarketValue,
      total_unrealized_pnl: totalUnrealizedPnl,
      total_realized_pnl: 0,
      open_positions: positions.length,
      open_orders: openOrders.length,
      invested_cost: investedCost,
      total_trades: trades.length,
      win_rate_pct: null,
      starting_cash: totalEquity || cashBalance,
    },
  };
}
