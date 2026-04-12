import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/PageFrame";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import ResultCard from "../components/ui/ResultCard";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { createRiskPlan, fetchRiskDashboard } from "../lib/api";
import { riskPlanSchema } from "../lib/forms";
import { t } from "../lib/i18n";


export default function RiskDashboardPage() {
  const [dashboard, setDashboard] = useState(null);
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(riskPlanSchema),
    defaultValues: {
      entryPrice: 100,
      stopLossPrice: "",
      takeProfitPrice: "",
      portfolioValue: 100000,
      riskPerTradePct: 1,
      maxDailyLossPct: 2.5,
    },
  });

  useEffect(() => {
    fetchRiskDashboard()
      .then((data) => setDashboard(data))
      .catch((requestError) => setError(requestError.message || "Risk dashboard failed to load."))
      .finally(() => setLoading(false));
  }, []);

  async function onSubmit(values) {
    setSubmitting(true);
    setError("");
    try {
      const data = await createRiskPlan({
        entry_price: values.entryPrice,
        stop_loss_price: values.stopLossPrice === "" ? null : values.stopLossPrice,
        take_profit_price: values.takeProfitPrice === "" ? null : values.takeProfitPrice,
        portfolio_value: values.portfolioValue,
        risk_per_trade_pct: values.riskPerTradePct,
        max_daily_loss_pct: values.maxDailyLossPct,
      });
      setPlan(data);
    } catch (requestError) {
      setError(requestError.message || "Risk plan request failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageFrame
      title="Risk Dashboard"
      description="Position sizing, daily loss controls, and portfolio-level warnings built on top of the current paper portfolio."
      eyebrow="Risk Intelligence"
      headerActions={<StatusBadge label="Protected" tone="accent" />}
    >
      <FilterBar
        title="Risk Planner"
        description="Calculate position size, stop loss, and reward/risk using reusable backend logic instead of UI-only math."
        action={<StatusBadge label={submitting ? "Calculating" : "Planner Ready"} tone={submitting ? "warning" : "subtle"} />}
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid">
            <label className="field">
              <span>سعر الدخول</span>
              <input type="number" step="0.01" {...register("entryPrice")} />
              {errors.entryPrice ? <small className="field-error">{errors.entryPrice.message}</small> : null}
            </label>
            <label className="field">
              <span>وقف الخسارة</span>
              <input type="number" step="0.01" {...register("stopLossPrice")} />
            </label>
            <label className="field">
              <span>جني الأرباح</span>
              <input type="number" step="0.01" {...register("takeProfitPrice")} />
            </label>
            <label className="field">
              <span>قيمة المحفظة</span>
              <input type="number" step="100" {...register("portfolioValue")} />
            </label>
            <label className="field">
              <span>المخاطرة لكل صفقة %</span>
              <input type="number" step="0.1" {...register("riskPerTradePct")} />
            </label>
            <label className="field">
              <span>أقصى خسارة يومية %</span>
              <input type="number" step="0.1" {...register("maxDailyLossPct")} />
            </label>
          </div>
          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? "جارٍ الحساب..." : "إنشاء خطة المخاطر"}
            </button>
          </div>
          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      <div className="panel result-panel">
        <SectionHeader title="Risk Limits" description="Configured guardrails and current portfolio exposure warnings." />
        {loading ? (
          <LoadingSkeleton lines={5} />
        ) : dashboard ? (
          <>
            <SummaryStrip
              items={[
                { label: "Portfolio Value", value: dashboard.portfolio_value },
                { label: "Max Risk / Trade", value: `${dashboard.max_risk_per_trade_pct}%` },
                { label: "Max Daily Loss", value: `${dashboard.max_daily_loss_pct}%` },
                { label: "Gross Exposure", value: `${dashboard.gross_exposure_pct}%`, badge: "Portfolio" },
              ]}
            />
            <div className="risk-warning-list">
              {(dashboard.portfolio_warnings || []).length ? (
                dashboard.portfolio_warnings.map((warning) => (
                  <div className="status-message warning" key={warning}>{warning}</div>
                ))
              ) : (
                <div className="empty-state compact-empty">
                  <strong>{t("No major risk warnings")}</strong>
                  <p>{t("The current paper portfolio is within the configured guardrails.")}</p>
                </div>
              )}
            </div>
          </>
        ) : null}
      </div>

      <div className="panel result-panel">
        <SectionHeader title="Latest Risk Plan" description="Backend-calculated sizing and reward/risk values for the requested setup." />
        {plan ? (
          <div className="result-grid">
            <ResultCard label="Suggested Quantity" value={plan.suggested_quantity} />
            <ResultCard label="Risk Budget $" value={plan.risk_budget_dollars} />
            <ResultCard label="Per Share Risk" value={plan.per_share_risk} />
            <ResultCard label="Reward / Risk" value={plan.reward_risk_ratio ?? "-"} />
            <ResultCard label="Position Value" value={plan.position_value} />
            <ResultCard label="Max Daily Loss $" value={plan.max_daily_loss_dollars} />
          </div>
        ) : (
          <div className="empty-state compact-empty">
            <strong>{t("No risk plan yet")}</strong>
            <p>{t("Run the planner to calculate size, stop, target, and risk budget.")}</p>
          </div>
        )}
      </div>
    </PageFrame>
  );
}
