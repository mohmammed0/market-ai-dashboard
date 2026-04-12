import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/PageFrame";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import FilterBar from "../components/ui/FilterBar";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import ResultCard from "../components/ui/ResultCard";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { analyzeAiNews, fetchAiStatus } from "../lib/api";
import { aiNewsSchema } from "../lib/forms";
import { t } from "../lib/i18n";


function parseItems(text) {
  return String(text || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}


function listOrFallback(items) {
  return items?.length ? items : ["None highlighted"];
}


export default function AINewsPage() {
  const [status, setStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchParams] = useSearchParams();

  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
  } = useForm({
    resolver: zodResolver(aiNewsSchema),
    defaultValues: {
      symbol: "",
      headline: "",
      articleText: "",
      itemsText: "",
      marketContext: "",
    },
  });

  useEffect(() => {
    let active = true;
    const symbol = searchParams.get("symbol");
    if (symbol) {
      setValue("symbol", symbol.trim().toUpperCase());
    }

    fetchAiStatus()
      .then((data) => {
        if (active) {
          setStatus(data);
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message || "AI status request failed.");
        }
      })
      .finally(() => {
        if (active) {
          setLoadingStatus(false);
        }
      });

    return () => {
      active = false;
    };
  }, [searchParams, setValue]);

  const sentimentTone = useMemo(() => {
    if (!result?.sentiment) {
      return "subtle";
    }
    if (result.sentiment === "BULLISH") {
      return "accent";
    }
    if (result.sentiment === "BEARISH") {
      return "warning";
    }
    return "subtle";
  }, [result]);

  async function onSubmit(values) {
    setLoading(true);
    setError("");
    try {
      const data = await analyzeAiNews({
        symbol: String(values.symbol || "").trim().toUpperCase() || null,
        headline: String(values.headline || "").trim() || null,
        article_text: String(values.articleText || "").trim() || null,
        items: parseItems(values.itemsText),
        market_context: String(values.marketContext || "").trim() || null,
      });
      setResult(data);
    } catch (requestError) {
      setResult(null);
      setError(requestError.message || "AI news analysis failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageFrame
      title="AI News Analyst"
      description="Run OpenAI-powered structured analysis on headlines, article text, or short market-news snippets without disturbing the rest of the platform."
      eyebrow="AI Research"
      headerActions={<StatusBadge label={status?.enabled ? "OpenAI Ready" : "OpenAI Standby"} tone={status?.enabled ? "accent" : "warning"} />}
    >
      <FilterBar
        title="News Analysis Request"
        description="Paste a headline, article body, or several news bullets and receive strict structured output for trading research."
        action={<StatusBadge label={loading ? "Analyzing" : (loadingStatus ? "Checking" : "Structured Output")} tone={loading || loadingStatus ? "warning" : "subtle"} />}
      >
        <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)}>
          <div className="form-grid">
            <label className="field">
              <span>{t("Symbol")}</span>
              <input {...register("symbol")} placeholder="AAPL" />
            </label>

            <label className="field field-span-2">
              <span>العنوان</span>
              <input {...register("headline")} placeholder="أعلنت Nvidia عن شراكة جديدة في البنية التحتية للذكاء الاصطناعي..." />
              {errors.headline ? <small className="field-error">{errors.headline.message}</small> : null}
            </label>

            <label className="field field-span-2">
              <span>نص المقال</span>
              <textarea className="field-textarea" {...register("articleText")} placeholder="ألصق نص المقال الكامل هنا..." />
            </label>

            <label className="field field-span-2">
              <span>عناصر الأخبار</span>
              <textarea className="field-textarea" {...register("itemsText")} placeholder={"خبر واحد في كل سطر\nرفع التوجيهات المستقبلية\nتوقيع عقد جديد لمراكز البيانات"} />
            </label>

            <label className="field">
              <span>سياق السوق</span>
              <textarea className="field-textarea" {...register("marketContext")} placeholder="سياق اختياري مثل دوران القطاعات أو الخلفية الاقتصادية أو مقارنة المؤشر." />
            </label>
          </div>

          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={loading || !status?.enabled}>
              {loading ? "جارٍ التحليل..." : "تحليل الخبر"}
            </button>
          </div>

          <ErrorBanner message={error} />

          {!loadingStatus && status && !status.enabled ? (
            <div className="status-message warning">
              {status.detail}
            </div>
          ) : null}
        </form>
      </FilterBar>

      <div className="panel result-panel">
        <SectionHeader
          title="AI Runtime"
          description="Current OpenAI integration status for this backend runtime."
        />
        {loadingStatus ? (
          <LoadingSkeleton lines={4} />
        ) : status ? (
          <SummaryStrip
            items={[
              { label: "Enabled", value: status.enabled ? "yes" : "no", badge: "Config" },
              { label: "Configured", value: status.configured ? "yes" : "no", badge: "Key" },
              { label: "SDK", value: status.sdk_installed ? "installed" : "missing", badge: "Backend" },
              { label: "Model", value: status.model || "-", badge: "OpenAI" },
            ]}
          />
        ) : (
          <EmptyState title={t("AI status unavailable")} description={t("The backend AI status route did not return runtime information.")} />
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader
          title="Structured Analysis"
          description="Strict JSON output rendered into concise trading-style decision support."
          badge={result?.impact_horizon || "Analysis"}
        />
        {loading ? <LoadingSkeleton lines={8} /> : null}
        {result ? (
          <>
            <SummaryStrip
              items={[
                { label: "Sentiment", value: <StatusBadge label={result.sentiment} tone={sentimentTone} />, badge: "AI" },
                { label: "Confidence", value: `${Number(result.confidence || 0).toFixed(0)}%`, badge: "Score" },
                { label: "Horizon", value: result.impact_horizon, badge: "Timing" },
                { label: "Tickers", value: result.affected_tickers?.join(", ") || "-", badge: "Scope" },
              ]}
            />
            <div className="result-grid">
              <ResultCard label="Summary" value={result.summary} accent="result-wide" />
              <ResultCard label="Analyst Note" value={result.analyst_note} accent="result-wide" />
              <ResultCard label="Sentiment" value={result.sentiment} hint={result.impact_horizon} accent={`result-tone-${sentimentTone}`} />
              <ResultCard label="Confidence" value={`${Number(result.confidence || 0).toFixed(0)}%`} />
            </div>
            <div className="ai-news-grid">
              <div className="panel result-panel ai-news-panel">
                <SectionHeader title="Bullish Factors" description="Potentially supportive implications extracted from the provided text." />
                <div className="tag-list">
                  {listOrFallback(result.bullish_factors).map((item, index) => <span className="tag-chip bullish-chip" key={`bullish-${index}`}>{item}</span>)}
                </div>
              </div>
              <div className="panel result-panel ai-news-panel">
                <SectionHeader title="Bearish Factors" description="Potentially adverse implications or warning signs from the text." />
                <div className="tag-list">
                  {listOrFallback(result.bearish_factors).map((item, index) => <span className="tag-chip bearish-chip" key={`bearish-${index}`}>{item}</span>)}
                </div>
              </div>
              <div className="panel result-panel ai-news-panel">
                <SectionHeader title="Catalysts" description="Near-term developments the model judged worth monitoring." />
                <div className="tag-list">
                  {listOrFallback(result.catalysts).map((item, index) => <span className="tag-chip" key={`catalyst-${index}`}>{item}</span>)}
                </div>
              </div>
              <div className="panel result-panel ai-news-panel">
                <SectionHeader title="Risks" description="Explicit uncertainty, downside, or follow-up validation needs." />
                <div className="tag-list">
                  {listOrFallback(result.risks).map((item, index) => <span className="tag-chip warning-chip" key={`risk-${index}`}>{item}</span>)}
                </div>
              </div>
            </div>
          </>
        ) : !loading && !error ? (
          <EmptyState
            title={t("No AI news analysis yet")}
            description={t("Submit a headline, article body, or short list of news items to generate structured sentiment and catalyst analysis.")}
          />
        ) : null}
      </div>
    </PageFrame>
  );
}
