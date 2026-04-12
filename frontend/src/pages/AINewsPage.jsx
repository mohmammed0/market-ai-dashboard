import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { zodResolver } from "@hookform/resolvers/zod";

import PageFrame from "../components/ui/PageFrame";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { analyzeAiNews, fetchAiStatus, getNewsFeed } from "../lib/api";
import { aiNewsSchema } from "../lib/forms";
import { t } from "../lib/i18n";


// ──────────────────────────────────────────────
// Date helpers
// ──────────────────────────────────────────────
function toDateStr(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function formatArabicDate(date) {
  return date.toLocaleDateString("ar-SA", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function prevDay(date) {
  const d = new Date(date);
  d.setDate(d.getDate() - 1);
  return d;
}

function nextDay(date) {
  const d = new Date(date);
  d.setDate(d.getDate() + 1);
  return d;
}

function isToday(date) {
  return toDateStr(date) === toDateStr(new Date());
}

function isFuture(date) {
  return toDateStr(date) > toDateStr(new Date());
}


// ──────────────────────────────────────────────
// Sentiment helpers
// ──────────────────────────────────────────────
function sentimentTone(sentiment) {
  if (!sentiment) return "subtle";
  const s = String(sentiment).toLowerCase();
  if (s === "positive" || s === "bullish") return "accent";
  if (s === "negative" || s === "bearish") return "warning";
  return "subtle";
}

function sentimentLabel(sentiment) {
  if (!sentiment) return null;
  const s = String(sentiment).toLowerCase();
  if (s === "positive" || s === "bullish") return "صاعد";
  if (s === "negative" || s === "bearish") return "هابط";
  return "محايد";
}

function formatTime(isoStr) {
  if (!isoStr) return "";
  try {
    return new Date(isoStr).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}


// ──────────────────────────────────────────────
// NewsItem component
// ──────────────────────────────────────────────
function NewsItem({ item }) {
  const tone = sentimentTone(item.sentiment);
  const label = sentimentLabel(item.sentiment);
  const timeStr = formatTime(item.captured_at);

  return (
    <div className="news-feed-item">
      <div className="news-feed-item-header">
        <span className="news-feed-instrument">{item.instrument}</span>
        {label && <StatusBadge label={label} tone={tone} />}
      </div>
      <p className="news-feed-title">
        {item.url ? (
          <a href={item.url} target="_blank" rel="noopener noreferrer" className="news-feed-link">
            {item.title || "(بدون عنوان)"}
          </a>
        ) : (
          item.title || "(بدون عنوان)"
        )}
      </p>
      <div className="news-feed-meta">
        {item.source && <span className="news-feed-source">{item.source}</span>}
        {timeStr && <span className="news-feed-time">{timeStr}</span>}
        {item.score != null && (
          <span className="news-feed-score">نقاط: {item.score}</span>
        )}
      </div>
    </div>
  );
}


// ──────────────────────────────────────────────
// Manual analysis form helpers
// ──────────────────────────────────────────────
function parseItems(text) {
  return String(text || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function listOrFallback(items) {
  return items?.length ? items : ["None highlighted"];
}


// ──────────────────────────────────────────────
// Main page
// ──────────────────────────────────────────────
export default function AINewsPage() {
  // Feed state
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const [feedData, setFeedData] = useState(null);
  const [feedLoading, setFeedLoading] = useState(true);
  const [feedError, setFeedError] = useState("");
  const refreshTimerRef = useRef(null);

  // Manual analysis state
  const [showManualForm, setShowManualForm] = useState(false);
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

  // Load AI status once
  useEffect(() => {
    let active = true;
    const symbol = searchParams.get("symbol");
    if (symbol) setValue("symbol", symbol.trim().toUpperCase());

    fetchAiStatus()
      .then((data) => { if (active) setStatus(data); })
      .catch((e) => { if (active) setError(e.message || "AI status request failed."); })
      .finally(() => { if (active) setLoadingStatus(false); });

    return () => { active = false; };
  }, [searchParams, setValue]);

  // Load feed whenever date changes
  useEffect(() => {
    let active = true;

    async function loadFeed() {
      setFeedLoading(true);
      setFeedError("");
      try {
        const data = await getNewsFeed(toDateStr(selectedDate), 50);
        if (active) setFeedData(data);
      } catch (e) {
        if (active) setFeedError(e.message || "فشل تحميل الأخبار.");
      } finally {
        if (active) setFeedLoading(false);
      }
    }

    loadFeed();

    // Auto-refresh every 60s (only when viewing today)
    if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    if (isToday(selectedDate)) {
      refreshTimerRef.current = setInterval(loadFeed, 60_000);
    }

    return () => {
      active = false;
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    };
  }, [selectedDate]);

  // Date navigation
  function goToPrevDay() { setSelectedDate((d) => prevDay(d)); }
  function goToNextDay() { if (!isFuture(nextDay(selectedDate))) setSelectedDate((d) => nextDay(d)); }
  function goToToday() { setSelectedDate(new Date()); }

  // Manual analysis submit
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

  const analysisResultTone = !result?.sentiment
    ? "subtle"
    : result.sentiment === "BULLISH"
    ? "accent"
    : result.sentiment === "BEARISH"
    ? "warning"
    : "subtle";

  const isNextDisabled = isFuture(nextDay(selectedDate));

  return (
    <PageFrame
      title="محلل أخبار الذكاء الاصطناعي"
      description="متابعة أخبار السوق لحظة بلحظة مع التحليل الآلي بالذكاء الاصطناعي المحلي."
      eyebrow="AI Research"
      headerActions={
        <StatusBadge
          label={status?.effective_status === "ready" ? "AI جاهز" : "AI معطّل"}
          tone={status?.effective_status === "ready" ? "accent" : "warning"}
        />
      }
    >
      {/* ── Date Navigation Bar ── */}
      <div className="panel news-date-nav">
        <button
          className="icon-button news-nav-arrow"
          onClick={goToPrevDay}
          aria-label="اليوم السابق"
          title="اليوم السابق"
        >
          &#8594;
        </button>

        <span className="news-date-label">{formatArabicDate(selectedDate)}</span>

        <button
          className="icon-button news-nav-arrow"
          onClick={goToNextDay}
          disabled={isNextDisabled}
          aria-label="اليوم التالي"
          title="اليوم التالي"
          style={{ opacity: isNextDisabled ? 0.35 : 1 }}
        >
          &#8592;
        </button>

        {!isToday(selectedDate) && (
          <button className="secondary-button news-today-btn" onClick={goToToday}>
            اليوم
          </button>
        )}
      </div>

      {/* ── News Feed ── */}
      <div className="panel result-panel">
        <SectionHeader
          title="تغذية الأخبار"
          description={
            feedData
              ? `${feedData.total} خبر بتاريخ ${feedData.date}`
              : "آخر الأخبار المُجمَّعة تلقائياً"
          }
          badge={isToday(selectedDate) ? "مباشر" : null}
        />

        {feedLoading && <LoadingSkeleton lines={6} />}

        {!feedLoading && feedError && (
          <ErrorBanner message={feedError} />
        )}

        {!feedLoading && !feedError && feedData && feedData.items.length === 0 && (
          <EmptyState
            title="لا توجد أخبار لهذا اليوم"
            description="لم يتم جمع أي أخبار في هذا التاريخ بعد. حاول التنقل إلى يوم آخر أو أضف خبراً يدوياً."
          />
        )}

        {!feedLoading && !feedError && feedData && feedData.items.length > 0 && (
          <div className="news-feed-list">
            {feedData.items.map((item) => (
              <NewsItem key={item.id} item={item} />
            ))}
          </div>
        )}
      </div>

      {/* ── Manual Analysis (Collapsible) ── */}
      <div className="panel result-panel">
        <button
          className="collapsible-header"
          onClick={() => setShowManualForm((v) => !v)}
          aria-expanded={showManualForm}
        >
          <SectionHeader
            title="تحليل يدوي"
            description="أدخل عنواناً أو نص مقال للحصول على تحليل آني بالذكاء الاصطناعي."
          />
          <span className="collapsible-icon">{showManualForm ? "▲" : "▼"}</span>
        </button>

        {showManualForm && (
          <>
            <div className="panel result-panel" style={{ marginTop: "1rem" }}>
              <SectionHeader title="AI Runtime" description="حالة الذكاء الاصطناعي لهذا المثيل." />
              {loadingStatus ? (
                <LoadingSkeleton lines={4} />
              ) : status ? (
                <SummaryStrip
                  items={[
                    { label: "المزوّد", value: status.effective_provider || "-", badge: "Provider" },
                    { label: "الحالة", value: status.effective_status || "-", badge: "Status" },
                    { label: "Ollama", value: status.ollama?.status || "-", badge: "Local" },
                    { label: "النموذج", value: status.ollama?.model || status.openai?.model || "-", badge: "Model" },
                  ]}
                />
              ) : (
                <EmptyState title={t("AI status unavailable")} description={t("The backend AI status route did not return runtime information.")} />
              )}
            </div>

            <form className="analyze-form filter-form" onSubmit={handleSubmit(onSubmit)} style={{ marginTop: "1rem" }}>
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
                <button
                  className="primary-button"
                  type="submit"
                  disabled={loading || !(status?.effective_status === "ready")}
                >
                  {loading ? "جارٍ التحليل..." : "تحليل الخبر"}
                </button>
              </div>

              <ErrorBanner message={error} />

              {!loadingStatus && status && status.effective_status !== "ready" ? (
                <div className="status-message warning">{status.detail}</div>
              ) : null}
            </form>

            {result && (
              <div className="panel result-panel" style={{ marginTop: "1rem" }}>
                <SectionHeader
                  title="Structured Analysis"
                  description="Strict JSON output rendered into concise trading-style decision support."
                  badge={result?.impact_horizon || "Analysis"}
                />
                {loading ? <LoadingSkeleton lines={8} /> : null}
                <SummaryStrip
                  items={[
                    { label: "Sentiment", value: <StatusBadge label={result.sentiment} tone={analysisResultTone} />, badge: "AI" },
                    { label: "Confidence", value: `${Number(result.confidence || 0).toFixed(0)}%`, badge: "Score" },
                    { label: "Horizon", value: result.impact_horizon, badge: "Timing" },
                    { label: "Tickers", value: result.affected_tickers?.join(", ") || "-", badge: "Scope" },
                  ]}
                />
                <p style={{ margin: "0.75rem 0" }}>{result.summary}</p>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>{result.analyst_note}</p>
              </div>
            )}
          </>
        )}
      </div>
    </PageFrame>
  );
}
