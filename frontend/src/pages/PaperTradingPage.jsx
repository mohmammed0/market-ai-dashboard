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
import SymbolPicker from "../components/ui/SymbolPicker";
import TradingChart from "../components/ui/TradingChart";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { liquidateBrokerPortfolio } from "../api/broker";
import useDecisionSurface from "../hooks/useDecisionSurface";
import useJobRunner from "../hooks/useJobRunner";
import { cancelPaperOrder, refreshPaperSignals } from "../lib/api";
import { buildRecentDateRange } from "../lib/dateDefaults";
import { useAppData, useAppStore } from "../store/AppDataStore";
import { useWorkspace } from "../lib/useWorkspace";

const FALLBACK_FOCUSED_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "SPY", "QQQ"];

export default function PaperTradingPage() {
  const { startDate: defaultStartDate, todayIso } = buildRecentDateRange();
  const { workspace, activeWatchlist, favoriteSymbols } = useWorkspace();
  const [searchParams, setSearchParams] = useSearchParams();
  const [operatorSymbol, setOperatorSymbol] = useState("AAPL");
  const [activeTab, setActiveTab] = useState("positions");
  const [pageError, setPageError] = useState("");
  const [liquidationBusy, setLiquidationBusy] = useState(false);
  const [liquidationResult, setLiquidationResult] = useState(null);

  // Use pre-fetched data from global store
  const { data: portfolioSnapshot, loading: portfolioSnapshotLoading } = useAppData("portfolioSnapshot");
  const { data: signals, loading: signalsLoading } = useAppData("paperSignals");
  const { data: dashboardLite } = useAppData("dashboardLite");
  const { fetchSection } = useAppStore() || {};
  const usingBrokerData = String(portfolioSnapshot?.active_source || "").startsWith("broker");
  const sourceLabel = portfolioSnapshot?.source_label || "Broker Paper";
  const brokerStatus = portfolioSnapshot?.broker_status || {};
  const positionsSectionLoading = portfolioSnapshotLoading;
  const ordersSectionLoading = portfolioSnapshotLoading;
  const tradesSectionLoading = portfolioSnapshotLoading;

  const loading = portfolioSnapshotLoading;

  const refreshJob = useJobRunner("paper_signal_refresh", { recentLimit: 6 });
  const lightweightExperimentMode = Boolean(dashboardLite?.product_scope?.lightweight_experiment_mode);
  const dlEnabled = Boolean(dashboardLite?.product_scope?.dl_enabled);

  const { decision, loading: decisionLoading, error: decisionError, refreshDecision } = useDecisionSurface({
    symbol: operatorSymbol,
    startDate: defaultStartDate,
    endDate: todayIso,
    includeDl: dlEnabled,
    enabled: Boolean(operatorSymbol),
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
        fetchSection("portfolioSnapshot", "/api/portfolio/snapshot", { forceFresh: true });
        fetchSection("paperSignals", "/api/paper/signals", { forceFresh: true });
      }
      refreshDecision({ symbol: operatorSymbol }).catch(() => {});
    }
  }, [refreshJob.currentJob?.job_id, refreshJob.currentJob?.status]);

  async function handleSignalRefresh() {
    setPageError("");
    const watchlistSymbols = focusedSymbols.slice(0, 8) || [operatorSymbol];
    await refreshJob.submit(() => refreshPaperSignals({
      symbols: watchlistSymbols, mode: lightweightExperimentMode ? "ensemble" : "classic",
      start_date: defaultStartDate, end_date: todayIso,
      auto_execute: true, quantity: 1,
    }));
  }

  async function handleLiquidate() {
    setPageError("");
    setLiquidationResult(null);
    if (!usingBrokerData || !brokerStatus?.paper) {
      setPageError("تسييل المحفظة مسموح فقط عندما يكون مصدر التنفيذ هو الحساب الورقي للوسيط.");
      return;
    }
    if (!window.confirm("سيتم إغلاق كل المراكز المفتوحة في الحساب الورقي وتحويلها إلى كاش. هل تريد المتابعة؟")) {
      return;
    }
    setLiquidationBusy(true);
    try {
      const response = await liquidateBrokerPortfolio({ cancel_open_orders: true });
      setLiquidationResult(response);
      if (fetchSection) {
        await fetchSection("portfolioSnapshot", "/api/portfolio/snapshot", { forceFresh: true });
        await fetchSection("paperSignals", "/api/paper/signals", { forceFresh: true });
        await fetchSection("dashboardLite", "/api/dashboard/lite", { forceFresh: true });
      }
      refreshDecision({ symbol: operatorSymbol }).catch(() => {});
      setActiveTab("positions");
    } catch (error) {
      setPageError(error.message || "تعذر تسييل المحفظة الورقية.");
    } finally {
      setLiquidationBusy(false);
    }
  }

  async function handleCancel(orderId) {
    try {
      await cancelPaperOrder(orderId);
      if (fetchSection) fetchSection("portfolioSnapshot", "/api/portfolio/snapshot", { forceFresh: true });
    } catch (e) {
      setPageError(e.message);
    }
  }

  const positions = useMemo(() => portfolioSnapshot?.positions || [], [portfolioSnapshot]);
  const summary = portfolioSnapshot?.summary || {};

  // Orders list
  const openOrders = useMemo(() => portfolioSnapshot?.open_orders || [], [portfolioSnapshot]);

  // Trades list
  const tradesList = useMemo(() => portfolioSnapshot?.trades || [], [portfolioSnapshot]);

  // Signals list
  const signalsList = useMemo(() => {
    return signals?.signals || signals?.items || (Array.isArray(signals) ? signals : []);
  }, [signals]);

  const focusedSymbols = useMemo(() => {
    const symbols = dashboardLite?.product_scope?.sample_symbols;
    return Array.isArray(symbols) && symbols.length ? symbols : FALLBACK_FOCUSED_SYMBOLS;
  }, [dashboardLite]);

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
    { accessorKey: "status", header: "الحالة", cell: ({ row }) => {
      const status = String(row.original.status || "").toUpperCase();
      const isOpenLike = !["FILLED", "CANCELED", "CANCELLED", "EXPIRED", "REJECTED", "REPLACED", "SUSPENDED"].includes(status);
      return <StatusBadge label={row.original.status} tone={isOpenLike ? "info" : "neutral"} dot={false} />;
    }},
    { accessorKey: "id", header: "إجراء", cell: ({ row }) => (
      !["FILLED", "CANCELED", "CANCELLED", "EXPIRED", "REJECTED", "REPLACED", "SUSPENDED"].includes(String(row.original.status || "").toUpperCase())
        ? <button className="btn btn-danger btn-xs" type="button" onClick={() => handleCancel(row.original.id)}>إلغاء</button>
        : null
    )},
  ], []);

  const signalColumns = useMemo(() => [
    { accessorKey: "symbol", header: "الرمز", cell: ({ row }) => <span className="cell-primary">{row.original.symbol}</span> },
    { accessorKey: "signal", header: "الإشارة", cell: ({ row }) => <SignalBadge signal={row.original.signal || row.original.action} /> },
    { accessorKey: "confidence", header: "الثقة", cell: ({ row }) => <span className="cell-mono">{row.original.confidence ?? "-"}</span> },
    { accessorKey: "reason", header: "السبب", cell: ({ row }) => <span>{row.original.reason || row.original.reasons || "-"}</span> },
  ], []);

  const quickSymbols = useMemo(() => {
    const seen = new Set();
    return [operatorSymbol, ...(favoriteSymbols || []), ...((activeWatchlist?.symbols || []).slice(0, 4)), ...focusedSymbols]
      .filter((item) => {
        const normalized = String(item || "").trim().toUpperCase();
        if (!normalized || seen.has(normalized)) return false;
        seen.add(normalized);
        return true;
      })
      .slice(0, 8);
  }, [operatorSymbol, favoriteSymbols, activeWatchlist?.symbols, focusedSymbols]);

  function handleOperatorSelect(item) {
    const normalized = String(item?.symbol || item || "").trim().toUpperCase();
    if (!normalized) return;
    setOperatorSymbol(normalized);
    const params = new URLSearchParams(searchParams);
    params.set("symbol", normalized);
    setSearchParams(params);
  }

  return (
    <PageFrame
      title="حساب الوسيط الورقي"
      description="المراكز والأوامر والعمليات من حساب الوسيط الورقي الخارجي، بدون محاكاة تنفيذ داخلية."
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
          المصدر الحالي: {sourceLabel}. لا يوجد محرك تداول ورقي داخلي نشط. الرصيد والمراكز والأوامر والصفقات تأتي من حساب Alpaca الورقي المتصل، بينما تبويب الإشارات يعرض قرارات التحليل فقط.
        </div>
      )}

      <SectionCard
        title="سياق التنفيذ"
        description="اختر الرمز التشغيلي من نفس القائمة canonical المستخدمة في السوق المباشر ومحطة التحليل."
        action={<StatusBadge label={sourceLabel} tone={usingBrokerData ? "info" : "warning"} dot={false} />}
      >
        <div className="paper-operator-shell">
          <div className="paper-operator-main">
            <SymbolPicker
              label="الرمز النشط"
              value={operatorSymbol}
              onChange={setOperatorSymbol}
              onSelect={handleOperatorSelect}
              placeholder="ابحث عن رمز للتنفيذ أو المراجعة"
              helperText="اختيار الرمز هنا يحدّث مساحة القرار مباشرة مع إبقاء بيانات المحفظة كما هي."
            />
            <div className="workspace-symbol-actions">
              {quickSymbols.map((item) => (
                <button
                  key={item}
                  className={`workspace-symbol-chip${item === operatorSymbol ? " active" : ""}`}
                  type="button"
                  onClick={() => handleOperatorSelect(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            <div className="info-banner" style={{ marginTop: 12 }}>
              الكون التشغيلي الحالي: {focusedSymbols.join("، ")}
            </div>
            {usingBrokerData && brokerStatus?.paper ? (
              <div className="info-banner" style={{ marginTop: 12, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <span>
                  اختبار fresh paper يعتمد على تسييل المراكز القديمة ثم إعادة تركيز الجولات على الكون المحدود فقط.
                </span>
                <button className="btn btn-danger btn-sm" type="button" onClick={() => handleLiquidate().catch(() => {})} disabled={liquidationBusy || positions.length === 0}>
                  {liquidationBusy ? "جارٍ تسييل المحفظة..." : "تسييل المحفظة الورقية"}
                </button>
              </div>
            ) : null}
            {liquidationResult?.audit ? (
              <div className="info-banner" style={{ marginTop: 12 }}>
                قبل التسييل: {liquidationResult.audit.before_positions} مراكز / {liquidationResult.audit.before_open_orders} أوامر.
                بعد التسييل: {liquidationResult.audit.after_positions} مراكز / {liquidationResult.audit.after_open_orders} أوامر.
              </div>
            ) : null}
          </div>
          <div className="paper-operator-stats">
            <MetricCard label="المصدر" value={sourceLabel} detail={usingBrokerData ? "Broker-connected snapshot" : "Internal simulated snapshot"} />
            <MetricCard label="المراكز" value={summary.open_positions ?? positions.length ?? 0} detail="Open positions" />
            <MetricCard label="الأوامر المفتوحة" value={openOrders.length} detail="Open orders" />
            <MetricCard label="الصفقات" value={tradesList.length} detail="Trade history" />
          </div>
        </div>
      </SectionCard>

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
