import { useEffect, useMemo, useState } from "react";

import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import PageFrame from "../components/ui/PageFrame";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import {
  ingestKnowledge,
  listRecentKnowledge,
  runAiResearch,
  searchKnowledge,
} from "../api/knowledge";

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("ar-SA", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

function normalizeSymbol(value) {
  return String(value || "").trim().toUpperCase();
}

function compactScore(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return num.toFixed(2);
}

function KnowledgeList({ items, loading, selectedId, onSelect }) {
  if (loading) {
    return <LoadingSkeleton lines={7} />;
  }
  if (!items.length) {
    return (
      <EmptyState
        title="لا توجد نتائج"
        description="لا يوجد مستندات مطابقة للفلاتر الحالية."
      />
    );
  }
  return (
    <div className="dashboard-list">
      {items.map((item) => (
        <button
          key={item.document_id}
          type="button"
          className={`dashboard-list-item dashboard-list-item--interactive${selectedId === item.document_id ? " active" : ""}`}
          onClick={() => onSelect(item)}
        >
          <div className="dashboard-list-copy">
            <strong>{item.title || item.document_id}</strong>
            <p>{item.summary || item.source_type || "Knowledge document"}</p>
            <p>{formatDate(item.created_at)}</p>
          </div>
          <div className="dashboard-list-meta">
            <StatusBadge label={item.source_type || "system"} tone="subtle" dot={false} />
            {item.symbol ? <StatusBadge label={item.symbol} tone="accent" dot={false} /> : null}
            {item.hybrid_score != null || item.score != null ? (
              <StatusBadge label={`score ${compactScore(item.hybrid_score ?? item.score)}`} tone="warning" dot={false} />
            ) : null}
          </div>
        </button>
      ))}
    </div>
  );
}

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [symbol, setSymbol] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [useVector, setUseVector] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState(null);
  const [selected, setSelected] = useState(null);

  const [noteTitle, setNoteTitle] = useState("");
  const [noteSummary, setNoteSummary] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteError, setNoteError] = useState("");

  const [researchLoading, setResearchLoading] = useState(false);
  const [researchError, setResearchError] = useState("");
  const [researchResult, setResearchResult] = useState(null);

  const tags = useMemo(
    () => tagsText.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean),
    [tagsText]
  );

  async function loadRecent() {
    setLoading(true);
    setError("");
    try {
      const response = await listRecentKnowledge({ limit: 25 });
      setPayload(response);
      const first = Array.isArray(response?.items) && response.items.length ? response.items[0] : null;
      setSelected(first);
    } catch (requestError) {
      setError(requestError.message || "تعذر تحميل مستندات المعرفة.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRecent().catch(() => {});
  }, []);

  async function runSearch(event) {
    event?.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await searchKnowledge({
        q: query,
        symbol: normalizeSymbol(symbol),
        sourceType,
        tags,
        limit: 25,
        offset: 0,
        useVector,
      });
      setPayload(response);
      const first = Array.isArray(response?.items) && response.items.length ? response.items[0] : null;
      setSelected(first);
    } catch (requestError) {
      setError(requestError.message || "تعذر تنفيذ البحث.");
    } finally {
      setLoading(false);
    }
  }

  async function saveManualNote(event) {
    event.preventDefault();
    if (!noteTitle.trim() && !noteContent.trim() && !noteSummary.trim()) {
      setNoteError("أدخل عنوانًا أو محتوى قبل الحفظ.");
      return;
    }
    setNoteSaving(true);
    setNoteError("");
    try {
      await ingestKnowledge({
        source_type: "manual_note",
        symbol: normalizeSymbol(symbol) || normalizeSymbol(selected?.symbol),
        title: noteTitle.trim() || "Manual note",
        summary: noteSummary.trim() || null,
        content: noteContent.trim() || null,
        tags,
        metadata: {
          created_from: "knowledge_ui",
        },
      });
      setNoteTitle("");
      setNoteSummary("");
      setNoteContent("");
      await runSearch();
    } catch (requestError) {
      setNoteError(requestError.message || "فشل حفظ الملاحظة.");
    } finally {
      setNoteSaving(false);
    }
  }

  async function runContextualResearch() {
    const candidateSymbol = normalizeSymbol(selected?.symbol || symbol);
    if (!candidateSymbol) {
      setResearchError("اختر رمزًا أو مستندًا مرتبطًا بسهم قبل التحليل.");
      return;
    }
    setResearchLoading(true);
    setResearchError("");
    try {
      const result = await runAiResearch({
        symbol: candidateSymbol,
        question: query.trim() || `Provide contextual research for ${candidateSymbol}.`,
        include_news: true,
        knowledge_limit: 8,
        use_vector: useVector,
        context_document_ids: selected?.document_id ? [selected.document_id] : [],
        persist: true,
      });
      setResearchResult(result);
    } catch (requestError) {
      setResearchError(requestError.message || "تعذر تنفيذ التحليل السياقي.");
    } finally {
      setResearchLoading(false);
    }
  }

  const items = Array.isArray(payload?.items) ? payload.items : [];
  const retrieval = payload?.retrieval || {};

  return (
    <PageFrame
      title="مركز المعرفة والأبحاث"
      description="بحث داخلي سريع على مخرجات النظام والملاحظات، مع تحليل AI سياقي مبني على الأدلة."
      eyebrow="AI Research"
      headerActions={<StatusBadge label={retrieval.mode || "lexical"} tone="accent" dot={false} />}
    >
      <ErrorBanner message={error || noteError || researchError} />

      <section className="analysis-toolbar-card">
        <form className="analyze-form filter-form knowledge-search-form" onSubmit={runSearch}>
          <label className="field">
            <span>بحث نصي</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="ابحث في التحليلات، الأخبار، والملاحظات..."
            />
          </label>

          <label className="field">
            <span>الرمز</span>
            <input
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="AAPL"
            />
          </label>

          <label className="field">
            <span>نوع المصدر</span>
            <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
              <option value="">الكل</option>
              <option value="manual_note">Manual Note</option>
              <option value="ai_research_report">AI Research</option>
              <option value="market_brief">Market Brief</option>
              <option value="news">News</option>
            </select>
          </label>

          <label className="field">
            <span>Tags</span>
            <input
              value={tagsText}
              onChange={(event) => setTagsText(event.target.value)}
              placeholder="earnings, breakout"
            />
          </label>

          <label className="field checkbox-field">
            <span>Hybrid</span>
            <input
              type="checkbox"
              checked={useVector}
              onChange={(event) => setUseVector(event.target.checked)}
            />
          </label>

          <div className="form-actions">
            <button className="primary-button" type="submit" disabled={loading}>
              {loading ? "جارٍ البحث..." : "بحث"}
            </button>
            <button className="secondary-button" type="button" onClick={() => loadRecent()} disabled={loading}>
              آخر المستندات
            </button>
            <button className="secondary-button" type="button" onClick={runContextualResearch} disabled={researchLoading}>
              {researchLoading ? "تحليل..." : "تحليل سياقي"}
            </button>
          </div>
        </form>
      </section>

      <div className="command-grid">
        <SectionCard
          className="col-span-7"
          title="نتائج البحث"
          description="نتائج مرتبة حسب الصلة الزمنية والنصية."
          action={<StatusBadge label={`${items.length} نتائج`} tone={items.length ? "subtle" : "warning"} dot={false} />}
        >
          <KnowledgeList
            items={items}
            loading={loading}
            selectedId={selected?.document_id}
            onSelect={setSelected}
          />
        </SectionCard>

        <SectionCard
          className="col-span-5"
          title="تفاصيل المستند"
          description="الملخص، الأدلة، وبيانات المصدر."
        >
          {selected ? (
            <div className="knowledge-detail-stack">
              <div className="analysis-chip-row">
                <StatusBadge label={selected.source_type || "source"} tone="subtle" dot={false} />
                {selected.symbol ? <StatusBadge label={selected.symbol} tone="accent" dot={false} /> : null}
                <StatusBadge label={formatDate(selected.created_at)} tone="subtle" dot={false} />
              </div>
              <h3 className="news-card-title">{selected.title || selected.document_id}</h3>
              <p className="analysis-hero-reasoning">{selected.summary || "No summary available."}</p>
              <div className="dashboard-source-card">
                <strong>المحتوى</strong>
                <p>{selected.content || "لا يوجد محتوى نصي محفوظ لهذا المستند."}</p>
              </div>
              <div className="dashboard-source-card">
                <strong>Tags</strong>
                <p>{Array.isArray(selected.tags) && selected.tags.length ? selected.tags.join(", ") : "—"}</p>
              </div>
            </div>
          ) : (
            <EmptyState title="اختر مستندًا" description="سيظهر هنا المحتوى التفصيلي للمستند المحدد." />
          )}
        </SectionCard>

        <SectionCard className="col-span-4" title="Retrieval Telemetry" description="جودة البحث الحالي وتشغيل hybrid.">
          <div className="analysis-mini-grid">
            <MetricCard label="Mode" value={retrieval.mode || "lexical"} detail={retrieval.vector_provider || "—"} tone="accent" />
            <MetricCard label="Lexical Hits" value={retrieval.lexical_hits ?? 0} />
            <MetricCard label="Vector Hits" value={retrieval.vector_hits ?? 0} />
            <MetricCard label="Vector Ready" value={retrieval.vector_ready ? "Yes" : "No"} />
          </div>
        </SectionCard>

        <SectionCard className="col-span-4" title="إضافة ملاحظة" description="توثيق سريع ومباشر داخل قاعدة المعرفة.">
          <form className="analyze-form filter-form" onSubmit={saveManualNote}>
            <label className="field">
              <span>العنوان</span>
              <input value={noteTitle} onChange={(event) => setNoteTitle(event.target.value)} placeholder="مثال: Earnings thesis" />
            </label>
            <label className="field">
              <span>ملخص</span>
              <input value={noteSummary} onChange={(event) => setNoteSummary(event.target.value)} placeholder="ملخص قصير..." />
            </label>
            <label className="field">
              <span>المحتوى</span>
              <textarea className="field-textarea" value={noteContent} onChange={(event) => setNoteContent(event.target.value)} placeholder="أضف التفاصيل التي تريد حفظها..." />
            </label>
            <div className="form-actions">
              <button className="primary-button" type="submit" disabled={noteSaving}>
                {noteSaving ? "حفظ..." : "حفظ الملاحظة"}
              </button>
            </div>
          </form>
        </SectionCard>

        <SectionCard className="col-span-4" title="AI Context Result" description="خلاصة التحليل السياقي المبني على المستندات المحددة.">
          {researchLoading ? (
            <LoadingSkeleton lines={6} />
          ) : researchResult ? (
            <div className="knowledge-research-result">
              <div className="analysis-chip-row">
                <StatusBadge label={researchResult.action?.toUpperCase() || "WATCH"} tone="accent" />
                <StatusBadge label={`${Number(researchResult.confidence || 0).toFixed(0)}%`} tone="warning" dot={false} />
                <StatusBadge label={researchResult.risk_level || "controlled"} tone="subtle" dot={false} />
              </div>
              <p className="analysis-hero-reasoning">{researchResult.summary}</p>
              <div className="dashboard-source-card">
                <strong>Key points</strong>
                <p>{Array.isArray(researchResult.key_points) ? researchResult.key_points.join(" • ") : "—"}</p>
              </div>
              <div className="dashboard-source-card">
                <strong>Evidence</strong>
                <p>{Array.isArray(researchResult.evidence) ? `${researchResult.evidence.length} items` : "0"}</p>
              </div>
            </div>
          ) : (
            <EmptyState title="لا يوجد تحليل بعد" description="نفّذ تحليل سياقي من الأعلى وسيظهر الناتج هنا." />
          )}
        </SectionCard>
      </div>
    </PageFrame>
  );
}
