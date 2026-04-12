import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import PageFrame from "../components/ui/PageFrame";
import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import { fetchAiStatus, getNewsFeed } from "../lib/api";


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
// Main page
// ──────────────────────────────────────────────
export default function AINewsPage() {
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const [feedData, setFeedData] = useState(null);
  const [feedLoading, setFeedLoading] = useState(true);
  const [feedError, setFeedError] = useState("");
  const [aiStatus, setAiStatus] = useState(null);
  const refreshTimerRef = useRef(null);
  const [searchParams] = useSearchParams();

  // Load AI status once
  useEffect(() => {
    fetchAiStatus().then(setAiStatus).catch(() => {});
  }, []);

  // Filter by symbol from URL param
  const symbolFilter = searchParams.get("symbol") || "";

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

    // Auto-refresh every 60s when viewing today
    if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    if (isToday(selectedDate)) {
      refreshTimerRef.current = setInterval(loadFeed, 60_000);
    }

    return () => {
      active = false;
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    };
  }, [selectedDate]);

  function goToPrevDay() { setSelectedDate((d) => prevDay(d)); }
  function goToNextDay() { if (!isFuture(nextDay(selectedDate))) setSelectedDate((d) => nextDay(d)); }
  function goToToday() { setSelectedDate(new Date()); }

  const isNextDisabled = isFuture(nextDay(selectedDate));

  // Optional: filter items by symbol if URL param present
  const items = feedData?.items
    ? symbolFilter
      ? feedData.items.filter((i) => i.instrument?.toUpperCase() === symbolFilter.toUpperCase())
      : feedData.items
    : [];

  return (
    <PageFrame
      title="تغذية أخبار السوق"
      description="آخر الأخبار المُجمَّعة تلقائياً مع التحليل الآلي بالذكاء الاصطناعي المحلي."
      eyebrow="AI Research"
      headerActions={
        <StatusBadge
          label={aiStatus?.effective_status === "ready" ? "AI جاهز" : "AI غير متصل"}
          tone={aiStatus?.effective_status === "ready" ? "accent" : "subtle"}
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

        {!feedLoading && feedError && <ErrorBanner message={feedError} />}

        {!feedLoading && !feedError && items.length === 0 && (
          <EmptyState
            title="لا توجد أخبار لهذا اليوم"
            description="سيتم جمع الأخبار تلقائياً. حاول التنقل إلى يوم آخر."
          />
        )}

        {!feedLoading && !feedError && items.length > 0 && (
          <div className="news-feed-list">
            {items.map((item) => (
              <NewsItem key={item.id} item={item} />
            ))}
          </div>
        )}
      </div>
    </PageFrame>
  );
}
