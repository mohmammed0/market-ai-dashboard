import { useEffect, useMemo, useState } from "react";

import PageFrame from "../components/PageFrame";
import ChartCard from "../components/ui/ChartCard";
import ActionButton from "../components/ui/ActionButton";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchDashboardKpis } from "../api/platform";


function numberOrDash(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(digits);
}


export default function KPIDashboardPage() {
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetchDashboardKpis()
      .then((data) => {
        if (active) {
          setPayload(data);
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message || "تعذر تحميل لوحات KPI.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const equityChart = useMemo(() => {
    const series = payload?.performance?.equity_curve || [];
    if (!series.length) {
      return null;
    }
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 20, top: 30, bottom: 30 },
      xAxis: {
        type: "category",
        data: series.map((item) => item.date),
        axisLabel: { color: "#9bb0c9", hideOverlap: true },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#9bb0c9" },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)" } },
      },
      series: [
        {
          type: "line",
          smooth: true,
          showSymbol: false,
          lineStyle: { color: "#38bdf8", width: 3 },
          areaStyle: { color: "rgba(56, 189, 248, 0.12)" },
          data: series.map((item) => item.equity),
        },
      ],
    };
  }, [payload]);

  const benchmarkChart = useMemo(() => {
    const spy = payload?.benchmark?.series?.spy || [];
    const qqq = payload?.benchmark?.series?.qqq || [];
    const strategy = payload?.benchmark?.series?.strategy || [];
    if (!spy.length && !qqq.length && !strategy.length) {
      return null;
    }
    const labels = spy.map((item) => item.date);
    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      legend: { textStyle: { color: "#9bb0c9" } },
      grid: { left: 40, right: 20, top: 30, bottom: 30 },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { color: "#9bb0c9", hideOverlap: true },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#9bb0c9", formatter: "{value}%" },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)" } },
      },
      series: [
        {
          name: "SPY",
          type: "line",
          smooth: true,
          showSymbol: false,
          data: spy.map((item) => item.return_pct),
          lineStyle: { color: "#22c55e", width: 2.5 },
        },
        {
          name: "QQQ",
          type: "line",
          smooth: true,
          showSymbol: false,
          data: qqq.map((item) => item.return_pct),
          lineStyle: { color: "#f59e0b", width: 2.5 },
        },
        {
          name: "الاستراتيجية",
          type: "line",
          smooth: true,
          showSymbol: false,
          data: strategy.map((item) => (((Number(item.equity || 0) / Number(payload?.base_portfolio_value || 1)) - 1) * 100)),
          lineStyle: { color: "#60a5fa", width: 3 },
        },
      ],
    };
  }, [payload]);

  const leaderboardColumns = useMemo(
    () => [
      { accessorKey: "strategy", header: "الاستراتيجية" },
      { accessorKey: "robust_score", header: "النتيجة المتينة" },
      { accessorKey: "total_return_pct", header: "العائد %" },
      { accessorKey: "win_rate_pct", header: "نسبة النجاح %" },
      { accessorKey: "avg_trade_return_pct", header: "متوسط الصفقة %" },
      { accessorKey: "max_drawdown_pct", header: "أقصى تراجع %" },
      { accessorKey: "confidence", header: "الثقة" },
    ],
    []
  );

  return (
    <PageFrame
      title="لوحات KPI"
      description="لوحات أداء ومخاطر وجودة استراتيجية وذكاء سوق ومقارنة مرجعية بطابع منصة تداول عربية احترافية."
      eyebrow="النظرة العامة"
      headerActions={
        <>
          <ActionButton to="/backtest" variant="secondary">الاختبار التاريخي</ActionButton>
          <StatusBadge label="لوحات تنفيذية" tone="accent" />
        </>
      }
    >
      <SectionCard
        title="الأداء"
        description="أهم أرقام الربحية والعائد والاستقرار على مستوى المنصة."
      >
        <ErrorBanner message={error} />
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : payload ? (
          <>
            <SummaryStrip
              items={[
                { label: "صافي الربح/الخسارة", value: payload.performance?.net_pnl ?? 0, badge: "P/L" },
                { label: "العائد الكلي %", value: numberOrDash(payload.performance?.total_return_pct, 2) },
                { label: "CAGR %", value: numberOrDash(payload.performance?.cagr_pct, 2) },
                { label: "استقرار العائد الشهري", value: numberOrDash(payload.performance?.monthly_return_stability, 2) },
                { label: "أفضل يوم", value: payload.performance?.best_day?.pnl ?? 0 },
                { label: "أسوأ يوم", value: payload.performance?.worst_day?.pnl ?? 0, tone: "warning" },
              ]}
            />
            <div className="result-grid premium-kpi-grid">
              <MetricCard label="متوسط الربح" value={payload.performance?.average_win ?? 0} tone="accent" />
              <MetricCard label="متوسط الخسارة" value={payload.performance?.average_loss ?? 0} tone="warning" />
              <MetricCard label="تقلب العائد الشهري %" value={numberOrDash(payload.performance?.monthly_return_volatility_pct, 2)} />
              <MetricCard label="قيمة المحفظة المرجعية" value={payload.base_portfolio_value ?? 0} />
            </div>
          </>
        ) : null}
      </SectionCard>

      {equityChart ? (
        <ChartCard
          className="span-12"
          title="منحنى رأس المال"
          description="ملخص بصري لتطور رأس المال انطلاقاً من تداولات الورقي الحالية."
          option={equityChart}
          height={320}
        />
      ) : null}

      <SectionCard
        title="المخاطر"
        description="تتبع التراجع والتذبذب وحدود الخسارة وتركيز الانكشاف الحالي."
      >
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : payload ? (
          <div className="result-grid premium-kpi-grid">
            <MetricCard label="أقصى تراجع %" value={numberOrDash(payload.risk?.max_drawdown_pct, 2)} tone="warning" />
            <MetricCard label="تتبع حد الخسارة اليومية %" value={numberOrDash(payload.risk?.daily_loss_limit_tracking_pct, 2)} tone="warning" />
            <MetricCard label="التذبذب %" value={numberOrDash(payload.risk?.volatility_pct, 2)} />
            <MetricCard label="الخسائر المتتالية" value={payload.risk?.consecutive_losses ?? 0} tone="warning" />
            <MetricCard label="عائد معدل بالمخاطر" value={numberOrDash(payload.risk?.risk_adjusted_return, 3)} />
            <MetricCard label="تركيز الانكشاف %" value={numberOrDash(payload.risk?.exposure_concentration_pct, 2)} />
            <MetricCard label="الانكشاف الإجمالي %" value={numberOrDash(payload.risk?.gross_exposure_pct, 2)} />
            <MetricCard label="حالة المخاطر الحالية" value={payload.risk?.current_portfolio_risk_state || "-"} tone={payload.risk?.warnings?.length ? "warning" : "default"} />
          </div>
        ) : null}
      </SectionCard>

      <SectionCard
        title="جودة الاستراتيجية"
        description="ملخص الفوز والربحية والتوقع ومتوسط الاحتفاظ وترتيب المقارنات الأخيرة."
      >
        {loading ? (
          <LoadingSkeleton lines={7} />
        ) : payload ? (
          <>
            <SummaryStrip
              items={[
                { label: "نسبة النجاح %", value: numberOrDash(payload.strategy_quality?.win_rate_pct, 2) },
                { label: "Profit Factor", value: numberOrDash(payload.strategy_quality?.profit_factor, 3) },
                { label: "Expectancy", value: numberOrDash(payload.strategy_quality?.expectancy, 3) },
                { label: "متوسط الاحتفاظ (س)", value: numberOrDash(payload.strategy_quality?.average_holding_time_hours, 2) },
              ]}
            />
            <DataTable
              columns={leaderboardColumns}
              data={payload.strategy_quality?.leaderboard || []}
              emptyTitle="لا توجد مقارنة استراتيجيات بعد"
              emptyDescription="سيظهر ترتيب المقارنة هنا بعد تشغيل تقييم الاستراتيجية."
            />
          </>
        ) : null}
      </SectionCard>

      <SectionCard
        title="ذكاء السوق"
        description="اتساع السوق، قوة القطاعات، حالة الذكاء الاصطناعي، وقائمة الفرص الحالية."
      >
        {loading ? (
          <LoadingSkeleton lines={7} />
        ) : payload ? (
          <>
            <SummaryStrip
              items={[
                { label: "الأسهم الصاعدة", value: payload.market_intelligence?.breadth?.advancing ?? 0 },
                { label: "الأسهم الهابطة", value: payload.market_intelligence?.breadth?.declining ?? 0 },
                { label: "نسبة الاتساع", value: payload.market_intelligence?.breadth?.breadth_ratio ?? 0 },
                { label: "OpenAI", value: payload.market_intelligence?.news_sentiment_summary?.openai_enabled ? "جاهز" : "غير جاهز" },
              ]}
            />
            <div className="result-grid premium-kpi-grid">
              {(payload.market_intelligence?.watchlist_opportunities || []).slice(0, 6).map((item) => (
                <MetricCard
                  key={`watch-${item.symbol}`}
                  label={item.symbol}
                  value={item.change_pct ?? 0}
                  detail={item.security_name || item.exchange || "فرصة متابعة"}
                  tone={Number(item.change_pct || 0) >= 0 ? "accent" : "warning"}
                />
              ))}
            </div>
          </>
        ) : null}
      </SectionCard>

      {benchmarkChart ? (
        <ChartCard
          className="span-12"
          title="المقارنة المرجعية"
          description="مقارنة الاستراتيجية الحالية مقابل SPY وQQQ بنظرة rolling مبسطة."
          option={benchmarkChart}
          height={320}
        />
      ) : null}

      <SectionCard
        title="المرجع والانكشاف"
        description="ملخص outperformance أو underperformance والتموضع الحالي مقابل SPY وQQQ."
      >
        {loading ? (
          <LoadingSkeleton lines={5} />
        ) : payload ? (
          <div className="result-grid premium-kpi-grid">
            <MetricCard label="مقابل SPY %" value={numberOrDash(payload.benchmark?.vs_spy_pct, 2)} tone={Number(payload.benchmark?.vs_spy_pct || 0) >= 0 ? "accent" : "warning"} />
            <MetricCard label="مقابل QQQ %" value={numberOrDash(payload.benchmark?.vs_qqq_pct, 2)} tone={Number(payload.benchmark?.vs_qqq_pct || 0) >= 0 ? "accent" : "warning"} />
            <MetricCard label="عائد SPY %" value={numberOrDash(payload.benchmark?.spy_total_return_pct, 2)} />
            <MetricCard label="عائد QQQ %" value={numberOrDash(payload.benchmark?.qqq_total_return_pct, 2)} />
            <MetricCard label="الانكشاف الإجمالي %" value={numberOrDash(payload.benchmark?.current_positioning_vs_benchmark?.gross_exposure_pct, 2)} />
            <MetricCard label="أكبر مركز %" value={numberOrDash(payload.benchmark?.current_positioning_vs_benchmark?.largest_position_pct, 2)} />
          </div>
        ) : null}
      </SectionCard>
    </PageFrame>
  );
}
