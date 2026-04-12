import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/PageFrame";
import ChartCard from "../components/ui/ChartCard";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import ResultCard from "../components/ui/ResultCard";
import SectionCard from "../components/ui/SectionCard";
import SymbolPicker from "../components/ui/SymbolPicker";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { runBacktest, runModelBacktest, runVectorbtBacktest } from "../lib/api";
import { backtestSchema } from "../lib/forms";
import { t } from "../lib/i18n";


export default function BacktestPage() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState("classic");

  const {
    control,
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(backtestSchema),
    defaultValues: {
      instrument: "AAPL",
      startDate: "2024-01-01",
      endDate: "2026-04-02",
      holdDays: 10,
      minTechnicalScore: 2,
      buyScoreThreshold: 3,
      sellScoreThreshold: 4,
    },
  });

  const chartOption = useMemo(() => {
    if (!result) {
      return null;
    }

    if (result.engine === "vectorbt" && Array.isArray(result.equity_curve) && result.equity_curve.length > 0) {
      return {
        backgroundColor: "transparent",
        tooltip: { trigger: "axis" },
        xAxis: {
          type: "category",
          data: result.equity_curve.map((point) => point.date),
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
            data: result.equity_curve.map((point) => point.equity),
            lineStyle: { color: "#34d399", width: 3 },
            itemStyle: { color: "#34d399" },
            areaStyle: { color: "rgba(52, 211, 153, 0.16)" },
            showSymbol: false,
          },
        ],
      };
    }

    if (mode !== "classic") {
      return {
        backgroundColor: "transparent",
        tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: ["صفقات كلاسيكية", "نجاح كلاسيكي", "عائد VectorBT", "ثقة ذكية"],
        axisLabel: { color: "#9bb0c9" },
      },
        yAxis: {
          type: "value",
          axisLabel: { color: "#9bb0c9" },
          splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)" } },
        },
        series: [
          {
            type: "bar",
            data: [
              result.classic_summary?.trades ?? 0,
              result.classic_summary?.overall_win_rate_pct ?? 0,
              result.vectorbt_summary?.total_return_pct ?? 0,
              result.smart_output?.confidence ?? 0,
            ],
            itemStyle: {
              color: "#818cf8",
              borderRadius: [8, 8, 0, 0],
            },
          },
        ],
      };
    }

    return {
      backgroundColor: "transparent",
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: ["نسبة النجاح", "متوسط العائد", "أفضل صفقة", "أسوأ صفقة"],
        axisLabel: { color: "#9bb0c9" },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#9bb0c9" },
        splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)" } },
      },
      series: [
        {
          type: "bar",
          data: [
            result.overall_win_rate_pct ?? 0,
            result.avg_trade_return_pct ?? 0,
            result.best_trade_pct ?? 0,
            result.worst_trade_pct ?? 0,
          ],
          itemStyle: {
            color: "#60a5fa",
            borderRadius: [8, 8, 0, 0],
          },
        },
      ],
    };
  }, [result]);

  async function onSubmit(values) {
    setLoading(true);
    setError("");

    try {
      const payload = {
        instrument: values.instrument.trim().toUpperCase(),
        start_date: values.startDate,
        end_date: values.endDate,
        hold_days: values.holdDays,
        min_technical_score: values.minTechnicalScore,
        buy_score_threshold: values.buyScoreThreshold,
        sell_score_threshold: values.sellScoreThreshold,
      };
      const data = mode === "vectorbt"
        ? await runVectorbtBacktest(payload)
        : mode === "classic"
          ? await runBacktest(payload)
          : await runModelBacktest({ ...payload, mode });
      if (data?.error) {
        throw new Error(data.error);
      }
      setResult(data);
    } catch (requestError) {
      setResult(null);
      setError(requestError.message || "Backtest request failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageFrame
      title="الاختبار التاريخي"
      description="شغّل الاختبار التاريخي الكلاسيكي أو المسارات الموازية الذكية مع الحفاظ على السلوك الحالي للمحرك الأساسي."
      eyebrow="بحث الاستراتيجية"
      headerActions={<StatusBadge label={mode.toUpperCase()} tone="accent" />}
    >
      <FilterBar
        title="طلب الاختبار التاريخي"
        description="الوضع الكلاسيكي يبقي المحرك الحالي، بينما تشغّل أوضاع VectorBT والطبقات الذكية مسارات مقارنة موازية."
        action={<StatusBadge label={loading ? "جارٍ التشغيل" : "الاستراتيجية جاهزة"} tone={loading ? "warning" : "subtle"} />}
      >
      <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>

        <label className="field">
          <span>وضع الاختبار</span>
          <select value={mode} onChange={(event) => setMode(event.target.value)}>
            <option value="classic">كلاسيكي</option>
            <option value="vectorbt">VectorBT</option>
            <option value="ml">ML</option>
            <option value="dl">DL</option>
            <option value="ensemble">Ensemble</option>
          </select>
        </label>

        <Controller
          name="instrument"
          control={control}
          render={({ field }) => (
            <SymbolPicker
              label="الأداة"
              value={field.value}
              onChange={field.onChange}
              onSelect={(item) => field.onChange(item.symbol)}
              placeholder="ابحث عن السهم أو ETF ثم اختره"
              helperText="نفس تجربة اختيار الرمز المستخدمة في التحليل والاستراتيجية والتداول الورقي."
              error={errors.instrument?.message}
            />
          )}
        />

        <label className="field">
          <span>{t("Start Date")}</span>
          <input type="date" {...register("startDate")} />
        </label>

        <label className="field">
          <span>{t("End Date")}</span>
          <input type="date" {...register("endDate")} />
        </label>

        <label className="field">
          <span>أيام الاحتفاظ</span>
          <input type="number" min="1" {...register("holdDays")} />
        </label>

        <label className="field">
          <span>أقل نتيجة فنية</span>
          <input type="number" min="1" {...register("minTechnicalScore")} />
        </label>

        <label className="field">
          <span>حد الشراء</span>
          <input type="number" min="1" {...register("buyScoreThreshold")} />
        </label>

        <label className="field">
          <span>حد البيع</span>
          <input type="number" min="1" {...register("sellScoreThreshold")} />
        </label>

        <div className="form-actions">
          <button className="primary-button" type="submit" disabled={loading}>
            {loading ? "جارٍ التشغيل..." : `تشغيل اختبار ${mode === "vectorbt" ? "VectorBT" : mode === "classic" ? "كلاسيكي" : mode.toUpperCase()}`}
          </button>
        </div>

        <ErrorBanner message={error} />
      </form>
      </FilterBar>

      <SectionCard
        title="ملخص الاختبار التاريخي"
        description="ملخص واضح لنتائج الاختبار التاريخي القادم من المسار الحالي في الباك إند."
      >
        {loading ? <LoadingSkeleton lines={6} /> : null}

        {result ? (
          <>
            <SummaryStrip
              items={[
                { label: "Engine", value: result.engine ?? "classic" },
                { label: "Instrument", value: result.instrument ?? "-" },
                { label: "Trades", value: result.trades ?? "-" },
                {
                  label: "Win Rate %",
                  value: result.win_rate_pct ?? result.overall_win_rate_pct ?? "-",
                },
              ]}
            />
            <div className="result-grid">
              {result.engine === "vectorbt" ? (
                <>
                  <ResultCard label="Total Return %" value={result.returns_stats?.total_return_pct ?? "-"} />
                  <ResultCard label="Annualized Return %" value={result.returns_stats?.annualized_return_pct ?? "-"} />
                  <ResultCard label="Sharpe Ratio" value={result.returns_stats?.sharpe_ratio ?? "-"} />
                  <ResultCard label="Max Drawdown %" value={result.drawdown_stats?.max_drawdown_pct ?? "-"} />
                  <ResultCard label="Profit Factor" value={result.profit_factor ?? "-"} />
                  <ResultCard label="Final Equity" value={result.final_equity ?? "-"} />
                </>
              ) : mode !== "classic" ? (
                <>
                  <ResultCard label="Classic Trades" value={result.classic_summary?.trades ?? "-"} />
                  <ResultCard label="VectorBT Return %" value={result.vectorbt_summary?.total_return_pct ?? "-"} />
                  <ResultCard label="Smart Signal" value={result.smart_output?.signal ?? "-"} />
                  <ResultCard label="Smart Confidence" value={result.smart_output?.confidence ?? "-"} />
                  <ResultCard label="Smart Score" value={result.smart_output?.ensemble_score ?? "-"} />
                  <ResultCard label="Smart Reasoning" value={result.smart_output?.reasoning ?? "-"} />
                </>
              ) : (
                <>
                  <ResultCard label="Avg Trade Return %" value={result.avg_trade_return_pct ?? "-"} />
                  <ResultCard label="Median Trade Return %" value={result.median_trade_return_pct ?? "-"} />
                  <ResultCard label="Best Trade %" value={result.best_trade_pct ?? "-"} />
                  <ResultCard label="Worst Trade %" value={result.worst_trade_pct ?? "-"} />
                  <ResultCard label="Avg MTF Score" value={result.avg_mtf_score ?? "-"} />
                  <ResultCard label="Avg RS Score" value={result.avg_rs_score ?? "-"} />
                </>
              )}
            </div>
          </>
        ) : !loading && !error ? (
          <EmptyState
            title={t("No backtest result yet")}
            description={t("Submit a backtest request to view the returned summary metrics.")}
          />
        ) : null}
      </SectionCard>

      {result && chartOption ? (
        <ChartCard
          title={result.engine === "vectorbt" ? "منحنى رأس المال VectorBT" : "مؤشرات الاختبار التاريخي"}
          description={
            result.engine === "vectorbt"
              ? "منحنى رأس مال حقيقي مبني من مخرجات محفظة VectorBT القادمة من الباك إند."
              : mode !== "classic"
                ? "مقارنة سريعة بين الكلاسيكي وVectorBT والطبقات الذكية."
              : "مخطط حقيقي مبني من مؤشرات ملخص الاختبار التاريخي."
          }
          option={chartOption}
        />
      ) : (
        <SectionCard
          title="مؤشرات الاختبار التاريخي"
          description="سيظهر هنا مخطط حقيقي بعد نجاح تشغيل الاختبار التاريخي."
        />
      )}
    </PageFrame>
  );
}
