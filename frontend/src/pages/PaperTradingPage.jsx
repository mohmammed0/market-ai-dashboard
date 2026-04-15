import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import DecisionPanel from "../components/ui/DecisionPanel";
import PageFrame from "../components/ui/PageFrame";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import SectionCard from "../components/ui/SectionCard";
import SignalBadge from "../components/ui/SignalBadge";
import TradingChart from "../components/ui/TradingChart";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import useDecisionSurface from "../hooks/useDecisionSurface";
import useJobRunner from "../hooks/useJobRunner";
import { buildBrokerPortfolioSnapshot } from "../lib/brokerPortfolio";
import { cancelPaperOrder, refreshPaperSignals } from "../lib/api";
import { useAppData, useAppStore } from "../store/AppDataStore";
import { useWorkspace } from "../lib/useWorkspace";


export default function PaperTradingPage() {
  const todayIso = new Date().toISOString().slice(0, 10);
  const { workspace, activeWatchlist } = useWorkspace();
  const [searchParams] = useSearchParams();
  const [operatorSymbol, setOperatorSymbol] = useState("AAPL");
  const [activeTab, setActiveTab] = useState("positions");
  const [pageError, setPageError] = useState("");

  // Use pre-fetched data from global store
  const { data: portfolio, loading: portfolioLoading } = useAppData("paperPortfolio");
  const { data: orders, loading: ordersLoading } = useAppData("paperOrders");
  const { data: trades, loading: tradesLoading } = useAppData("paperTrades");
  const { data: signals, loading: signalsLoading } = useAppData("paperSignals");
  const { data: brokerStatus } = useAppData("brokerStatus");
  const { data: brokerSummary, loading: brokerSummaryLoading } = useAppData("brokerSummary");
  const { fetchSection } = useAppStore() || {};
  const brokerPortfolio = useMemo(() => buildBrokerPortfolioSnapshot(brokerSummary), [brokerSummary]);
  const brokerDataConnected = Boolean(brokerStatus?.connected || brokerSummary?.connected);
  const usingBrokerData = Boolean(brokerDataConnected && brokerPortfolio);
  const positionsSectionLoading = usingBrokerData ? brokerSummaryLoading : portfolioLoading;
  const ordersSectionLoading = usingBrokerData ? brokerSummaryLoading : ordersLoading;
  const tradesSectionLoading = usingBrokerData ? brokerSummaryLoading : tradesLoading;

  const loading = brokerDataConnected ? brokerSummaryLoading : portfolioLoading && ordersLoading;

  const refreshJob = useJobRunner("paper_signal_refresh", { recentLimit: 6 });

  const { decision, loading: decisionLoading, error: decisionError, refreshDecision } = useDecisionSurface({
    symbol: operatorSymbol, startDate: "2024-01-01", endDate: todayIso, enabled: Boolean(operatorSymbol),
  });

  // Set symbol from URL params or workspace
  useEffect(() => {
    const symbol = searchParams.get("symbol");
    if (symbol) {
      setOperatorSymbol(symbol.trim().toUpperCase());
      return;
    }
    const ws = workspace?.active_symbol || activeWatchlist?.symbols?.[0] || "AAPL";
    setOperatorSymbol(ws);
  }, [searchParams, workspace?.active_symbol, activeWatchlist?.symbols]);

  // Refresh store data after signal refresh completes
  useEffect(() => {
    if (refreshJob.currentJob?.status === "completed") {
      if (fetchSection) {
        fetchSection("paperPortfolio", "/api/paper/portfolio");
        fetchSection("paperOrders", "/api/paper/orders");
        fetchSection("paperTrades", "/api/paper/trades");
        fetchSection("paperSignals", "/api/paper/signals");
        fetchSection("brokerStatus", "/api/broker/status");
        fetchSection("brokerSummary", "/api/broker/summary");
      }
      refreshDecision({ symbol: operatorSymbol }).catch(() => {});
    }
  }, [refreshJob.currentJob?.job_id, refreshJob.currentJob?.status]);

  async function handleSignalRefresh() {
    setPageError("");
    const watchlistSymbols = activeWatchlist?.symbols?.slice(0, 8) || [operatorSymbol];
    await refreshJob.submit(() => refreshPaperSignals({
      symbols: watchlistSymbols, mode: "classic",
      start_date: "2024-01-01", end_date: todayIso,
      auto_execute: true, quantity: 1,
    }));
  }

  async function handleCancel(orderId) {
    try {
      await cancelPaperOrder(orderId);
      if (fetchSection) fetchSection("paperOrders", "/api/paper/orders");
    } catch (e) {
      setPageError(e.message);
    }
  }

  // Portfolio positions — API returns `items`, older shapes used `positions`
  const positions = useMemo(
    () => usingBrokerData ? brokerPortfolio?.items || [] : portfolio?.items || portfolio?.positions || [],
    [brokerPortfolio, portfolio, usingBrokerData]
  );
  const summary = usingBrokerData ? brokerPortfolio?.summary || {} : portfolio?.summary || {};

  // Orders list
  const openOrders = useMemo(() => {
    if (usingBrokerData) {
      return brokerPortfolio?.open_orders || [];
    }
    const rawOrders = orders?.orders || orders?.items || (Array.isArray(orders) ? orders : []);
    return rawOrders.filter(o => o.status === "OPEN" || o.status === "open");
  }, [brokerPortfolio, orders, usingBrokerData]);

  // Trades list
  const tradesList = useMemo(() => {
    if (usingBrokerData) {
      return brokerPortfolio?.trades || [];
    }
    return trades?.trades || trades?.items || (Array.isArray(trades) ? trades : []);
  }, [brokerPortfolio, trades, usingBrokerData]);

  // Signals list
  const signalsList = useMemo(() => {
    return signals?.signals || signals?.items || (Array.isArray(signals) ? signals : []);
  }, [signals]);

  const portfolioColumns = useMemo(() => [
    { accessorKey: "symbol", header: "الرمز", cell: ({ row }) => (
      <button className="cell-primary cell-link" type="button" onClick={() => { setOperatorSymbol(row.original.symbol); }}>
        {row.original.symbol}
      </button>
    )},
    { accessorKey: "side", header: "الجانب", cell: ({ row }) => <StatusBadge label={row.original.side} tone={row.original.side === "LONG" || row.original.side === "BUY" ? "positive" : "negative"} dot={false} /> },
    { accessorKey: "quantity", header: "الكمية", cell: ({ row }) => <span className="cell-mono">{row.original.quantity}</span> },
    { accessorKey: "avg_entry_price", header: "الدخول", cell: ({ row }) => <span className="cell-mono">{Number(row.original.avg_entry_price)?.toFixed(2) ?? "-"}</span> },
    { accessorKey: "current_price", header: "السعر الحالي", cell: ({ row }) => <span className="cell-mono">{Number(row.original.current_price)?.toFixed(2) ?? "-"}</span> },
    { accessorKey: "unrealized_pnl", header: "PnL غير محققة", cell: ({ row }) => {
      const pnl = Number(row.original.unrealized_pnl);
      return <span className={pnl >= 0 ? "cell-positive" : "cell-negative"}>{isNaN(pnl) ? "-" : pnl.toFixed(2)}</span>;
    }},
    { accessorKey: "stop_loss_price", header: "وقف الخسارة", cell: ({ row }) => {
      const sl = row.original.stop_loss_price;
      return sl ? <span className="cell-mono" style={{ color: "#FF9800" }}>${Number(sl).toFixed(2)}</span> : <span style={{ color: "var(--text-muted)" }}>—</span>;
    }},
    { accessorKey: "trailing_stop_pct", header: "الوقف المتحرك %", cell: ({ row }) => {
      const tp = row.original.trailing_stop_pct;
      return tp ? <span className="cell-mono" style={{ color: "#2196F3" }}>{Number(tp).toFixed(1)}%</span> : <span style={{ color: "var(--text-muted)" }}>—</span>;
    }},
    { accessorKey: "trailing_stop_price", header: "سعر الوقف المتحرك", cell: ({ row }) => {
      const tsp = row.original.trailing_stop_price;
      return tsp ? <span className="cell-mono" style={{ color: "#2196F3" }}>${Number(tsp).toFixed(2)}</span> : <span style={{ color: "var(--text-muted)" }}>—</span>;
    }},
    { accessorKey: "high_water_mark", header: "اعلى سعر", cell: ({ row }) => {
      const hwm = row.original.high_water_mark;
      return hwm ? <span className="cell-mono" style={{ color: "#089981" }}>${Number(hwm).toFixed(2)}</span> : <span style={{ color: "var(--text-muted)" }}>—</span>;
    }},
  ], []);

  const tradeColumns = useMemo(() => [
    { accessorKey: "symbol", header: "الرمز", cell: ({ row }) => <span className="cell-primary">{row.original.symbol}</span> },
    { accessorKey: "side", header: "الجانب", cell: ({ row }) => <StatusBadge label={row.original.side} tone={row.original.side === "BUY" ? "positive" : "negative"} dot={false} /> },
    { accessorKey: "quantity", header: "الكمية", cell: ({ row }) => <span className="cell-mono">{row.original.quantity}</span> },
    { accessorKey: "price", header: "السعر", cell: ({ row }) => <span className="cell-mono">{Number(row.original.price)?.toFixed(2) ?? "-"}</span> },
    { accessorKey: "realized_pnl", header: "PnL", cell: ({ row }) => {
      const pnl = Number(row.original.realized_pnl);
      return <span className={pnl >= 0 ? "cell-positive" : "cell-negative"}>{isNaN(pnl) ? "-" : pnl.toFixed(2)}</span>;
    }},
  ], []);

  const orderColumns = useMemo(() => [
    { accessorKey: "symbol", header: "الرمز", cell: ({ row }) => <span className="cell-primary">{row.original.symbol}</span> },
    { accessorKey: "side", header: "الجانب" },
    { accessorKey: "order_type", header: "النوع" },
    { accessorKey: "quantity", header: "الكمية" },
    { accessorKey: "status", header: "الحالة", cell: ({ row }) => <StatusBadge label={row.original.status} tone={row.original.status === "OPEN" ? "info" : "neutral"} dot={false} /> },
    { accessorKey: "id", header: "إجراء", cell: ({ row }) => (
      !usingBrokerData && row.original.status === "OPEN"
        ? <button className="btn btn-danger btn-xs" type="button" onClick={() => handleCancel(row.original.id)}>إلغاء</button>
        : null
    )},
  ], [usingBrokerData]);

  const signalColumns = useMemo(() => [
    { accessorKey: "symbol", header: "الرمز", cell: ({ row }) => <span className="cell-primary">{row.original.symbol}</span> },
    { accessorKey: "signal", header: "الإشارة", cell: ({ row }) => <SignalBadge signal={row.original.signal || row.original.action} /> },
    { accessorKey: "confidence", header: "الثقة", cell: ({ row }) => <span className="cell-mono">{row.original.confidence ?? "-"}</span> },
    { accessorKey: "reason", header: "السبب", cell: ({ row }) => <span>{row.original.reason || row.original.reasons || "-"}</span> },
  ], []);

  return (
    <PageFrame
      title="التداول الورقي"
      description="محفظة تداول ورقي مباشرة، إشارات ذكية، وأوامر مفتوحة."
      eyebrow="التداول"
      headerActions={
        <button
          className="btn btn-primary btn-sm"
          onClick={() => handleSignalRefresh().catch(() => {})}
          disabled={refreshJob.submitting}
          type="button"
        >
          {refreshJob.submitting ? "جارٍ تحديث الإشارات..." : "تحديث الإشارات"}
        </button>
      }
    >
      <ErrorBanner message={pageError} />
      {usingBrokerData && (
        <div className="info-banner">
          يتم عرض الرصيد والمراكز والأوامر والصفقات من حساب Alpaca المتصل. تبويب الإشارات ما زال يعتمد على محرك التحليل الداخلي.
        </div>
      )}

      {/* Portfolio Summary */}
      {loading ? <LoadingSkeleton lines={2} /> : (
        <SummaryStrip
          items={[
            { label: "إجمالي الرصيد", value: summary.total_equity ?? summary.portfolio_value ?? 0, badge: "$", tone: "positive" },
            { label: "الرصيد النقدي", value: summary.cash_balance ?? 0, badge: "$" },
            { label: "القيمة السوقية", value: summary.total_market_value ?? 0, badge: "$" },
            { label: "P&L غير محققة", value: summary.total_unrealized_pnl ?? 0, tone: Number(summary.total_unrealized_pnl || 0) >= 0 ? "positive" : "negative" },
            { label: "P&L محققة", value: summary.total_realized_pnl ?? 0, tone: Number(summary.total_realized_pnl || 0) >= 0 ? "positive" : "negative" },
            { label: "المراكز المفتوحة", value: summary.open_positions ?? 0 },
          ]}
        />
      )}

      {/* Main grid */}
      <div className="command-grid">
        {/* Chart + Decision */}
        <TradingChart
          className="col-span-7"
          title={`مساحة القرار — ${operatorSymbol}`}
          decision={decision}
          loading={decisionLoading}
          height={340}
        />

        <DecisionPanel
          className="col-span-5"
          decision={decision}
          loading={decisionLoading}
          error={decisionError}
          title="القرار الحالي"
        />

        {/* Tabs */}
        <div className="col-span-12">
          <div className="tab-bar" style={{ marginBottom: 12 }}>
            {[
              { key: "positions", label: "المراكز المفتوحة" },
              { key: "signals", label: "الإشارات" },
              { key: "orders", label: "الأوامر" },
              { key: "trades", label: "الصفقات" },
            ].map((tab) => (
              <button
                key={tab.key}
                className={`tab-btn${activeTab === tab.key ? " active" : ""}`}
                onClick={() => setActiveTab(tab.key)}
                type="button"
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === "positions" && (
            <SectionCard title="المراكز المفتوحة" description="أداء المراكز الحالية في الوقت الفعلي.">
              {positionsSectionLoading ? <LoadingSkeleton lines={5} /> : (
                positions.length
                  ? <DataTable columns={portfolioColumns} data={positions} />
                  : <div className="empty-state"><span className="empty-state-title">لا توجد مراكز مفتوحة</span></div>
              )}
            </SectionCard>
          )}

          {activeTab === "signals" && (
            <SectionCard title="إشارات التداول" description="آخر الإشارات الذكية المنتجة للمحفظة.">
              {signalsLoading ? <LoadingSkeleton lines={5} /> : (
                signalsList.length
                  ? <DataTable columns={signalColumns} data={signalsList} />
                  : <div className="empty-state"><span className="empty-state-title">لا توجد إشارات</span><span className="empty-state-text">اضغط "تحديث الإشارات" لتوليد إشارات جديدة.</span></div>
              )}
            </SectionCard>
          )}

          {activeTab === "orders" && (
            <SectionCard title="الأوامر المفتوحة" description="أوامر قيد التنفيذ.">
              {ordersSectionLoading ? <LoadingSkeleton lines={5} /> : (
                openOrders.length
                  ? <DataTable columns={orderColumns} data={openOrders} />
                  : <div className="empty-state"><span className="empty-state-title">لا توجد أوامر مفتوحة</span></div>
              )}
            </SectionCard>
          )}

          {activeTab === "trades" && (
            <SectionCard title="سجل الصفقات" description="الصفقات المنفذة.">
              {tradesSectionLoading ? <LoadingSkeleton lines={5} /> : (
                tradesList.length
                  ? <DataTable columns={tradeColumns} data={tradesList.slice(0, 50)} />
                  : <div className="empty-state"><span className="empty-state-title">لا توجد صفقات بعد</span></div>
              )}
            </SectionCard>
          )}
        </div>
      </div>
    </PageFrame>
  );
}
