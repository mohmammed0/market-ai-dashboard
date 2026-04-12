import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
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
import SymbolPicker from "../components/ui/SymbolPicker";
import SymbolMultiPicker from "../components/ui/SymbolMultiPicker";
import useDecisionSurface from "../hooks/useDecisionSurface";
import useJobRunner from "../hooks/useJobRunner";
import {
  cancelPaperOrder,
  createPaperOrder,
  fetchPaperControlPanel,
  refreshPaperSignals,
} from "../lib/api";
import { parseSymbolList } from "../lib/forms";
import { t } from "../lib/i18n";
import { useWorkspace } from "../lib/useWorkspace";


export default function PaperTradingPage() {
  const todayIso = new Date().toISOString().slice(0, 10);
  const { workspace, activeWatchlist } = useWorkspace();
  const [portfolio, setPortfolio] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [signals, setSignals] = useState(null);
  const [trades, setTrades] = useState(null);
  const [orders, setOrders] = useState(null);
  const [broker, setBroker] = useState(null);
  const [audit, setAudit] = useState(null);
  const [controlSummary, setControlSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [operatorSymbol, setOperatorSymbol] = useState("AAPL");
  const [activeTab, setActiveTab] = useState("positions");
  const [searchParams] = useSearchParams();
  const refreshJob = useJobRunner("paper_signal_refresh", { recentLimit: 6 });

  const { control, register, handleSubmit, setValue, watch } = useForm({
    defaultValues: { symbolsText: "AAPL,MSFT,NVDA,SPY", mode: "classic", startDate: "2024-01-01", endDate: todayIso, quantity: 1 },
  });

  const { control: orderControl, register: registerOrder, handleSubmit: handleSubmitOrder, reset: resetOrderForm } = useForm({
    defaultValues: { symbol: "AAPL", side: "BUY", quantity: 1, orderType: "market", limitPrice: "", strategyMode: "manual", notes: "" },
  });

  const watchedStartDate = watch("startDate");
  const watchedEndDate = watch("endDate");
  const { decision, loading: decisionLoading, error: decisionError, refreshDecision } = useDecisionSurface({
    symbol: operatorSymbol, startDate: watchedStartDate, endDate: watchedEndDate, enabled: Boolean(operatorSymbol),
  });
  const watchedSymbols = parseSymbolList(watch("symbolsText"));

  async function loadAll() {
    setLoading(true);
    try {
      const panel = await fetchPaperControlPanel();
      setPortfolio(panel.portfolio);
      setAlerts(panel.alerts);
      setSignals(panel.signals);
      setTrades(panel.trades);
      setOrders(panel.open_orders);
      setBroker(panel.broker);
      setAudit(panel.audit);
      setControlSummary(panel.summary);
    } catch (e) {
      setPageError(e.message || "Failed to load paper trading data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll(); }, []);

  useEffect(() => {
    const symbol = searchParams.get("symbol");
    if (symbol) {
      const s = symbol.trim().toUpperCase();
      setOperatorSymbol(s);
      setValue("symbolsText", s);
      resetOrderForm({ symbol: s, side: "BUY", quantity: 1, orderType: "market", limitPrice: "", strategyMode: "manual", notes: "" });
      return;
    }
    const ws = workspace?.active_symbol || activeWatchlist?.symbols?.[0] || "AAPL";
    setOperatorSymbol(ws);
    setValue("symbolsText", (activeWatchlist?.symbols?.slice(0, 4) || [ws]).join(","));
    resetOrderForm({ symbol: ws, side: "BUY", quantity: 1, orderType: "market", limitPrice: "", strategyMode: "manual", notes: "" });
  }, [searchParams, workspace?.active_symbol, activeWatchlist?.symbols]);

  useEffect(() => {
    if (refreshJob.currentJob?.status === "completed") {
      loadAll();
      refreshDecision({ symbol: operatorSymbol }).catch(() => {});
    }
  }, [refreshJob.currentJob?.job_id, refreshJob.currentJob?.status]);

  async function onSubmit(values) {
    setPageError("");
    await refreshJob.submit(() => refreshPaperSignals({
      symbols: parseSymbolList(values.symbolsText), mode: values.mode,
      start_date: values.startDate, end_date: values.endDate,
      auto_execute: true, quantity: Number(values.quantity || 1),
    }));
  }

  async function onOrderSubmit(values) {
    setPageError("");
    try {
      const s = String(values.symbol || "").trim().toUpperCase();
      await createPaperOrder({
        symbol: s, side: values.side, quantity: Number(values.quantity || 1),
        order_type: values.orderType, limit_price: values.orderType === "limit" ? Number(values.limitPrice || 0) : null,
        strategy_mode: values.strategyMode, notes: values.notes || null,
      });
      setOperatorSymbol(s);
      await loadAll();
      refreshDecision({ symbol: s }).catch(() => {});
      resetOrderForm({ symbol: s, side: "BUY", quantity: 1, orderType: "market", limitPrice: "", strategyMode: "manual", notes: "" });
    } catch (e) {
      setPageError(e.message || "Order creation failed.");
    }
  }

  async function handleCancel(orderId) {
    try { await cancelPaperOrder(orderId); await loadAll(); } catch (e) { setPageError(e.message); }
  }

  const portfolioColumns = useMemo(() => [
    { accessorKey: "symbol", header: "الرمز", cell: ({ row }) => (
      <button className="cell-primary cell-link" type="button" onClick={() => { setOperatorSymbol(row.original.symbol); refreshDecision({ symbol: row.original.symbol }).catch(() => {}); }}>
        {row.original.symbol}
      </button>
    )},
    { accessorKey: "side", header: "الجانب", cell: ({ row }) => <StatusBadge label={row.original.side} tone={row.original.side === "LONG" || row.original.side === "BUY" ? "positive" : "negative"} dot={false} /> },
    { accessorKey: "quantity", header: "الكمية", cell: ({ row }) => <span className="cell-mono">{row.original.quantity}</span> },
    { accessorKey: "avg_entry_price", header: "الدخول", cell: ({ row }) => <span className="cell-mono">{Number(row.original.avg_entry_price)?.toFixed(2) ?? "-"}</span> },
    { accessorKey: "current_price", header: "السعر الحالي", cell: ({ row }) => <span className="cell-mono">{Number(row.original.current_price)?.toFixed(2) ?? "-"}</span> },
    { accessorKey: "unrealized_pnl", header: "PnL غير محققة", cell: ({ row }) => {
      const pnl = Number(row.original.unrealized_pnl);
      const pct = row.original.avg_entry_price ? ((pnl / (Number(row.original.avg_entry_price) * Number(row.original.quantity || 1))) * 100).toFixed(1) : null;
      return (
        <div className="pnl-cell">
          <span className={pnl >= 0 ? "cell-positive" : "cell-negative"}>{isNaN(pnl) ? "-" : pnl.toFixed(2)}</span>
          {pct && <small className={pnl >= 0 ? "cell-positive" : "cell-negative"}>{pnl >= 0 ? "+" : ""}{pct}%</small>}
        </div>
      );
    }},
  ], []);

  const tradeColumns = useMemo(() => [
    { accessorKey: "symbol", header: "الرمز", cell: ({ row }) => <span className="cell-primary">{row.original.symbol}</span> },
    { accessorKey: "action", header: "الإجراء" },
    { accessorKey: "side", header: "الجانب", cell: ({ row }) => <StatusBadge label={row.original.side} tone={row.original.side === "BUY" ? "positive" : "negative"} dot={false} /> },
    { accessorKey: "quantity", header: "الكمية", cell: ({ row }) => {
      const fd = row.original.fill_details;
      return <span className="cell-mono">{row.original.quantity}{fd?.is_partial ? <StatusBadge label="جزئي" tone="warning" dot={false} /> : null}</span>;
    }},
    { accessorKey: "price", header: "السعر", cell: ({ row }) => <span className="cell-mono">{Number(row.original.price)?.toFixed(2) ?? "-"}</span> },
    { accessorKey: "realized_pnl", header: "PnL", cell: ({ row }) => {
      const pnl = Number(row.original.realized_pnl);
      return <span className={pnl >= 0 ? "cell-positive" : "cell-negative"}>{isNaN(pnl) ? "-" : pnl.toFixed(2)}</span>;
    }},
    { accessorKey: "fill_details", header: "تفاصيل التنفيذ", cell: ({ row }) => {
      const fd = row.original.fill_details;
      if (!fd) return <span className="text-muted">—</span>;
      const slippage = fd.fill_price && fd.reference_price ? (Number(fd.fill_price) - Number(fd.reference_price)).toFixed(4) : null;
      return (
        <div className="fill-detail-cell">
          <div className="fill-detail-row"><span className="fill-detail-key">مرجع</span><span className="cell-mono">{Number(fd.reference_price)?.toFixed(2) ?? "-"}</span></div>
          <div className="fill-detail-row"><span className="fill-detail-key">تعبئة</span><span className="cell-mono">{Number(fd.fill_price)?.toFixed(2) ?? "-"}</span></div>
          {slippage && <div className="fill-detail-row"><span className="fill-detail-key">انزلاق</span><span className={`cell-mono ${Number(slippage) > 0 ? "cell-negative" : "cell-positive"}`}>{slippage}</span></div>}
          <div className="fill-detail-row"><span className="fill-detail-key">رسوم</span><span className="cell-mono">{fd.fee_amount ?? 0}</span></div>
          {fd.spread && <div className="fill-detail-row"><span className="fill-detail-key">هامش</span><span className="cell-mono">{fd.spread}</span></div>}
        </div>
      );
    }},
  ], []);

  const orderColumns = useMemo(() => [
    { accessorKey: "symbol", header: "الرمز", cell: ({ row }) => <span className="cell-primary">{row.original.symbol}</span> },
    { accessorKey: "side", header: "الجانب" },
    { accessorKey: "order_type", header: "النوع" },
    { accessorKey: "quantity", header: "الكمية" },
    { accessorKey: "status", header: "الحالة", cell: ({ row }) => <StatusBadge label={row.original.status} tone={row.original.status === "OPEN" ? "info" : "neutral"} dot={false} /> },
    { accessorKey: "fill_details", header: "المحاكاة", cell: ({ row }) => {
      const fd = row.original.fill_details;
      if (!fd) return "-";
      return <span className="cell-mono">{fd.fill_price} (fee={fd.fee_amount})</span>;
    }},
    { accessorKey: "id", header: "إجراء", cell: ({ row }) => (
      <div className="market-action-links">
        <button className="btn btn-ghost btn-xs" type="button" onClick={() => { setOperatorSymbol(row.original.symbol); refreshDecision({ symbol: row.original.symbol }).catch(() => {}); }}>متابعة</button>
        {row.original.status === "OPEN" && <button className="btn btn-danger btn-xs" type="button" onClick={() => handleCancel(row.original.id)}>إلغاء</button>}
      </div>
    )},
  ], []);

  const chartSummaryItems = [
    { label: "الرمز", value: operatorSymbol, badge: "Paper" },
    { label: "الموقف", value: decision?.stance || "-", tone: decision?.stance === "BUY" ? "positive" : decision?.stance === "SELL" ? "negative" : "warning" },
    { label: "الأوامر", value: controlSummary?.open_orders ?? 0 },
    { label: "المراكز", value: controlSummary?.open_positions ?? 0 },
  ];

  return (
    <PageFrame
      title="التداول التجريبي"
      description="مركز تشغيل ورقي: المحفظة، الشارت، القرار، والأوامر."
      eyebrow="التنفيذ الورقي"
      headerActions={
        <>
          <StatusBadge label={broker?.mode || "paper"} tone="info" dot={false} />
          <StatusBadge label={operatorSymbol} tone="positive" />
        </>
      }
    >
      <ErrorBanner message={pageError || refreshJob.error} />

      {/* Safety Notice */}
      <div className="warning-banner">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
        تداول ورقي فقط — التنفيذ الحي غير مفعّل.
      </div>

      {/* KPI Strip */}
      {!loading && controlSummary && (
        <SummaryStrip items={[
          { label: "المراكز المفتوحة", value: controlSummary.open_positions ?? 0 },
          { label: "الأوامر المفتوحة", value: controlSummary.open_orders ?? 0 },
          { label: "التنفيذات", value: controlSummary.recent_trades ?? 0 },
          { label: "الوسيط", value: controlSummary.broker_connected ? "متصل" : "غير متصل", tone: controlSummary.broker_connected ? "positive" : "warning" },
          { label: "الوضع", value: controlSummary.broker_mode || "paper" },
        ]} />
      )}

      {/* Chart + Decision */}
      <div className="command-grid">
        <TradingChart
          className="col-span-7"
          title="الشارت التشغيلي"
          description="القرار المهيكل لرمز التشغيل."
          decision={decision}
          summaryItems={chartSummaryItems}
          loading={decisionLoading}
          height={440}
        />

        <DecisionPanel
          className="col-span-5"
          decision={decision}
          loading={decisionLoading}
          error={decisionError}
          title="القرار الحالي"
          description="قبل إرسال أو إلغاء أي نشاط ورقي."
        />
      </div>

      {/* Order Entry */}
      <div className="command-grid">
        <SectionCard className="col-span-7" title="إنشاء أمر ورقي" description="إدخال يدوي سريع.">
          <form className="analyze-form" onSubmit={handleSubmitOrder(onOrderSubmit)}>
            <div className="form-grid">
              <div className="field field-span-2">
                <Controller
                  name="symbol"
                  control={orderControl}
                  render={({ field }) => (
                    <SymbolPicker
                      compact
                      label={t("Symbol")}
                      value={field.value}
                      onChange={field.onChange}
                      onSelect={(item) => { field.onChange(item.symbol); setOperatorSymbol(item.symbol); }}
                    />
                  )}
                />
              </div>
              <label className="field"><span>الجانب</span><select {...registerOrder("side")}><option value="BUY">شراء</option><option value="SELL">بيع</option></select></label>
              <label className="field"><span>النوع</span><select {...registerOrder("orderType")}><option value="market">سوقي</option><option value="limit">حدي</option></select></label>
              <label className="field"><span>الكمية</span><input type="number" min="1" step="1" {...registerOrder("quantity")} /></label>
              <label className="field"><span>السعر الحدي</span><input type="number" step="0.01" {...registerOrder("limitPrice")} /></label>
            </div>
            <div className="form-actions">
              <button className="btn btn-primary" type="submit">إنشاء أمر</button>
              <button className="btn btn-secondary" type="button" onClick={() => refreshDecision({ symbol: operatorSymbol }).catch(() => {})} disabled={decisionLoading}>
                مزامنة القرار
              </button>
            </div>
          </form>
        </SectionCard>

        {/* Signal Refresh */}
        <SectionCard className="col-span-5" title="تحديث الإشارات" description="تحديث دفعي وتنفيذ تلقائي.">
          <form className="analyze-form" onSubmit={handleSubmit(onSubmit)}>
            <div className="form-grid">
              <div className="field field-span-2">
                <SymbolMultiPicker label={t("Symbols")} symbols={watchedSymbols} onChange={(s) => setValue("symbolsText", s.join(","), { shouldValidate: true })} />
              </div>
              <label className="field"><span>الوضع</span><select {...register("mode")}><option value="classic">كلاسيكي</option><option value="ml">ML</option><option value="dl">DL</option><option value="ensemble">تجميعي</option></select></label>
              <label className="field"><span>الكمية</span><input type="number" min="1" {...register("quantity")} /></label>
            </div>
            <div className="form-actions">
              <button className="btn btn-primary" type="submit" disabled={refreshJob.submitting}>
                {refreshJob.submitting ? "جارٍ..." : "��حديث ومحاكاة"}
              </button>
            </div>
          </form>
        </SectionCard>
      </div>

      {/* Data Tabs */}
      <SectionCard flush>
        <div className="tab-nav" style={{ padding: "0 var(--space-5)" }}>
          {[
            { id: "positions", label: "المراكز" },
            { id: "orders", label: "الأوامر" },
            { id: "trades", label: "الصفقات" },
            { id: "signals", label: "الإشارات" },
            { id: "alerts", label: "التنبيهات" },
          ].map((tab) => (
            <button
              key={tab.id}
              className={`tab-nav-item${activeTab === tab.id ? " active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{ padding: "var(--space-4) var(--space-5)" }}>
          {loading ? <LoadingSkeleton lines={5} /> : (
            <>
              {activeTab === "positions" && (
                <>
                  {portfolio?.summary && (
                    <SummaryStrip compact items={[
                      { label: "القيمة السوقية", value: portfolio.summary.total_market_value ?? 0 },
                      { label: "PnL غير محققة", value: portfolio.summary.total_unrealized_pnl ?? 0, tone: Number(portfolio.summary.total_unrealized_pnl) >= 0 ? "positive" : "negative" },
                      { label: "PnL محققة", value: portfolio.summary.total_realized_pnl ?? 0 },
                    ]} />
                  )}
                  <div style={{ marginTop: "var(--space-3)" }}>
                    <DataTable columns={portfolioColumns} data={portfolio?.items || []} emptyTitle="لا توجد مراكز" emptyDescription="حدّث الإشارات لإنشاء مراكز." />
                  </div>
                </>
              )}
              {activeTab === "orders" && (
                <DataTable columns={orderColumns} data={orders?.items || []} emptyTitle="لا توجد أوامر مفتوحة" emptyDescription="أنشئ أمراً ورقياً من النموذج أعلاه." />
              )}
              {activeTab === "trades" && (
                <DataTable columns={tradeColumns} data={trades?.items || []} emptyTitle="لا توجد صفقات" emptyDescription="ستظهر بعد تنفيذ ال��شارات." />
              )}
              {activeTab === "signals" && (
                <DataTable
                  columns={[
                    { accessorKey: "symbol", header: "الرمز" },
                    { accessorKey: "strategy_mode", header: "الوضع" },
                    { accessorKey: "signal", header: "الإشارة", cell: ({ row }) => <SignalBadge signal={row.original.signal} /> },
                    { accessorKey: "confidence", header: "الثقة" },
                    { accessorKey: "price", header: "السعر" },
                  ]}
                  data={signals?.items || []}
                  emptyTitle="لا يوجد سجل إشارات"
                  emptyDescription="سيظهر بعد التحديث."
                />
              )}
              {activeTab === "alerts" && (
                <DataTable
                  columns={[
                    { accessorKey: "symbol", header: "الرمز" },
                    { accessorKey: "alert_type", header: "النوع" },
                    { accessorKey: "severity", header: "الشدة", cell: ({ row }) => <StatusBadge label={row.original.severity} tone={row.original.severity === "warning" ? "warning" : "neutral"} dot={false} /> },
                    { accessorKey: "message", header: "الرسالة" },
                  ]}
                  data={alerts?.items || []}
                  emptyTitle="لا توجد تنبيهات"
                  emptyDescription="ستظهر بعد تحديث الإشارات."
                />
              )}
            </>
          )}
        </div>
      </SectionCard>
    </PageFrame>
  );
}
