import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import PageFrame from "../components/ui/PageFrame";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import { fetchAiStatus, getNewsFeed, refreshNewsFeed } from "../api/ai";

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

function formatTime(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("ar-SA", {
      hour: "2-digit",
      minute: "2-digit",
      month: "short",
      day: "numeric",
    });
  } catch {
    return "—";
  }
}

function sentimentTone(sentiment) {
  const normalized = String(sentiment || "").toLowerCase();
  if (normalized === "positive" || normalized === "bullish") return "positive";
  if (normalized === "negative" || normalized === "bearish") return "negative";
  return "neutral";
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

function NewsFeedCard({ item }) {
  return (
    <article className="news-card news-card--full">
      <div className="news-card-header">
        <div className="news-card-tags">
          {item?.instrument ? <span className="news-card-symbol">{item.instrument}</span> : null}
          {item?.sentiment ? <StatusBadge label={item.sentiment} tone={sentimentTone(item.sentiment)} /> : null}
          {item?.event_type ? <span className="news-card-score">{String(item.event_type).replace("_", " ")}</span> : null}
          {item?.impact_score != null ? <span className="news-card-score">Impact {Number(item.impact_score).toFixed(2)}</span> : null}
        </div>
        {item?.source ? <span className="news-card-source">{item.source}</span> : null}
      </div>
      <h3 className="news-card-title">
        {item?.url ? (
          <a href={item.url} target="_blank" rel="noreferrer">
            {item.title || "بدون عنوان"}
          </a>
        ) : (
          item?.title || "بدون عنوان"
        )}
      </h3>
      <div className="news-card-footer">
        <span>{formatTime(item?.captured_at || item?.published)}</span>
        <span>
          {item?.relevance_score != null ? `Relevance ${Number(item.relevance_score).toFixed(2)}` : item?.id ? `#${item.id}` : ""}
        </span>
      </div>
    </article>
  );
}

export default function AINewsPage() {
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const [feedData, setFeedData] = useState(null);
  const [feedLoading, setFeedLoading] = useState(true);
  const [feedError, setFeedError] = useState("");
  const [aiStatus, setAiStatus] = useState(null);
  const [searchParams] = useSearchParams();
  const refreshTimerRef = useRef(null);
  const sourceRefreshTimestampRef = useRef(0);
  const clientTimeZone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch {
      return "UTC";
    }
  }, []);

  const symbolFilter = searchParams.get("symbol") || "";

  useEffect(() => {
    fetchAiStatus().then(setAiStatus).catch(() => {});
  }, []);

  useEffect(() => {
    let active = true;
    sourceRefreshTimestampRef.current = 0;

    async function loadFeed() {
      setFeedLoading(true);
      setFeedError("");
      try {
        const shouldRefreshSource =
          isToday(selectedDate) &&
          (sourceRefreshTimestampRef.current === 0 || (Date.now() - sourceRefreshTimestampRef.current) >= 5 * 60 * 1000);

        if (shouldRefreshSource) {
          await refreshNewsFeed(symbolFilter ? [symbolFilter] : null, 5);
          sourceRefreshTimestampRef.current = Date.now();
        }
        const payload = await getNewsFeed(toDateStr(selectedDate), 50, 0, symbolFilter || null, clientTimeZone);
        if (active) {
          setFeedData(payload);
        }
      } catch (error) {
        if (active) {
          setFeedError(error.message || "فشل تحميل الأخبار.");
        }
      } finally {
        if (active) {
          setFeedLoading(false);
        }
      }
    }

    loadFeed().catch(() => {});
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
    }
    if (isToday(selectedDate)) {
      refreshTimerRef.current = setInterval(() => loadFeed().catch(() => {}), 60_000);
    } else {
      sourceRefreshTimestampRef.current = 0;
    }

    return () => {
      active = false;
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
      }
    };
  }, [selectedDate, symbolFilter, clientTimeZone]);

  const items = useMemo(() => Array.isArray(feedData?.items) ? feedData.items : [], [feedData]);
  const positiveCount = items.filter((item) => sentimentTone(item.sentiment) === "positive").length;
  const negativeCount = items.filter((item) => sentimentTone(item.sentiment) === "negative").length;
  const neutralCount = items.filter((item) => sentimentTone(item.sentiment) === "neutral").length;
  const topSources = useMemo(() => {
    const counts = new Map();
    items.forEach((item) => {
      const key = item?.source || "Unknown";
      counts.set(key, (counts.get(key) || 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [items]);

  const nextDisabled = isFuture(nextDay(selectedDate));

  return (
    <PageFrame
      title="الأخبار"
      description="غرفة أخبار احترافية تعرض العنوان والمصدر والوقت والرمز المرتبط وحالة المعنويات عندما تتوفر."
      eyebrow="AI Research"
      headerActions={
        <>
          {symbolFilter ? <StatusBadge label={`رمز: ${symbolFilter.toUpperCase()}`} tone="accent" /> : null}
          <StatusBadge label={aiStatus?.effective_status === "ready" ? "AI جاهز" : "AI غير متصل"} tone={aiStatus?.effective_status === "ready" ? "positive" : "warning"} />
        </>
      }
    >
      <ErrorBanner message={feedError} />

      <section className="news-toolbar-card">
        <div className="news-toolbar-main">
          <button className="icon-button news-nav-arrow" type="button" onClick={() => setSelectedDate((current) => prevDay(current))} aria-label="اليوم السابق">
            &#8594;
          </button>
          <div className="news-toolbar-copy">
            <strong>{formatArabicDate(selectedDate)}</strong>
            <span>{isToday(selectedDate) ? "عرض اليوم الحالي مع تحديث تلقائي" : "عرض أرشيف يومي"}</span>
          </div>
          <button className="icon-button news-nav-arrow" type="button" onClick={() => setSelectedDate((current) => nextDay(current))} aria-label="اليوم التالي" disabled={nextDisabled} style={{ opacity: nextDisabled ? 0.35 : 1 }}>
            &#8592;
          </button>
        </div>
        {!isToday(selectedDate) ? (
          <button className="secondary-button news-today-btn" type="button" onClick={() => setSelectedDate(new Date())}>
            اليوم
          </button>
        ) : null}
      </section>

      {feedLoading ? (
        <LoadingSkeleton lines={8} />
      ) : (
        <div className="command-grid">
          <SectionCard
            className="col-span-8"
            title="تغذية الأخبار"
            description={symbolFilter ? `النتائج الحالية مفلترة على ${symbolFilter.toUpperCase()}.` : "آخر الأخبار المجمعة من المصدر الحالي في المشروع."}
            action={<StatusBadge label={items.length ? `${items.length} خبر` : "لا توجد"} tone={items.length ? "accent" : "subtle"} dot={false} />}
          >
            {items.length ? (
              <div className="news-card-grid news-card-grid--single">
                {items.map((item) => <NewsFeedCard key={item.id} item={item} />)}
              </div>
            ) : (
              <EmptyState title="لا توجد أخبار لهذا اليوم" description="المصدر الحالي لم يرجع عناصر لهذا التاريخ. جرّب يوماً آخر أو دع عملية الجمع تعمل لفترة أطول." />
            )}
          </SectionCard>

          <SectionCard className="col-span-4" title="ملخص سريع" description="تفكيك سريع للتغذية الحالية حسب المعنويات والمصادر.">
            <div className="analysis-mini-grid">
              <MetricCard label="الإجمالي" value={items.length} detail={feedData?.date || "—"} tone="accent" />
              <MetricCard label="إيجابي" value={positiveCount} detail="Positive / Bullish" tone="positive" />
              <MetricCard label="سلبي" value={negativeCount} detail="Negative / Bearish" tone="negative" />
              <MetricCard label="محايد" value={neutralCount} detail="Neutral / Missing" tone="warning" />
            </div>

            <div className="dashboard-subsection">
              <div className="dashboard-subsection-head">
                <strong>أكثر المصادر حضورًا</strong>
                <span>Top sources</span>
              </div>
              <div className="dashboard-list">
                {topSources.length ? (
                  topSources.map(([source, count]) => (
                    <div key={source} className="dashboard-list-item">
                      <div className="dashboard-list-copy">
                        <strong>{source}</strong>
                        <p>عدد العناصر في التاريخ الحالي</p>
                      </div>
                      <div className="dashboard-list-meta">
                        <StatusBadge label={`${count} خبر`} tone="subtle" dot={false} />
                      </div>
                    </div>
                  ))
                ) : (
                  <EmptyState title="لا توجد مصادر بعد" description="عندما تصل أخبار حقيقية ستظهر هنا قائمة المصادر الأكثر نشاطًا." />
                )}
              </div>
            </div>
          </SectionCard>
        </div>
      )}
    </PageFrame>
  );
}
