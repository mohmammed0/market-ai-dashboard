import { useEffect, useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";

import PageFrame from "../components/PageFrame";
import ActionButton from "../components/ui/ActionButton";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import ResultCard from "../components/ui/ResultCard";
import SectionCard from "../components/ui/SectionCard";
import SignalBadge from "../components/ui/SignalBadge";
import SymbolMultiPicker from "../components/ui/SymbolMultiPicker";
import SymbolPicker from "../components/ui/SymbolPicker";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
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
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [searchParams] = useSearchParams();

  const { control, register, handleSubmit, setValue, watch } = useForm({
    defaultValues: {
      symbolsText: "AAPL,MSFT,NVDA,SPY",
      mode: "classic",
      startDate: "2024-01-01",
      endDate: "2026-04-02",
      quantity: 1,
    },
  });

  const {
    control: orderControl,
    register: registerOrder,
    handleSubmit: handleSubmitOrder,
    reset: resetOrderForm,
  } = useForm({
    defaultValues: {
      symbol: "AAPL",
      side: "BUY",
      quantity: 1,
      orderType: "market",
      limitPrice: "",
      strategyMode: "manual",
      notes: "",
    },
  });

  useEffect(() => {
    const symbol = searchParams.get("symbol");
    if (symbol) {
      const normalizedSymbol = symbol.trim().toUpperCase();
      setValue("symbolsText", symbol.trim().toUpperCase());
      resetOrderForm({
        symbol: normalizedSymbol,
        side: "BUY",
        quantity: 1,
        orderType: "market",
        limitPrice: "",
        strategyMode: "manual",
        notes: "",
      });
    }
  }, [searchParams, setValue, resetOrderForm]);

  useEffect(() => {
    const symbol = searchParams.get("symbol");
    if (symbol || !workspace?.active_symbol) {
      return;
    }
    const activeSymbols = activeWatchlist?.symbols?.slice(0, 4) || [workspace.active_symbol];
    setValue("symbolsText", activeSymbols.join(","));
    resetOrderForm({
      symbol: workspace.active_symbol,
      side: "BUY",
      quantity: 1,
      orderType: "market",
      limitPrice: "",
      strategyMode: "manual",
      notes: "",
    });
  }, [activeWatchlist?.symbols, resetOrderForm, searchParams, setValue, workspace?.active_symbol]);

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
    } catch (requestError) {
      setError(requestError.message || "Paper trading data failed to load.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function onSubmit(values) {
    setRefreshing(true);
    setError("");
    try {
      const data = await refreshPaperSignals({
        symbols: parseSymbolList(values.symbolsText),
        mode: values.mode,
        start_date: values.startDate,
        end_date: values.endDate,
        auto_execute: true,
        quantity: Number(values.quantity || 1),
      });
      setPortfolio(data.portfolio);
      setAlerts(data.alerts);
      setSignals(data.signals);
      await loadAll();
    } catch (requestError) {
      setError(requestError.message || "Paper signal refresh failed.");
    } finally {
      setRefreshing(false);
    }
  }

  async function onOrderSubmit(values) {
    setRefreshing(true);
    setError("");
    try {
      await createPaperOrder({
        symbol: values.symbol,
        side: values.side,
        quantity: Number(values.quantity || 1),
        order_type: values.orderType,
        limit_price: values.orderType === "limit" ? Number(values.limitPrice || 0) : null,
        strategy_mode: values.strategyMode,
        notes: values.notes || null,
      });
      await loadAll();
      resetOrderForm();
    } catch (requestError) {
      setError(requestError.message || "Paper order creation failed.");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleCancelOrder(orderId) {
    setRefreshing(true);
    setError("");
    try {
      await cancelPaperOrder(orderId);
      await loadAll();
    } catch (requestError) {
      setError(requestError.message || "Paper order cancel failed.");
    } finally {
      setRefreshing(false);
    }
  }

  const portfolioColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "strategy_mode", header: "Mode" },
      { accessorKey: "side", header: "Side" },
      { accessorKey: "quantity", header: "Qty" },
      { accessorKey: "avg_entry_price", header: "Entry" },
      { accessorKey: "current_price", header: "Price" },
      { accessorKey: "unrealized_pnl", header: "Unrealized PnL" },
      { accessorKey: "realized_pnl", header: "Realized PnL" },
    ],
    []
  );

  const signalColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "strategy_mode", header: "Mode" },
      {
        accessorKey: "signal",
        header: "Signal",
        cell: ({ row }) => <SignalBadge signal={row.original.signal} />,
      },
      { accessorKey: "confidence", header: "Confidence" },
      { accessorKey: "price", header: "Price" },
      { accessorKey: "reasoning", header: "Reasoning" },
    ],
    []
  );

  const alertColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "strategy_mode", header: "Mode" },
      { accessorKey: "alert_type", header: "Alert Type" },
      { accessorKey: "severity", header: "Severity" },
      { accessorKey: "message", header: "Message" },
    ],
    []
  );

  const tradeColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "strategy_mode", header: "Mode" },
      { accessorKey: "action", header: "Action" },
      { accessorKey: "side", header: "Side" },
      { accessorKey: "quantity", header: "Qty" },
      { accessorKey: "price", header: "Price" },
      { accessorKey: "realized_pnl", header: "Realized PnL" },
    ],
    []
  );

  const orderColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "side", header: "Side" },
      { accessorKey: "order_type", header: "Type" },
      { accessorKey: "quantity", header: "Qty" },
      { accessorKey: "limit_price", header: "Limit" },
      { accessorKey: "status", header: "Status" },
      {
        accessorKey: "id",
        header: "Action",
        cell: ({ row }) =>
          row.original.status === "OPEN" ? (
            <button className="secondary-button" type="button" onClick={() => handleCancelOrder(row.original.id)}>
              إلغاء
            </button>
          ) : "—",
      },
    ],
    []
  );

  const auditColumns = useMemo(
    () => [
      { accessorKey: "event_type", header: "الحدث" },
      { accessorKey: "symbol", header: "الرمز" },
      { accessorKey: "strategy_mode", header: "الوضع" },
      { accessorKey: "correlation_id", header: "معرّف الربط" },
      {
        accessorKey: "payload",
        header: "الحمولة",
        cell: ({ row }) => JSON.stringify(row.original.payload || {}).slice(0, 140) || "-",
      },
    ],
    []
  );

  return (
    <PageFrame
      title="التداول التجريبي"
      description="تنفيذ افتراضي محلي مع أوامر وتنبيهات وسجل إشارات وصفقات فوق المحركات الحالية، مع فصل واضح عن أي تنفيذ حي."
      eyebrow="مركز التنفيذ"
      headerActions={
        <>
          <ActionButton to="/risk" variant="secondary">لوحة المخاطر</ActionButton>
          <StatusBadge label="تنفيذ ورقي" tone="accent" />
        </>
      }
    >
      <SectionCard
        className="paper-summary-card"
        title="ملخص الحساب والتنفيذ"
        description="سطح تشغيل موحّد للتداول التجريبي فقط، مع حالة الوسيط وسجل التنفيذ والالتزام الواضح بعدم التفعيل الحي."
      >
        <div className="status-message warning">هذه الصفحة مخصصة للتداول الورقي والمحاكاة فقط. التنفيذ الحي غير مفعّل افتراضياً ولن يتم تفعيله بصمت.</div>
        {loading ? (
          <LoadingSkeleton lines={5} />
        ) : (
          <>
            <SummaryStrip
              items={[
                { label: "المراكز المفتوحة", value: controlSummary?.open_positions ?? 0 },
                { label: "الأوامر المفتوحة", value: controlSummary?.open_orders ?? 0 },
                { label: "التنفيذات الأخيرة", value: controlSummary?.recent_trades ?? 0 },
                { label: "التنبيهات الأخيرة", value: controlSummary?.recent_alerts ?? 0 },
                { label: "اتصال الوسيط", value: controlSummary?.broker_connected ? "متصل" : "غير متصل", tone: controlSummary?.broker_connected ? "accent" : "warning" },
                { label: "وضع الوسيط", value: controlSummary?.broker_mode || "paper" },
              ]}
            />
            <div className="result-grid">
              <ResultCard label="مزود الوسيط" value={broker?.provider || "none"} />
              <ResultCard label="الوضع" value={broker?.mode || "paper"} />
              <ResultCard label="إرسال الأوامر" value={broker?.order_submission_enabled ? "مفعل" : "معطل"} />
              <ResultCard label="التنفيذ الحي" value={broker?.live_execution_enabled ? "مفعل" : "معطل"} />
            </div>
          </>
        )}
      </SectionCard>

      <FilterBar
        title="تحديث الإشارات الورقية"
        description="حدّث الإشارات للوضع المختار ونفّذ الصفقات الافتراضية تلقائياً داخل المحاكي من دون ربط تنفيذي حي."
        action={<StatusBadge label={refreshing ? "جارٍ التنفيذ" : "المحفظة جاهزة"} tone={refreshing ? "warning" : "subtle"} />}
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid">
            <div className="field field-span-2">
              <SymbolMultiPicker
                label={t("Symbols")}
                symbols={parseSymbolList(watch("symbolsText"))}
                onChange={(symbols) => setValue("symbolsText", symbols.join(","), { shouldValidate: true, shouldDirty: true })}
                helperText="كوّن سلة التحديث بنفس symbol picker الموحد المستخدم عبر المنصة."
              />
            </div>
            <label className="field">
              <span>{t("Mode")}</span>
              <select {...register("mode")}>
                <option value="classic">كلاسيكي</option>
                <option value="vectorbt">VectorBT</option>
                <option value="ml">ML</option>
                <option value="dl">DL</option>
                <option value="ensemble">تجميعي</option>
              </select>
            </label>
            <label className="field">
              <span>الكمية</span>
              <input type="number" min="1" step="1" {...register("quantity")} />
            </label>
            <label className="field">
              <span>{t("Start Date")}</span>
              <input type="date" {...register("startDate")} />
            </label>
            <label className="field">
              <span>{t("End Date")}</span>
              <input type="date" {...register("endDate")} />
            </label>
          </div>
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={refreshing}>
              {refreshing ? "جارٍ التحديث..." : "تحديث الإشارات والمحاكاة"}
            </button>
          </div>
          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      <SectionCard
        title="الأوامر المفتوحة"
        description="أوامر محاكية يدوية يمكن مراجعتها وإلغاؤها من دون تمريرها إلى وسيط حقيقي."
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmitOrder(onOrderSubmit)}>
          <div className="form-grid form-grid-compact">
            <Controller
              name="symbol"
              control={orderControl}
              render={({ field }) => (
                <SymbolPicker
                  compact
                  label={t("Symbol")}
                  value={field.value}
                  onChange={field.onChange}
                  onSelect={(item) => field.onChange(item.symbol)}
                  placeholder="اختر الرمز للأمر الورقي"
                />
              )}
            />
            <label className="field">
              <span>{t("Side")}</span>
              <select {...registerOrder("side")}>
                <option value="BUY">شراء</option>
                <option value="SELL">بيع</option>
              </select>
            </label>
            <label className="field">
              <span>{t("Type")}</span>
              <select {...registerOrder("orderType")}>
                <option value="market">سوقي</option>
                <option value="limit">حدي</option>
              </select>
            </label>
            <label className="field">
              <span>الكمية</span>
              <input type="number" min="1" step="1" {...registerOrder("quantity")} />
            </label>
            <label className="field">
              <span>السعر الحدي</span>
              <input type="number" step="0.01" {...registerOrder("limitPrice")} />
            </label>
          </div>
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={refreshing}>
              {refreshing ? "جارٍ التنفيذ..." : "إنشاء أمر تجريبي"}
            </button>
          </div>
        </form>
        {loading ? <LoadingSkeleton lines={5} /> : <DataTable columns={orderColumns} data={orders?.items || []} emptyTitle="لا توجد أوامر ورقية مفتوحة" emptyDescription="ستظهر أوامر المحاكي اليدوية هنا إلى أن تُلغى أو تُنفذ في مرحلة لاحقة." />}
      </SectionCard>

      <SectionCard
        title="المراكز"
        description="المراكز الافتراضية المفتوحة حالياً مع تقييم سوقي محدث."
      >
        {portfolio ? (
          <SummaryStrip
            items={[
              { label: "المراكز المفتوحة", value: portfolio.summary?.open_positions ?? 0 },
              { label: "القيمة السوقية", value: portfolio.summary?.total_market_value ?? 0 },
              { label: "الربح/الخسارة غير المحققة", value: portfolio.summary?.total_unrealized_pnl ?? 0 },
              { label: "الربح/الخسارة المحققة", value: portfolio.summary?.total_realized_pnl ?? 0 },
            ]}
          />
        ) : null}
        {loading ? <LoadingSkeleton lines={6} /> : <DataTable columns={portfolioColumns} data={portfolio?.items || []} emptyTitle="لا توجد مراكز ورقية" emptyDescription="حدّث الإشارات لإنشاء صفقات ومراكز افتراضية." />}
      </SectionCard>

      <SectionCard
        title="النشاط والتنبيهات"
        description="تنبيهات الشراء والبيع وتغير الثقة وحالة النماذج الناتجة عن تحديث الإشارات."
      >
        {loading ? <LoadingSkeleton lines={5} /> : <DataTable columns={alertColumns} data={alerts?.items || []} emptyTitle="لا توجد تنبيهات بعد" emptyDescription="ستظهر التنبيهات هنا بعد تشغيل تحديث الإشارات الورقية." />}
      </SectionCard>

      <SectionCard
        title="سجل الإشارات"
        description="قرارات الإشارات المحفوظة بحسب وضع الاستراتيجية لمراجعة التداول الورقي."
      >
        {loading ? <LoadingSkeleton lines={5} /> : <DataTable columns={signalColumns} data={signals?.items || []} emptyTitle="لا يوجد سجل إشارات بعد" emptyDescription="سيظهر سجل الإشارات بعد التحديث." />}
      </SectionCard>

      <SectionCard
        title="سجل الصفقات"
        description="تنفيذات افتراضية لعمليات الفتح والإغلاق مع تاريخ الربح والخسارة المحققة."
      >
        {loading ? <LoadingSkeleton lines={5} /> : <DataTable columns={tradeColumns} data={trades?.items || []} emptyTitle="لا توجد صفقات ورقية بعد" emptyDescription="ستظهر هنا تنفيذات الصفقات الافتراضية." />}
      </SectionCard>

      <SectionCard
        title="سجل التنفيذ"
        description="سجل تدقيق مختصر للأوامر والإشارات والتنفيذات داخل المحاكي الورقي."
      >
        {loading ? <LoadingSkeleton lines={5} /> : <DataTable columns={auditColumns} data={audit?.items || []} emptyTitle="لا يوجد سجل تدقيق بعد" emptyDescription="ستظهر هنا أحداث إنشاء الأوامر، الإشارات، والإلغاءات والتنفيذات." />}
      </SectionCard>
    </PageFrame>
  );
}
