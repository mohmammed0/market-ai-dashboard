import { useMemo } from "react";

import PageFrame from "../components/ui/PageFrame";
import ChartCard from "../components/ui/ChartCard";
import ActionButton from "../components/ui/ActionButton";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { useAppData } from "../store/AppDataStore";


function numberOrDash(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
}


export default function KPIDashboardPage() {
  // Use pre-fetched summary data since KPI endpoint is intermittent
  const { data: summary, loading, error } = useAppData("summary");

  // Build a payload-like object from summary data
  const payload = useMemo(() => {
    if (!summary) return null;
    return {
      performance: {
        net_pnl: summary?.portfolio?.summary?.total_pnl ?? 0,
        total_return_pct: summary?.portfolio?.summary?.total_return_pct ?? 0,
        open_positions: summary?.portfolio?.summary?.open_positions ?? 0,
        equity_curve: [],
      },
      risk: {
        max_drawdown_pct: summary?.risk?.portfolio_warnings?.length ?? 0,
        consecutive_losses: 0,
        volatility_pct: 0,
        risk_adjusted_return: 0,
        exposure_concentration_pct: 0,
        gross_exposure_pct: 0,
        daily_loss_limit_tracking_pct: 0,
      },
      base_portfolio_value: summary?.portfolio?.summary?.portfolio_value ?? 100000,
      quality: {
        win_rate_pct: summary?.portfolio?.summary?.win_rate_pct ?? 0,
        signal_count: summary?.scan_ranking?.total_scanned ?? 0,
        top_pick: summary?.scan_ranking?.top_pick ?? "-",
      },
    };
  }, [summary]);

  return (
    <PageFrame
      title="لوحات KPI"
      description="مؤشرات أداء ومخاطر من بيانات المنصة الحية."
      eyebrow="النظرة العامة"
      headerActions={
        <>
          <ActionButton to="/backtest" variant="secondary">الاختبار التاريخي</ActionButton>
          <StatusBadge label="لوحات تنفيذية" tone="accent" />
        </>
      }
    >
      <ErrorBanner message={error} />

      {loading ? (
        <LoadingSkeleton lines={8} />
      ) : payload ? (
        <>
          {/* Performance */}
          <SectionCard title="الأداء" description="أهم أرقام الربحية والعائد.">
            <SummaryStrip
              items={[
                { label: "صافي الربح/الخسارة", value: payload.performance.net_pnl, badge: "P/L" },
                { label: "العائد الكلي %", value: numberOrDash(payload.performance.total_return_pct, 2) },
                { label: "المراكز المفتوحة", value: payload.performance.open_positions },
                { label: "نسبة النجاح %", value: numberOrDash(payload.quality?.win_rate_pct, 1) },
                { label: "Top Pick", value: payload.quality?.top_pick ?? "-", tone: "info" },
                { label: "إجمالي الفحص", value: payload.quality?.signal_count ?? 0 },
              ]}
            />
            <div className="result-grid premium-kpi-grid" style={{ marginTop: 12 }}>
              <MetricCard label="قيمة المحفظة" value={payload.base_portfolio_value} tone="accent" />
              <MetricCard label="الانكشاف الإجمالي %" value={numberOrDash(payload.risk.gross_exposure_pct, 2)} />
              <MetricCard label="التركيز %" value={numberOrDash(payload.risk.exposure_concentration_pct, 2)} />
              <MetricCard label="تنبيهات المخاطر" value={payload.risk.max_drawdown_pct} tone="warning" />
            </div>
          </SectionCard>

          {/* Market Intelligence */}
          <SectionCard title="ذكاء السوق" description="إشارات واتساع السوق الحالي.">
            <div className="result-grid premium-kpi-grid">
              <MetricCard label="اتساع السوق" value={summary?.breadth?.breadth_ratio ?? "-"} />
              <MetricCard label="حالة السوق" value={summary?.breadth?.market_phase || "-"} />
              <MetricCard label="محرك البيانات" value={summary?.market_data_status?.primary_provider || "-"} />
              <MetricCard label="حالة التعلم" value={summary?.continuous_learning?.state?.active_stage || "idle"} />
            </div>
          </SectionCard>
        </>
      ) : (
        <div className="empty-state">
          <span className="empty-state-title">لا توجد بيانات KPI متاحة</span>
          <span className="empty-state-text">تحقق من حالة المنصة في صفحة الإعدادات.</span>
        </div>
      )}
    </PageFrame>
  );
}
