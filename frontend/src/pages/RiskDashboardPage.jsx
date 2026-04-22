import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/ui/PageFrame";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import SectionCard from "../components/ui/SectionCard";
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

  function exposureTone(value) {
    const num = parseFloat(value);
    if (isNaN(num)) return "neutral";
    if (num > 80) return "negative";
    if (num > 50) return "warning";
    return "positive";
  }

  return (
    <PageFrame
      title="لوحة المخاطر"
      description="تحجيم المراكز، ضوابط الخسارة اليومية، وتنبيهات المحفظة المبنية على محفظة الوسيط الحالية."
      eyebrow="ذكاء المخاطر"
      headerActions={<StatusBadge label="محمي" tone="positive" dot />}
    >
      {/* Risk Planner Form */}
      <FilterBar
        title="مخطط المخاطر"
        description="احسب حجم المركز، وقف الخسارة، والمكافأة/المخاطرة باستخدام منطق الخادم بدلا من حساب الواجهة فقط."
        action={<StatusBadge label={submitting ? "جارٍ الحساب" : "المخطط جاهز"} tone={submitting ? "warning" : "neutral"} />}
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
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? "جارٍ الحساب..." : "إنشاء خطة المخاطر"}
            </button>
          </div>
          <ErrorBanner message={error} />
        </form>
      </FilterBar>

      {/* Risk Limits & Portfolio Warnings */}
      <SectionCard
        title="حدود المخاطر"
        description="الحواجز المهيأة والتنبيهات على مستوى المحفظة الحالية."
        action={
          dashboard ? (
            <StatusBadge
              label={`${(dashboard.portfolio_warnings || []).length} تنبيه`}
              tone={(dashboard.portfolio_warnings || []).length > 0 ? "warning" : "positive"}
              dot
            />
          ) : null
        }
      >
        {loading ? (
          <LoadingSkeleton lines={5} />
        ) : dashboard ? (
          <>
            <div className="result-grid">
              <MetricCard
                label="قيمة المحفظة"
                value={dashboard.portfolio_value}
                tone="info"
                badge="$"
              />
              <MetricCard
                label="أقصى مخاطرة / صفقة"
                value={`${dashboard.max_risk_per_trade_pct}%`}
                tone="warning"
              />
              <MetricCard
                label="أقصى خسارة يومية"
                value={`${dashboard.max_daily_loss_pct}%`}
                tone="negative"
              />
              <MetricCard
                label="التعرض الإجمالي"
                value={`${dashboard.gross_exposure_pct}%`}
                tone={exposureTone(dashboard.gross_exposure_pct)}
                badge="Portfolio"
              />
            </div>
            {(dashboard.portfolio_warnings || []).length > 0 ? (
              <div style={{ marginTop: "var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                {dashboard.portfolio_warnings.map((warning, idx) => (
                  <div className="status-message warning" key={`warn-${idx}`}>{warning}</div>
                ))}
              </div>
            ) : (
              <div style={{ marginTop: "var(--space-4)" }}>
                <EmptyState
                  className="compact-empty"
                  title={t("No major risk warnings")}
                  description={t("The current paper portfolio is within the configured guardrails.")}
                />
              </div>
            )}
          </>
        ) : (
          <EmptyState
            title="لا توجد بيانات مخاطر"
            description="تعذر تحميل لوحة المخاطر من الخادم."
          />
        )}
      </SectionCard>

      {/* Latest Risk Plan Results */}
      <SectionCard
        title="آخر خطة مخاطر"
        description="القيم المحسوبة من الخادم لتحجيم المركز والمكافأة/المخاطرة للإعداد المطلوب."
        action={plan ? <StatusBadge label="محسوبة" tone="positive" /> : null}
      >
        {plan ? (
          <div className="result-grid">
            <MetricCard
              label="الكمية المقترحة"
              value={plan.suggested_quantity}
              tone="info"
            />
            <MetricCard
              label="ميزانية المخاطرة $"
              value={plan.risk_budget_dollars}
              tone="warning"
            />
            <MetricCard
              label="مخاطرة السهم الواحد"
              value={plan.per_share_risk}
            />
            <MetricCard
              label="المكافأة / المخاطرة"
              value={plan.reward_risk_ratio ?? "-"}
              tone={plan.reward_risk_ratio && plan.reward_risk_ratio >= 2 ? "positive" : "neutral"}
            />
            <MetricCard
              label="قيمة المركز"
              value={plan.position_value}
              badge="$"
            />
            <MetricCard
              label="أقصى خسارة يومية $"
              value={plan.max_daily_loss_dollars}
              tone="negative"
            />
          </div>
        ) : (
          <EmptyState
            className="compact-empty"
            title={t("No risk plan yet")}
            description={t("Run the planner to calculate size, stop, target, and risk budget.")}
          />
        )}
      </SectionCard>
    </PageFrame>
  );
}
