import { useNavigate } from "react-router-dom";

import EmptyState from "../components/ui/EmptyState";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import MetricCard from "../components/ui/MetricCard";
import PageFrame from "../components/ui/PageFrame";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { useAppData } from "../store/AppDataStore";

function money(value) {
  const numeric = Number(value ?? 0);
  return `$${numeric.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function pct(value) {
  const numeric = Number(value ?? 0);
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(2)}%`;
}

function compactDate(value) {
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

function signalTone(signal) {
  const normalized = String(signal || "").trim().toUpperCase();
  if (normalized === "BUY" || normalized === "ADD" || normalized === "BULLISH") return "positive";
  if (normalized === "SELL" || normalized === "EXIT" || normalized === "BEARISH") return "negative";
  if (normalized === "TRIM" || normalized === "HOLD" || normalized === "NEUTRAL") return "warning";
  return "neutral";
}

function statusTone(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (["ready", "ok", "running", "connected", "completed", "success"].includes(normalized)) return "positive";
  if (["warning", "idle", "disabled", "pending", "queued"].includes(normalized)) return "warning";
  if (["failed", "error", "unavailable", "blocked"].includes(normalized)) return "negative";
  return "neutral";
}

function sourceTone(isBroker) {
  return isBroker ? "info" : "warning";
}

function eventTone(level, stage) {
  const normalizedLevel = String(level || "").trim().toLowerCase();
  if (normalizedLevel === "error") return "negative";
  if (normalizedLevel === "warning" || String(stage || "").toLowerCase().includes("error")) return "warning";
  if (["completed", "success", "ok"].some((token) => String(stage || "").toLowerCase().includes(token))) return "positive";
  return "info";
}

function formatElapsed(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const rem = Math.floor(value % 60);
  return `${minutes}m ${rem}s`;
}

function IndexCard({ item, onInspect }) {
  const change = Number(item?.change_pct ?? 0);
  return (
    <button className="dashboard-market-card" type="button" onClick={() => onInspect(item?.symbol)}>
      <div className="dashboard-market-card-top">
        <div>
          <strong>{item?.label || item?.symbol || "—"}</strong>
          <span>{item?.symbol || "—"}</span>
        </div>
        <StatusBadge label={change >= 0 ? "صاعد" : "هابط"} tone={change >= 0 ? "positive" : "negative"} />
      </div>
      <div className="dashboard-market-card-price">{Number(item?.price ?? 0).toFixed(2)}</div>
      <div className={`dashboard-market-card-change ${change >= 0 ? "quote-positive" : "quote-negative"}`}>{pct(change)}</div>
    </button>
  );
}

function FeaturedTicker({ item, onNavigate }) {
  const change = Number(item?.change_pct ?? 0);
  return (
    <button className="dashboard-featured-row" type="button" onClick={() => onNavigate(`/ai-market?symbol=${encodeURIComponent(item?.symbol || "")}`)}>
      <div className="dashboard-featured-copy">
        <strong>{item?.symbol || "—"}</strong>
        <span>{item?.security_name || item?.label || "رمز مميز"}</span>
      </div>
      <div className="dashboard-featured-metric">
        <span>{Number(item?.price ?? 0).toFixed(2)}</span>
        <small className={change >= 0 ? "quote-positive" : "quote-negative"}>{pct(change)}</small>
      </div>
    </button>
  );
}

function PerformerRow({ item, onNavigate }) {
  const change = Number(item?.change_pct ?? 0);
  return (
    <button className="dashboard-list-item dashboard-list-item--interactive dashboard-list-item--ranked" type="button" onClick={() => onNavigate(`/ai-market?symbol=${encodeURIComponent(item?.symbol || "")}`)}>
      <div className="dashboard-rank-badge">{item?.rank || "—"}</div>
      <div className="dashboard-list-copy">
        <strong>{item?.symbol || "—"}</strong>
        <p>{item?.security_name || item?.label || "سهم قيادي"}</p>
      </div>
      <div className="dashboard-list-meta">
        <span>{Number(item?.price ?? 0).toFixed(2)}</span>
        <small className={change >= 0 ? "quote-positive" : "quote-negative"}>{pct(change)}</small>
      </div>
    </button>
  );
}

function NewsCard({ item, onNavigate }) {
  const sentiment = String(item?.sentiment || "").toLowerCase();
  const tone = sentiment === "positive" || sentiment === "bullish" ? "positive" : sentiment === "negative" || sentiment === "bearish" ? "negative" : "neutral";
  return (
    <article className="news-card">
      <div className="news-card-header">
        <div className="news-card-tags">
          {item?.instrument ? (
            <button className="news-card-symbol" type="button" onClick={() => onNavigate(`/ai-market?symbol=${encodeURIComponent(item.instrument)}`)}>
              {item.instrument}
            </button>
          ) : null}
          {item?.sentiment ? <StatusBadge label={item.sentiment} tone={tone} /> : null}
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
        <span>{compactDate(item?.captured_at || item?.published)}</span>
        {item?.score != null ? <span className="news-card-score">Score {item.score}</span> : null}
      </div>
    </article>
  );
}

function OpportunityRow({ item, onNavigate }) {
  const signal = item?.signal || item?.stance || "HOLD";
  const action = item?.action || signal || "WATCH";
  const confidence = Number(item?.confidence ?? 0);
  const riskLabel = item?.risk_label || "RANGE";
  const reason = item?.reason || item?.best_setup || item?.setup_type || item?.notes || "فرصة مرتبة من محرك القرار.";
  return (
    <button className="dashboard-list-item dashboard-list-item--interactive" type="button" onClick={() => onNavigate(`/execution?symbol=${encodeURIComponent(item?.symbol || "")}`)}>
      <div className="dashboard-list-copy">
        <strong>{item?.symbol || "—"}</strong>
        <p>{reason}</p>
      </div>
      <div className="dashboard-list-meta">
        <StatusBadge label={action} tone={signalTone(action)} dot={false} />
        <span>{confidence > 0 ? `${confidence.toFixed(0)}% | ${riskLabel}` : compactDate(item?.created_at)}</span>
      </div>
    </button>
  );
}

function PositionRow({ item, onNavigate }) {
  const pnl = Number(item?.unrealized_pnl ?? 0);
  return (
    <button className="dashboard-list-item dashboard-list-item--interactive" type="button" onClick={() => onNavigate(`/execution?symbol=${encodeURIComponent(item?.symbol || "")}`)}>
      <div className="dashboard-list-copy">
        <strong>{item?.symbol || "—"}</strong>
        <p>{`${item?.side || "LONG"} · ${item?.quantity || 0} أسهم`}</p>
      </div>
      <div className="dashboard-list-meta">
        <span>{money(item?.current_price || item?.avg_entry_price || 0)}</span>
        <small className={pnl >= 0 ? "quote-positive" : "quote-negative"}>{money(pnl)}</small>
      </div>
    </button>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data: dashboardLite, loading, error } = useAppData("dashboardLite");
  const { data: pipelineLive, loading: pipelineLoading, error: pipelineError } = useAppData("pipelineLive");

  const market = dashboardLite?.market_overview || {};
  const portfolioSnapshot = dashboardLite?.portfolio_snapshot || {};
  const ai = dashboardLite?.ai_status || {};
  const news = dashboardLite?.news || {};
  const opportunitiesPayload = dashboardLite?.opportunities || {};
  const productScope = dashboardLite?.product_scope || {};
  const autoTrading = dashboardLite?.auto_trading || {};

  const summary = portfolioSnapshot?.summary || {};
  const indices = Array.isArray(market?.indices) ? market.indices : [];
  const featured = Array.isArray(market?.featured) ? market.featured : [];
  const topPerformers = Array.isArray(market?.top_performers) && market.top_performers.length
    ? market.top_performers
    : featured
        .filter((item) => !["SPY", "QQQ", "DIA"].includes(String(item?.symbol || "").toUpperCase()))
        .sort((left, right) => Number(right?.change_pct ?? 0) - Number(left?.change_pct ?? 0))
        .slice(0, 5)
        .map((item, index) => ({ ...item, rank: item?.rank || index + 1 }));
  const positions = Array.isArray(portfolioSnapshot?.positions) ? portfolioSnapshot.positions : [];
  const trades = Array.isArray(portfolioSnapshot?.trades) ? portfolioSnapshot.trades : [];
  const opportunityItems = Array.isArray(opportunitiesPayload?.items) ? opportunitiesPayload.items : [];
  const newsItems = Array.isArray(news?.items) ? news.items : [];
  const pipelineEvents = Array.isArray(pipelineLive?.events) ? pipelineLive.events.slice(0, 12) : [];
  const pipelineActiveCycles = Array.isArray(pipelineLive?.active_cycles) ? pipelineLive.active_cycles : [];
  const pipelineStats = pipelineLive?.stats || {};

  const usingBrokerData = String(portfolioSnapshot?.active_source || "").startsWith("broker");
  const sourceLabel = portfolioSnapshot?.source_label || (usingBrokerData ? "Broker Paper" : "Internal Simulated Paper");
  const sourceDescription = usingBrokerData
    ? "يتم الآن عرض الرصيد والمراكز من حساب الوسيط الورقي المتصل مع بقاء الإشارات صادرة من محرك التحليل الداخلي."
    : "اللوحة الحالية تعتمد على المحاكاة الداخلية بالكامل، من دون مزجها بحساب وسيط خارجي.";

  const totalEquity = summary?.total_equity ?? summary?.portfolio_value ?? Number(summary?.cash_balance ?? 0) + Number(summary?.total_market_value ?? 0);
  const aiReady = ai?.effective_status || ai?.status || "checking";
  const aiProvider = ai?.effective_provider || ai?.active_provider || "unavailable";
  const autoTradingLabel = autoTrading?.auto_trading_enabled ? (autoTrading?.ready ? "نشط وجاهز" : "مفعل") : "معطل";
  const openPositions = Number(summary?.open_positions ?? positions.length ?? 0);
  const totalTrades = Number(summary?.total_trades ?? trades.length ?? 0);

  return (
    <PageFrame
      title="لوحة القيادة"
      description="لوحة تشغيل مركزة تُبرز السوق، المحفظة، الإشارات، وأفضل الفرص فقط."
      eyebrow="Live Summary"
      headerActions={
        <>
          <StatusBadge label={sourceLabel} tone={sourceTone(usingBrokerData)} />
          <StatusBadge label={aiReady} tone={statusTone(aiReady)} />
        </>
      }
    >
      <ErrorBanner message={error} />

      <section className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <span className="dashboard-hero-kicker">Research And Trading Workspace</span>
          <h2>واجهة تشغيل احترافية تضع أهم ما يهمك في أول الشاشة</h2>
          <p>
            السوق، أفضل الفرص، المخاطر، والأخبار في تسلسل واحد. ما لا يخدم القرار الفوري لم يعد ظاهرًا هنا.
          </p>
          <div className="dashboard-action-strip">
            <button className="btn btn-primary" type="button" onClick={() => navigate("/ai-market")}>
              افتح محطة التحليل
            </button>
            <button className="btn btn-secondary" type="button" onClick={() => navigate("/live-market")}>
              راقب السوق المباشر
            </button>
            <button className="btn btn-ghost" type="button" onClick={() => navigate("/ai-news")}>
              افتح غرفة الأخبار
            </button>
          </div>
        </div>

        <div className="dashboard-hero-status">
          <div className="dashboard-hero-pulse">
            <div className="dashboard-hero-pulse-top">
              <span>حالة النظام</span>
              <StatusBadge label={aiProvider} tone={statusTone(aiReady)} dot={false} />
            </div>
            <div className="dashboard-hero-pulse-value">{aiReady === "ready" ? "Operational" : "Monitoring"}</div>
            <p>المزود الحالي: {aiProvider}</p>
          </div>
          <div className="dashboard-hero-pulse">
            <div className="dashboard-hero-pulse-top">
              <span>التداول التلقائي</span>
              <StatusBadge label={autoTradingLabel} tone={statusTone(autoTrading?.ready ? "ready" : autoTrading?.auto_trading_enabled ? "warning" : "disabled")} dot={false} />
            </div>
            <div className="dashboard-hero-pulse-value">{autoTrading?.ready ? "Ready" : "Standby"}</div>
            <p>{autoTrading?.ready ? "الدورة جاهزة لمسح الكون المحدود" : "الدورة تعمل بموارد مقيدة ومراقبة"}</p>
          </div>
        </div>
      </section>

      {loading ? (
        <LoadingSkeleton lines={6} />
      ) : (
        <>
          <SummaryStrip
            items={[
              { label: "إجمالي رصيد المحفظة", value: money(totalEquity), detail: "القيمة الكلية الحالية", tone: "accent" },
              { label: "الرصيد النقدي", value: money(summary?.cash_balance ?? 0), detail: "سيولة متاحة", tone: "info" },
              { label: "القيمة السوقية", value: money(summary?.total_market_value ?? 0), detail: `${openPositions} مركز مفتوح`, tone: "warning" },
              {
                label: "P&L غير محققة",
                value: money(summary?.total_unrealized_pnl ?? 0),
                detail: "المكاسب/الخسائر الحالية",
                tone: Number(summary?.total_unrealized_pnl ?? 0) >= 0 ? "positive" : "negative",
              },
              {
                label: "P&L محققة",
                value: money(summary?.total_realized_pnl ?? 0),
                detail: `${totalTrades} صفقة`,
                tone: Number(summary?.total_realized_pnl ?? 0) >= 0 ? "positive" : "negative",
              },
              {
                label: "أفضل الفرص",
                value: opportunityItems.length,
                detail: `${productScope?.analysis_lookback_days || 30} يومًا · ${productScope?.tracked_symbols_limit || 8} رموز`,
                tone: "accent",
              },
            ]}
          />

          <div className="command-grid dashboard-grid">
            <SectionCard
              className="col-span-12"
              title="مراقبة التشغيل الحي"
              description="سجل نصي مباشر لمراحل النظام: جلب البيانات، الأخبار، التحليل، الإشارات، والأتمتة."
              action={(
                <StatusBadge
                  label={pipelineActiveCycles.length ? `${pipelineActiveCycles.length} دورة تعمل` : "Standby"}
                  tone={pipelineActiveCycles.length ? "accent" : "subtle"}
                  dot={false}
                />
              )}
            >
              {pipelineLoading ? (
                <LoadingSkeleton lines={4} />
              ) : (
                <>
                  <SummaryStrip
                    compact
                    items={[
                      { label: "الدورات النشطة", value: pipelineActiveCycles.length },
                      { label: "إجمالي الدورات", value: Number(pipelineStats?.total_cycles ?? 0) },
                      { label: "مكتملة", value: Number(pipelineStats?.completed_cycles ?? 0) },
                      { label: "فاشلة", value: Number(pipelineStats?.failed_cycles ?? 0) },
                    ]}
                  />
                  {pipelineActiveCycles.length ? (
                    <div className="dashboard-feed-list">
                      {pipelineActiveCycles.slice(0, 4).map((cycle) => (
                        <div className="dashboard-feed-item" key={cycle.id}>
                          <div className="dashboard-feed-copy">
                            <strong>{cycle.component || "pipeline"} · {cycle.stage || "running"}</strong>
                            <p>
                              {cycle.symbol_count ? `symbols ${cycle.processed_count ?? 0}/${cycle.symbol_count}` : "general cycle"}
                              {cycle.failed_count ? ` · failed ${cycle.failed_count}` : ""}
                            </p>
                          </div>
                          <StatusBadge label={formatElapsed(cycle.elapsed_seconds)} tone="info" dot={false} />
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {pipelineEvents.length ? (
                    <div className="dashboard-feed-list">
                      {pipelineEvents.map((event) => (
                        <div className="dashboard-feed-item" key={event.id}>
                          <div className="dashboard-feed-copy">
                            <strong>{event.message || "pipeline update"}</strong>
                            <p>
                              {event.component || "pipeline"} · {event.stage || "update"}
                              {event.symbol ? ` · ${event.symbol}` : ""}
                            </p>
                          </div>
                          <StatusBadge label={compactDate(event.at)} tone={eventTone(event.level, event.stage)} dot={false} />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState title="لا يوجد سجل حي بعد" description={pipelineError || "سيظهر هنا تسلسل التشغيل النصي عند بدء دورة التحليل."} />
                  )}
                </>
              )}
            </SectionCard>

            <SectionCard
              className="col-span-7"
              title="لوحة السوق"
              description="المؤشرات الرئيسية والرموز المميزة الحالية للوصول السريع إلى أكثر ما يتحرك الآن."
              action={<StatusBadge label={`${indices.length} مؤشرات`} tone="subtle" dot={false} />}
            >
              <div className="dashboard-market-grid">
                {indices.length ? (
                  indices.map((item) => <IndexCard key={item.symbol} item={item} onInspect={(symbol) => navigate(`/live-market?symbol=${encodeURIComponent(symbol || "")}`)} />)
                ) : (
                  <EmptyState title="لا توجد بيانات مؤشرات" description="سيتحدث هذا القسم تلقائيًا عند توفر لقطات السوق." />
                )}
              </div>
              <div className="dashboard-subsection">
                <div className="dashboard-subsection-head">
                  <strong>الرموز المميزة</strong>
                  <span>انتقال سريع إلى التحليل</span>
                </div>
                <div className="dashboard-list">
                  {featured.length ? (
                    featured.slice(0, 6).map((item) => <FeaturedTicker key={item.symbol} item={item} onNavigate={navigate} />)
                  ) : (
                    <EmptyState title="لا توجد رموز مميزة" description="سيظهر هذا القسم عند توفر السوق المميز من الباك إند." />
                  )}
                </div>
              </div>

              <div className="dashboard-subsection">
                <div className="dashboard-subsection-head">
                  <strong>أفضل الأسهم صعودًا %</strong>
                  <span>بحسب التغير اليومي بالنسبة المئوية داخل القائمة المتابعة</span>
                </div>
                <div className="dashboard-list">
                  {topPerformers.length ? (
                    topPerformers.map((item) => <PerformerRow key={`performer-${item.symbol}`} item={item} onNavigate={navigate} />)
                  ) : (
                    <EmptyState title="لا توجد أسهم متصدرة الآن" description="سيظهر هنا أفضل أداء من الأسهم القيادية عند توفر لقطات السوق الحالية." />
                  )}
                </div>
              </div>
            </SectionCard>

            <SectionCard
              className="col-span-5"
              title="المحفظة والمخاطر"
              description="لقطة المحفظة الحالية مع التركيز على الرصيد، التعرض، والمراكز المؤثرة على القرار."
              action={<StatusBadge label={sourceLabel} tone={sourceTone(usingBrokerData)} dot={false} />}
            >
              <div className="dashboard-source-card" data-testid="dashboard-source-badge">
                <strong>مصدر بيانات التنفيذ</strong>
                <p>{sourceDescription}</p>
              </div>

              <div className="dashboard-mini-metrics">
                <MetricCard label="المراكز المفتوحة" value={openPositions} detail="نشطة الآن" />
                <MetricCard label="الصفقات" value={totalTrades} detail="سجل التنفيذ" />
                <MetricCard label="الفوز %" value={summary?.win_rate_pct != null ? `${Number(summary.win_rate_pct).toFixed(1)}%` : "—"} detail="منفصل عن الإشارة" />
                <MetricCard label="التعرض السوقي" value={money(summary?.total_market_value ?? 0)} detail="Market exposure" />
              </div>

              <div className="dashboard-subsection">
                <div className="dashboard-subsection-head">
                  <strong>المراكز الحالية</strong>
                  <button className="secondary-button" type="button" onClick={() => navigate("/execution")}>
                    افتح التداول الورقي
                  </button>
                </div>
                <div className="dashboard-list">
                  {positions.length ? (
                    positions.slice(0, 4).map((item, index) => <PositionRow key={`${item.symbol || "position"}-${index}`} item={item} onNavigate={navigate} />)
                  ) : (
                    <EmptyState title="لا توجد مراكز مفتوحة" description="سيتحدث هذا القسم تلقائيًا عند وجود مراكز أو ربط حساب ورقي." />
                  )}
                </div>
              </div>
            </SectionCard>

            <SectionCard
              className="col-span-6"
              title="غرفة الأخبار"
              description="آخر الأخبار المجمعة من المصدر الحالي مع إظهار الرمز المرتبط والمشاعر إن توفرت."
              action={<StatusBadge label={newsItems.length ? `${newsItems.length} خبر` : "فارغة"} tone={newsItems.length ? "accent" : "subtle"} dot={false} />}
            >
              {newsItems.length ? (
                <div className="news-card-grid">
                  {newsItems.map((item) => <NewsCard key={item.id} item={item} onNavigate={navigate} />)}
                </div>
              ) : (
                <EmptyState
                  title="لا توجد أخبار محفوظة اليوم"
                  description="الواجهة جاهزة، لكن المصدر الحالي لم يسجّل أخبارًا حتى الآن. عند امتلاء feed ستظهر هنا مباشرة."
                  action={
                    <button className="btn btn-secondary btn-sm" type="button" onClick={() => navigate("/ai-news")}>
                      افتح صفحة الأخبار
                    </button>
                  }
                />
              )}
            </SectionCard>

            <SectionCard
              className="col-span-6"
              title="أفضل الفرص الآن"
              description="ترتيب مركّز لأعلى الفرص من الكون الصغير النشط، مع ثقة وسبب مختصر وانتقال مباشر إلى القرار."
              action={<StatusBadge label={opportunityItems.length ? `${opportunityItems.length} فرصة` : "بدون"} tone={opportunityItems.length ? "positive" : "subtle"} dot={false} />}
            >
              <div className="dashboard-list">
                {opportunityItems.length ? (
                  opportunityItems.map((item, index) => <OpportunityRow key={`${item.symbol || "opportunity"}-${index}`} item={item} onNavigate={navigate} />)
                ) : (
                  <EmptyState title="لا توجد فرص مرتبة بعد" description="حدّث الإشارات أو افتح محطة التحليل لإنتاج فرص جديدة من الكون النشط." />
                )}
              </div>
            </SectionCard>
          </div>
        </>
      )}
    </PageFrame>
  );
}
