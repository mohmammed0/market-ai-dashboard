import { useMemo, useState } from "react";

import PageFrame from "../components/ui/PageFrame";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import ResultCard from "../components/ui/ResultCard";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchBrokerSummary } from "../api/broker";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { t } from "../lib/i18n";


export default function BrokerPage() {
  const [refreshing, setRefreshing] = useState(false);
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

  const brokerTone = summary?.connected ? "accent" : summary?.enabled ? "warning" : "subtle";
  const brokerLabel = summary?.connected
    ? `${summary.provider?.toUpperCase?.() || "Broker"} · ${summary.mode || "paper"}`
    : summary?.enabled
      ? "Broker Pending"
      : "Broker Disabled";

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await reload(true);
    } catch (error) {
      // Error state is handled by the shared resource hook.
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <PageFrame
      title="Broker Foundation"
      description="Read-only broker status and account state, kept separate from the internal simulator so paper trading stays safe and explicit."
      eyebrow="Broker Integration"
      headerActions={<StatusBadge label={brokerLabel} tone={brokerTone} />}
    >
      <div className="panel result-panel">
        <SectionHeader
          title="Broker Connection"
          description="Alpaca-ready account visibility with live execution still disabled by default."
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
                يبقى التداول التجريبي داخل المحاكي هو مسار التنفيذ الافتراضي. أما التداول التجريبي عبر الوسيط وأي تنفيذ حي مستقبلي
                فهما معزولان خلف إعدادات صريحة.
              </span>
              <span>
                تم ضبط مسار التنفيذ النقدي فقط بحيث يعتمد على <strong>Cash</strong> والأسهم المملوكة فعليًا، وليس على
                <strong> Buying Power</strong> أو أي فتح مراكز شورت.
              </span>
            </div>
            <div className="form-actions">
              <button className="primary-button" type="button" onClick={handleRefresh} disabled={refreshing}>
                {refreshing ? "جارٍ التحديث..." : "تحديث لقطة الوسيط"}
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
            <ResultCard label="Buying Power (informational only)" value={summary.account.buying_power ?? 0} />
            <ResultCard label="Portfolio Value" value={summary.account.portfolio_value ?? 0} />
            <ResultCard label="Pattern Day Trader" value={summary.account.pattern_day_trader ? "Yes" : "No"} />
            <ResultCard label="Trading Blocked" value={summary.account.trading_blocked ? "Yes" : "No"} tone={summary.account.trading_blocked ? "warning" : "default"} />
            <ResultCard label="Account Blocked" value={summary.account.account_blocked ? "Yes" : "No"} tone={summary.account.account_blocked ? "warning" : "default"} />
          </div>
        ) : (
          <div className="empty-state compact-empty">
            <strong>{t("No broker account connected")}</strong>
            <p>احفظ بيانات Alpaca من صفحة الإعدادات ثم اختبر الاتصال هناك. يبقى التداول التجريبي الداخلي متاحاً حتى لو كان اتصال الوسيط غير مهيأ.</p>
          </div>
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
            emptyDescription="Broker paper positions appear here once a provider is configured and has open holdings."
          />
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader title="Recent Broker Orders" description="Read-only order history for broker paper accounts. No live order path is enabled in this pass." />
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : (
          <DataTable
            columns={ordersColumns}
            data={summary?.orders || []}
            emptyTitle="No broker orders"
            emptyDescription="Recent broker paper orders appear here when the provider has order history available."
          />
        )}
      </div>
    </PageFrame>
  );
}
