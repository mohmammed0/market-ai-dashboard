import { useEffect, useMemo, useState } from "react";

import PageFrame from "../components/ui/PageFrame";
import DataTable from "../components/ui/DataTable";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import ResultCard from "../components/ui/ResultCard";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchBrokerSummary, liquidateBrokerPortfolio } from "../api/broker";
import { fetchExecutionReconcile, runExecutionReconcile } from "../api/execution";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { t } from "../lib/i18n";


export default function BrokerPage() {
  const [refreshing, setRefreshing] = useState(false);
  const [liquidating, setLiquidating] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [actionMessage, setActionMessage] = useState("");
  const [reconcilePayload, setReconcilePayload] = useState(null);
  const {
    data: summary,
    loading,
    error,
    reload,
  } = useAsyncResource(fetchBrokerSummary);

  const positionsColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "side", header: "Side" },
      { accessorKey: "qty", header: "Qty" },
      { accessorKey: "avg_entry_price", header: "Avg Entry" },
      { accessorKey: "current_price", header: "Last" },
      { accessorKey: "market_value", header: "Market Value" },
      { accessorKey: "unrealized_pnl", header: "Unrealized PnL" },
      { accessorKey: "change_today_pct", header: "Day %" },
    ],
    []
  );

  const ordersColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "side", header: "Side" },
      { accessorKey: "type", header: "Type" },
      { accessorKey: "status", header: "Status" },
      { accessorKey: "qty", header: "Qty" },
      { accessorKey: "filled_qty", header: "Filled" },
      { accessorKey: "filled_avg_price", header: "Avg Fill" },
      { accessorKey: "submitted_at", header: "Submitted" },
    ],
    []
  );

  const reconcileColumns = useMemo(
    () => [
      { accessorKey: "symbol", header: "Symbol" },
      { accessorKey: "status", header: "Status" },
      { accessorKey: "broker_side", header: "Broker Side" },
      { accessorKey: "internal_side", header: "Internal Side" },
      { accessorKey: "broker_quantity", header: "Broker Qty" },
      { accessorKey: "internal_quantity", header: "Internal Qty" },
      { accessorKey: "quantity_delta", header: "Delta" },
    ],
    []
  );

  const brokerTone = summary?.connected ? "accent" : summary?.enabled ? "warning" : "subtle";
  const brokerLabel = summary?.connected
    ? `${summary.provider?.toUpperCase?.() || "Broker"} · ${summary.mode || "paper"}`
    : summary?.enabled
      ? "Broker Pending"
      : "Broker Disabled";
  const liquidationDisabled = !summary?.connected || !summary?.order_submission_enabled || (summary?.positions?.length ?? 0) === 0 || liquidating;

  async function handleReconcile(applySync = false) {
    setReconciling(true);
    try {
      const response = applySync
        ? await runExecutionReconcile({ broker: "alpaca", strategy_mode: "classic", apply_sync: true })
        : await fetchExecutionReconcile({ broker: "alpaca", strategy_mode: "classic" });
      setReconcilePayload(response);
      if (applySync) {
        setActionMessage(`تمت مزامنة ${response?.sync_result?.positions ?? 0} مركز داخلي مع الوسيط.`);
        await reload(true);
      }
    } catch (actionError) {
      setActionMessage(actionError.message || "فشل فحص المطابقة بين الوسيط والمحفظة الداخلية.");
    } finally {
      setReconciling(false);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await reload(true);
      if (summary?.connected) {
        await handleReconcile(false);
      }
    } catch (error) {
      // Error state is handled by the shared resource hook.
    } finally {
      setRefreshing(false);
    }
  }

  async function handleLiquidate() {
    const confirmed = window.confirm("سيتم إغلاق جميع المراكز المفتوحة وتحويل المحفظة إلى وضع مسطّح. هل تريد المتابعة؟");
    if (!confirmed) return;
    setLiquidating(true);
    setActionMessage("");
    try {
      const response = await liquidateBrokerPortfolio({ cancel_open_orders: true });
      const closed = Array.isArray(response?.results) ? response.results.length : 0;
      setActionMessage(response?.error || `تم إرسال أوامر تصفية لـ ${closed} مركز.`);
      await reload(true);
    } catch (actionError) {
      setActionMessage(actionError.message || "فشل تسييل المحفظة.");
    } finally {
      setLiquidating(false);
    }
  }

  useEffect(() => {
    if (!summary?.connected || loading || reconcilePayload || reconciling) {
      return;
    }
    handleReconcile(false).catch(() => {});
  }, [summary?.connected, loading]);

  return (
    <PageFrame
      title="Broker Foundation"
      description="Broker-managed account and execution state from the connected broker environment."
      eyebrow="Broker Integration"
      headerActions={<StatusBadge label={brokerLabel} tone={brokerTone} />}
    >
      <div className="panel result-panel">
        <SectionHeader
          title="Broker Connection"
          description="Broker connectivity, account state, and execution readiness from the connected environment."
          badge={summary?.connected ? <StatusBadge label="Connected" tone="accent" /> : <StatusBadge label="Read Only" tone="warning" />}
        />
        <ErrorBanner message={error} />
        {loading ? (
          <LoadingSkeleton lines={5} />
        ) : summary ? (
          <>
            <SummaryStrip
              items={[
                { label: "Provider", value: summary.provider || "none" },
                { label: "Mode", value: summary.mode || "disabled" },
                { label: "Trading Mode", value: summary.trading_mode === "margin" ? "margin" : "cash" },
                { label: "Connected", value: summary.connected ? "yes" : "no" },
                { label: "Order Submission", value: summary.order_submission_enabled ? "enabled" : "disabled", tone: summary.order_submission_enabled ? "warning" : "default" },
                { label: "Live Execution", value: summary.live_execution_enabled ? "enabled" : "disabled", tone: summary.live_execution_enabled ? "warning" : "default" },
                { label: "Open Positions", value: summary.totals?.positions ?? 0 },
                { label: "Open Orders", value: summary.totals?.open_orders ?? 0 },
              ]}
            />
            <div className="status-message">
              <strong>{summary.detail || "Broker integration status unavailable."}</strong>
              <span>
                المسار التشغيلي الحالي broker-managed بالكامل. لا يوجد محرك تداول ورقي داخلي نشط، وأي تنفيذ يتم عبر إعدادات الوسيط المتصل.
              </span>
              <span>
                {summary.trading_mode === "margin"
                  ? <>نمط التداول الحالي <strong>Margin</strong>، لذلك يسمح بالاقتراض وفتح الشورت ويعتمد على <strong>Buying Power</strong> لدى الوسيط.</>
                  : <>تم ضبط مسار التنفيذ على <strong>Cash Only</strong> بحيث يعتمد على <strong>Cash</strong> والأسهم المملوكة فعليًا، وليس على <strong>Buying Power</strong> أو أي فتح مراكز شورت.</>}
              </span>
              {actionMessage ? <span>{actionMessage}</span> : null}
            </div>
            <div className="form-actions">
              <button className="primary-button" type="button" onClick={handleRefresh} disabled={refreshing}>
                {refreshing ? "جارٍ التحديث..." : "تحديث لقطة الوسيط"}
              </button>
              <button className="secondary-button" type="button" onClick={() => handleReconcile(false)} disabled={!summary?.connected || reconciling}>
                {reconciling ? "جارٍ الفحص..." : "فحص المطابقة"}
              </button>
              <button className="secondary-button" type="button" onClick={() => handleReconcile(true)} disabled={!summary?.connected || reconciling}>
                {reconciling ? "جارٍ المزامنة..." : "مزامنة الداخلي"}
              </button>
              <button className="btn btn-danger btn-sm" type="button" onClick={handleLiquidate} disabled={liquidationDisabled}>
                {liquidating ? "جارٍ التسييل..." : "تسييل المحفظة"}
              </button>
            </div>
          </>
        ) : null}
      </div>

      <div className="panel result-panel">
        <SectionHeader title="Account Summary" description="Account cash, equity, and guardrail status from the configured broker provider." />
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : summary?.account ? (
          <div className="result-grid">
            <ResultCard label="Account Status" value={summary.account.status || "-"} />
            <ResultCard label="Cash" value={summary.account.cash ?? 0} />
            <ResultCard label="Equity" value={summary.account.equity ?? 0} />
            <ResultCard
              label={summary?.trading_mode === "margin" ? "Buying Power" : "Buying Power (informational only)"}
              value={summary.account.buying_power ?? 0}
            />
            <ResultCard label="Portfolio Value" value={summary.account.portfolio_value ?? 0} />
            <ResultCard label="Pattern Day Trader" value={summary.account.pattern_day_trader ? "Yes" : "No"} />
            <ResultCard label="Trading Blocked" value={summary.account.trading_blocked ? "Yes" : "No"} tone={summary.account.trading_blocked ? "warning" : "default"} />
            <ResultCard label="Account Blocked" value={summary.account.account_blocked ? "Yes" : "No"} tone={summary.account.account_blocked ? "warning" : "default"} />
          </div>
        ) : (
          <div className="empty-state compact-empty">
            <strong>{t("No broker account connected")}</strong>
            <p>احفظ بيانات Alpaca من صفحة الإعدادات ثم اختبر الاتصال هناك. هذا السطح يعرض حالة التنفيذ عبر الوسيط فقط.</p>
          </div>
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader
          title="Execution Reconciliation"
          description="مقارنة مباشرة بين مراكز الوسيط والمراكز الداخلية مع خيار مزامنة داخلي محافظ."
        />
        {reconciling && !reconcilePayload ? (
          <LoadingSkeleton lines={5} />
        ) : reconcilePayload ? (
          <>
            <SummaryStrip
              items={[
                { label: "Broker", value: reconcilePayload.summary?.broker_positions ?? 0 },
                { label: "Internal", value: reconcilePayload.summary?.internal_positions ?? 0 },
                { label: "Matched", value: reconcilePayload.summary?.matched ?? 0, tone: "positive" },
                { label: "Mismatched", value: reconcilePayload.summary?.mismatched ?? 0, tone: (reconcilePayload.summary?.mismatched ?? 0) > 0 ? "warning" : "positive" },
                { label: "Broker Only", value: reconcilePayload.summary?.broker_only ?? 0, tone: (reconcilePayload.summary?.broker_only ?? 0) > 0 ? "warning" : "neutral" },
                { label: "Internal Only", value: reconcilePayload.summary?.internal_only ?? 0, tone: (reconcilePayload.summary?.internal_only ?? 0) > 0 ? "warning" : "neutral" },
              ]}
            />
            <DataTable
              columns={reconcileColumns}
              data={reconcilePayload.positions || []}
              emptyTitle="No reconciliation rows"
              emptyDescription="No broker/internal positions were available for comparison."
            />
          </>
        ) : (
          <EmptyState
            title="لم يتم تشغيل المطابقة بعد"
            description="شغّل فحص المطابقة لإظهار الفروق بين حالة الوسيط والحالة الداخلية."
          />
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader title="Broker Positions" description="Read-only broker portfolio state for future exposure, alerts, and automation hooks." />
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : (
          <DataTable
            columns={positionsColumns}
            data={summary?.positions || []}
            emptyTitle="No broker positions"
            emptyDescription="Broker positions appear here once a provider is configured and has open holdings."
          />
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader title="Recent Broker Orders" description="Broker-managed order history from the connected account." />
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : (
          <DataTable
            columns={ordersColumns}
            data={summary?.orders || []}
            emptyTitle="No broker orders"
            emptyDescription="Recent broker orders appear here when the provider has order history available."
          />
        )}
      </div>
    </PageFrame>
  );
}
