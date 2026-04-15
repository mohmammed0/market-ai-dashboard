import { useAppData } from "../store/AppDataStore";
import { useNavigate } from "react-router-dom";
import { buildBrokerPortfolioSnapshot } from "../lib/brokerPortfolio";

function pct(v) { const n = Number(v ?? 0); return (n >= 0 ? "+" : "") + n.toFixed(2) + "%"; }
function money(v) { return Number(v ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

/* ── Strategy recommendation based on portfolio value ── */
function getStrategyRecommendation(portfolioValue) {
  const v = Number(portfolioValue || 0);
  if (v <= 0) return {
    level: "inactive",
    title: "لا يوجد رأس مال",
    desc: "اضف مبلغ للمحفظة التجريبية لبدء التداول",
    color: "#555a6b",
    bg: "rgba(85,90,107,0.1)",
    maxPositions: 0,
    riskPerTrade: "0%",
    strategy: "—",
  };
  if (v < 10000) return {
    level: "conservative",
    title: "استراتيجية محافظة",
    desc: "مبلغ صغير — التركيز على الأسهم القيادية والصناديق (ETFs) فقط مع حد أقصى 5 مراكز",
    color: "#2196F3",
    bg: "rgba(33,150,243,0.1)",
    maxPositions: 5,
    riskPerTrade: "2%",
    strategy: "Blue Chips + ETFs",
  };
  if (v < 50000) return {
    level: "moderate",
    title: "استراتيجية متوازنة",
    desc: "تنويع معتدل — 10-15 مركز، مزيج من النمو والقيمة مع وقف خسارة 5%",
    color: "#FF9800",
    bg: "rgba(255,152,0,0.1)",
    maxPositions: 15,
    riskPerTrade: "3%",
    strategy: "Growth + Value Mix",
  };
  if (v < 100000) return {
    level: "growth",
    title: "استراتيجية نمو",
    desc: "محفظة كبيرة — 15-25 مركز، تداول عدواني مسموح مع تنويع قطاعي",
    color: "#089981",
    bg: "rgba(8,153,129,0.1)",
    maxPositions: 25,
    riskPerTrade: "5%",
    strategy: "Aggressive Growth",
  };
  return {
    level: "full",
    title: "تنويع كامل",
    desc: "محفظة مؤسسية — كل الاستراتيجيات مفعلة، 25+ مركز، تداول آلي كامل",
    color: "#9C27B0",
    bg: "rgba(156,39,176,0.1)",
    maxPositions: 40,
    riskPerTrade: "10%",
    strategy: "Full Diversification",
  };
}

function StatCard({ label, value, sub, subTone, icon, accent }) {
  const subColor = subTone === "pos" ? "var(--tv-positive)" : subTone === "neg" ? "var(--tv-negative)" : "var(--tv-text-muted)";
  return (
    <div className="tv-card" style={{ display: "flex", flexDirection: "column", gap: 6, borderTop: accent ? `2px solid ${accent}` : undefined }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11, color: "var(--tv-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</span>
        {icon && <span style={{ width: 18, height: 18, color: accent || "var(--tv-text-muted)" }}>{icon}</span>}
      </div>
      <span style={{ fontSize: 22, fontWeight: 700, color: "var(--tv-text)", fontVariantNumeric: "tabular-nums" }}>{value}</span>
      {sub && <span style={{ fontSize: 12, color: subColor }}>{sub}</span>}
    </div>
  );
}

function StatusDot({ ok, label }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: ok ? "#089981" : "#555a6b", flexShrink: 0 }} />
      <span style={{ fontSize: 12, color: "var(--tv-text-muted)" }}>{label}</span>
    </div>
  );
}

function IndexRow({ item }) {
  const chg = Number(item.change_pct ?? 0);
  return (
    <tr>
      <td style={{ color: "var(--tv-text)", fontWeight: 600 }}>{item.symbol}</td>
      <td style={{ color: "var(--tv-text)", fontVariantNumeric: "tabular-nums" }}>{Number(item.price ?? 0).toFixed(2)}</td>
      <td style={{ color: chg >= 0 ? "var(--tv-positive)" : "var(--tv-negative)", fontVariantNumeric: "tabular-nums" }}>{pct(chg)}</td>
    </tr>
  );
}

function NewsRow({ item }) {
  const s = String(item.sentiment || "").toLowerCase();
  const dot = (s === "bullish" || s === "positive") ? "#089981" : (s === "bearish" || s === "negative") ? "#f23645" : "#555a6b";
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 0", borderBottom: "1px solid var(--tv-border)" }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: dot, flexShrink: 0, marginTop: 5 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ margin: 0, fontSize: 13, color: "var(--tv-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "none" }}>{item.title}</a> : item.title}
        </p>
        <p style={{ margin: "2px 0 0", fontSize: 11, color: "var(--tv-text-muted)" }}>{item.instrument} · {item.source}</p>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data: market, loading: mktLoading }    = useAppData("marketOverview");
  const { data: portfolio }                      = useAppData("paperPortfolio");
  const { data: broker }                         = useAppData("brokerStatus");
  const { data: brokerSummary }                  = useAppData("brokerSummary");
  const { data: ai }                             = useAppData("aiStatus");
  const { data: news }                           = useAppData("newsFeed");
  const { data: signals }                        = useAppData("paperSignals");
  const { data: autoTrading }                    = useAppData("autoTrading");
  const { data: automationStatus }               = useAppData("automationStatus");
  const { data: telegramStatus }                 = useAppData("telegramStatus");
  const { data: trades }                         = useAppData("paperTrades");
  const brokerSnapshot = buildBrokerPortfolioSnapshot(brokerSummary);
  const brokerDataConnected = Boolean(broker?.connected || brokerSummary?.connected);
  const usingBrokerData = Boolean(brokerDataConnected && brokerSnapshot);
  const portfolioSummary = usingBrokerData ? brokerSnapshot.summary : portfolio?.summary || {};

  const indices    = market?.indices ?? [];
  const newsItems  = (news?.items ?? []).slice(0, 8);
  const pnl        = portfolioSummary?.total_unrealized_pnl ?? 0;
  const mv         = portfolioSummary?.total_market_value   ?? 0;
  const positions  = portfolioSummary?.open_positions       ?? 0;
  const cashBalance = portfolioSummary?.cash_balance        ?? 0;
  const invested   = portfolioSummary?.invested_cost        ?? 0;
  const startingCash = portfolioSummary?.starting_cash      ?? 0;
  // Total equity = cash + positions market value (this is the real "wallet balance")
  const portfolioValue = portfolioSummary?.total_equity ?? portfolioSummary?.portfolio_value ?? (cashBalance + mv);
  const realizedPnl = portfolioSummary?.total_realized_pnl  ?? 0;
  const tradesList = usingBrokerData
    ? brokerSnapshot?.trades || []
    : trades?.trades ?? trades?.items ?? (Array.isArray(trades) ? trades : []);
  const winRate = usingBrokerData ? null : portfolioSummary?.win_rate_pct ?? 0;
  const totalTrades = usingBrokerData ? tradesList.length : portfolioSummary?.total_trades ?? 0;
  const signalList = (signals?.items ?? signals ?? []).slice(0, 8);

  // Strategy recommendation
  const strategy = getStrategyRecommendation(portfolioValue);

  // Auto-trading info
  const atEnabled = autoTrading?.auto_trading_enabled;
  const atReady   = autoTrading?.ready;
  const brokerConnected = brokerDataConnected || autoTrading?.alpaca_configured;

  // Positions with trailing stops
  const positionsList = usingBrokerData ? brokerSnapshot?.positions || [] : portfolio?.items ?? portfolio?.positions ?? [];
  const trailingStopCount = positionsList.filter(p => p.trailing_stop_price || p.trailing_stop_pct).length;

  // Automation recent jobs
  const recentJobs = automationStatus?.recent_jobs ?? automationStatus?.jobs ?? [];
  const lastAutoRun = recentJobs.find(j => j.type === "auto_trading_cycle" || j.type === "market_analysis");

  // Trades
  const recentTrades = tradesList.slice(0, 6);

  return (
    <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 20 }}>

      {/* ── Row 1: Key Stats ── */}
      <div className="tv-card-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <StatCard
          label="إجمالي رصيد المحفظة"
          value={"$" + money(portfolioValue)}
          sub={`نقد + استثمارات (بداية: $${money(startingCash)})`}
          subTone="pos"
          accent={strategy.color}
        />
        <StatCard
          label="الرصيد النقدي"
          value={"$" + money(cashBalance)}
          sub={cashBalance > 0 ? "متاح للتداول" : "كل النقد مستثمر"}
          subTone={cashBalance > 0 ? "pos" : "neutral"}
          accent="#2196F3"
        />
        <StatCard
          label="القيمة السوقية للمراكز"
          value={"$" + money(mv)}
          sub={positions === 0 ? "لا مراكز نشطة" : `${positions} مركز · تكلفة $${money(invested)}`}
          subTone="neutral"
          accent="#FF9800"
        />
        <StatCard
          label="P&L غير محققة"
          value={"$" + money(pnl)}
          subTone={pnl >= 0 ? "pos" : "neg"}
          sub={pnl >= 0 ? "ربح" : "خسارة"}
          accent={pnl >= 0 ? "#089981" : "#f23645"}
        />
        <StatCard
          label="P&L محققة"
          value={"$" + money(realizedPnl)}
          subTone={realizedPnl >= 0 ? "pos" : "neg"}
          sub={totalTrades > 0 ? `${totalTrades} صفقة` : "—"}
          accent={realizedPnl >= 0 ? "#089981" : "#f23645"}
        />
        <StatCard
          label="نسبة النجاح"
          value={winRate > 0 ? Number(winRate).toFixed(1) + "%" : "—"}
          sub={totalTrades > 0 ? `من ${totalTrades} صفقة` : "لا صفقات بعد"}
          subTone="neutral"
        />
      </div>

      {/* ── Row 2: Strategy + System Status ── */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>

        {/* Strategy Recommendation */}
        <div className="tv-card" style={{ borderRight: `3px solid ${strategy.color}` }}>
          <p className="tv-section-title" style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={strategy.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
            الاستراتيجية المقترحة
          </p>
          <div style={{ background: strategy.bg, borderRadius: 8, padding: 16, marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span style={{ fontSize: 18, fontWeight: 700, color: strategy.color }}>{strategy.title}</span>
              <span style={{ fontSize: 12, background: strategy.color, color: "#fff", padding: "2px 10px", borderRadius: 12, fontWeight: 600 }}>
                ${money(portfolioValue)}
              </span>
            </div>
            <p style={{ margin: 0, fontSize: 13, color: "var(--tv-text)", lineHeight: 1.6 }}>{strategy.desc}</p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <div style={{ textAlign: "center", padding: 10, background: "var(--tv-bg-secondary, rgba(255,255,255,0.03))", borderRadius: 8 }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: strategy.color }}>{strategy.maxPositions}</div>
              <div style={{ fontSize: 11, color: "var(--tv-text-muted)" }}>اقصى مراكز</div>
            </div>
            <div style={{ textAlign: "center", padding: 10, background: "var(--tv-bg-secondary, rgba(255,255,255,0.03))", borderRadius: 8 }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: strategy.color }}>{strategy.riskPerTrade}</div>
              <div style={{ fontSize: 11, color: "var(--tv-text-muted)" }}>مخاطرة/صفقة</div>
            </div>
            <div style={{ textAlign: "center", padding: 10, background: "var(--tv-bg-secondary, rgba(255,255,255,0.03))", borderRadius: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: strategy.color }}>{strategy.strategy}</div>
              <div style={{ fontSize: 11, color: "var(--tv-text-muted)" }}>نوع الاستراتيجية</div>
            </div>
          </div>
        </div>

        {/* System Status Panel */}
        <div className="tv-card">
          <p className="tv-section-title" style={{ marginBottom: 12 }}>حالة النظام</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <StatusDot ok={ai?.effective_status === "ready" || ai?.status === "running"} label={`الذكاء الاصطناعي — ${ai?.ollama?.model || ai?.effective_status || "..."}`} />
            <StatusDot ok={brokerConnected} label={`الوسيط — ${broker?.provider || "غير متصل"} ${broker?.mode === "paper" ? "(ورقي)" : ""}`} />
            <StatusDot ok={atEnabled && atReady} label={`التداول التلقائي — ${atEnabled ? (atReady ? "جاهز" : "غير مكتمل") : "معطل"}`} />
            <StatusDot ok={telegramStatus?.configured} label={`تيليجرام — ${telegramStatus?.configured ? "متصل" : "غير مفعل"}`} />
            <StatusDot ok={trailingStopCount > 0} label={`وقف الخسارة المتحرك — ${trailingStopCount > 0 ? `${trailingStopCount} مركز محمي` : "لا مراكز"}`} />

            <div style={{ borderTop: "1px solid var(--tv-border)", paddingTop: 8, marginTop: 4 }}>
              <div style={{ fontSize: 11, color: "var(--tv-text-muted)", marginBottom: 4 }}>اخر دورة تحليل</div>
              <div style={{ fontSize: 13, color: "var(--tv-text)" }}>
                {lastAutoRun?.created_at
                  ? new Date(lastAutoRun.created_at).toLocaleString("ar-SA", { hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" })
                  : "لم تبدأ بعد"
                }
              </div>
            </div>

            <button
              className="tv-btn-link"
              style={{ fontSize: 12, color: "var(--tv-accent)", cursor: "pointer", background: "none", border: "none", textAlign: "start", padding: 0, marginTop: 4 }}
              onClick={() => navigate("/settings")}
            >
              اعدادات النظام &larr;
            </button>
          </div>
        </div>
      </div>

      {/* ── Row 3: Auto-Trading Banner (if active) ── */}
      {atEnabled && (
        <div className="tv-card" style={{ background: atReady ? "rgba(8,153,129,0.08)" : "rgba(255,152,0,0.08)", borderRight: `3px solid ${atReady ? "#089981" : "#FF9800"}` }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: atReady ? "#089981" : "#FF9800", animation: atReady ? "pulse 2s infinite" : "none" }} />
              <div>
                <span style={{ fontSize: 14, fontWeight: 700, color: "var(--tv-text)" }}>
                  التداول التلقائي {atReady ? "نشط" : "مفعل (غير مكتمل)"}
                </span>
                <p style={{ margin: "2px 0 0", fontSize: 12, color: "var(--tv-text-muted)" }}>
                  {atReady
                    ? "النظام يحلل السوق كل 30 دقيقة وينفذ اوامر تلقائيا"
                    : "اضف مفاتيح Alpaca في الاعدادات لتفعيل التنفيذ التلقائي"
                  }
                </p>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {autoTrading?.order_submission_enabled && (
                <span style={{ fontSize: 11, background: "rgba(8,153,129,0.2)", color: "#089981", padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>
                  ارسال الاوامر مفعل
                </span>
              )}
              {autoTrading?.alpaca_paper && (
                <span style={{ fontSize: 11, background: "rgba(33,150,243,0.2)", color: "#2196F3", padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>
                  ورقي
                </span>
              )}
              <button
                style={{ fontSize: 12, color: "var(--tv-accent)", background: "none", border: "1px solid var(--tv-border)", borderRadius: 6, padding: "4px 12px", cursor: "pointer" }}
                onClick={() => navigate("/paper-trading")}
              >
                فتح التداول
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Row 4: Positions with Trailing Stops (if any) ── */}
      {positionsList.length > 0 && (
        <div className="tv-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <p className="tv-section-title" style={{ margin: 0 }}>المراكز المفتوحة</p>
            <button
              style={{ fontSize: 12, color: "var(--tv-accent)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
              onClick={() => navigate("/paper-trading")}
            >
              عرض الكل &larr;
            </button>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="tv-table" style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th>الرمز</th>
                  <th>الجانب</th>
                  <th>الكمية</th>
                  <th>الدخول</th>
                  <th>الحالي</th>
                  <th>P&L</th>
                  <th>وقف الخسارة</th>
                  <th>الوقف المتحرك</th>
                </tr>
              </thead>
              <tbody>
                {positionsList.slice(0, 10).map((p, i) => {
                  const positionPnl = Number(p.unrealized_pnl || 0);
                  const side = String(p.side || "").toUpperCase();
                  const isLong = side === "LONG" || side === "BUY";
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 600, color: "var(--tv-text)" }}>{p.symbol}</td>
                      <td>
                        <span style={{
                          display: "inline-flex", alignItems: "center", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600,
                          background: isLong ? "rgba(8,153,129,0.15)" : "rgba(242,54,69,0.15)",
                          color: isLong ? "var(--tv-positive)" : "var(--tv-negative)"
                        }}>{side}</span>
                      </td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>{p.quantity}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>${Number(p.avg_entry_price || 0).toFixed(2)}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>${Number(p.current_price || 0).toFixed(2)}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums", color: positionPnl >= 0 ? "var(--tv-positive)" : "var(--tv-negative)", fontWeight: 600 }}>
                        ${money(positionPnl)}
                      </td>
                      <td style={{ fontVariantNumeric: "tabular-nums", color: p.stop_loss_price ? "#FF9800" : "var(--tv-text-muted)", fontSize: 12 }}>
                        {p.stop_loss_price ? `$${Number(p.stop_loss_price).toFixed(2)}` : "—"}
                      </td>
                      <td style={{ fontVariantNumeric: "tabular-nums", fontSize: 12 }}>
                        {p.trailing_stop_pct ? (
                          <span style={{ color: "#2196F3" }}>
                            {Number(p.trailing_stop_pct).toFixed(1)}%
                            {p.trailing_stop_price ? ` ($${Number(p.trailing_stop_price).toFixed(2)})` : ""}
                          </span>
                        ) : (
                          <span style={{ color: "var(--tv-text-muted)" }}>—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {positionsList.length > 10 && (
            <div style={{ textAlign: "center", padding: "8px 0", fontSize: 12, color: "var(--tv-text-muted)" }}>
              +{positionsList.length - 10} مراكز اخرى
            </div>
          )}
        </div>
      )}

      {/* ── Row 5: Market + News ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="tv-card">
          <p className="tv-section-title">المؤشرات الرئيسية</p>
          {mktLoading
            ? <div className="tv-skeleton" style={{ height: 120 }} />
            : indices.length === 0
            ? <p style={{ color: "var(--tv-text-muted)", fontSize: 13 }}>لا بيانات</p>
            : <table className="tv-table" style={{ width: "100%" }}>
                <thead><tr><th>المؤشر</th><th>السعر</th><th>التغيير</th></tr></thead>
                <tbody>{indices.map((idx, i) => <IndexRow key={i} item={idx} />)}</tbody>
              </table>
          }
        </div>
        <div className="tv-card">
          <p className="tv-section-title">اخر الاخبار</p>
          {newsItems.length === 0
            ? <p style={{ color: "var(--tv-text-muted)", fontSize: 13 }}>لا اخبار اليوم</p>
            : <div>{newsItems.map((n, i) => <NewsRow key={i} item={n} />)}</div>
          }
        </div>
      </div>

      {/* ── Row 6: Recent Signals + Recent Trades ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Signals */}
        <div className="tv-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <p className="tv-section-title" style={{ margin: 0 }}>اخر الاشارات</p>
            <button
              style={{ fontSize: 12, color: "var(--tv-accent)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
              onClick={() => navigate("/paper-trading")}
            >
              عرض الكل &larr;
            </button>
          </div>
          {signalList.length === 0 ? (
            <p style={{ color: "var(--tv-text-muted)", fontSize: 13 }}>لا اشارات حديثة</p>
          ) : (
            <table className="tv-table" style={{ width: "100%" }}>
              <thead><tr><th>الرمز</th><th>الاشارة</th><th>الثقة</th><th>الوقت</th></tr></thead>
              <tbody>
                {signalList.map((s, i) => {
                  const dir = String(s.signal || s.direction || s.action || "").toUpperCase();
                  const up = dir === "BUY" || dir === "BULLISH" || dir === "LONG" || dir === "OPEN_LONG";
                  const pill = { display:"inline-flex",alignItems:"center",padding:"2px 8px",borderRadius:4,fontSize:11,fontWeight:600,
                    background: up ? "rgba(8,153,129,0.15)" : "rgba(242,54,69,0.15)",
                    color: up ? "var(--tv-positive)" : "var(--tv-negative)" };
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{s.symbol || s.instrument}</td>
                      <td><span style={pill}>{dir || "—"}</span></td>
                      <td style={{ color: "var(--tv-text-muted)" }}>{s.confidence ? Number(s.confidence).toFixed(0) + "%" : "—"}</td>
                      <td style={{ color: "var(--tv-text-muted)", fontSize: 11 }}>{s.created_at ? new Date(s.created_at).toLocaleTimeString("ar-SA",{hour:"2-digit",minute:"2-digit"}) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Recent Trades */}
        <div className="tv-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <p className="tv-section-title" style={{ margin: 0 }}>اخر الصفقات</p>
            <button
              style={{ fontSize: 12, color: "var(--tv-accent)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
              onClick={() => navigate("/trade-journal")}
            >
              سجل الصفقات &larr;
            </button>
          </div>
          {recentTrades.length === 0 ? (
            <p style={{ color: "var(--tv-text-muted)", fontSize: 13 }}>لا صفقات حديثة</p>
          ) : (
            <table className="tv-table" style={{ width: "100%" }}>
              <thead><tr><th>الرمز</th><th>الجانب</th><th>الكمية</th><th>السعر</th><th>P&L</th></tr></thead>
              <tbody>
                {recentTrades.map((t, i) => {
                  const tPnl = Number(t.realized_pnl || 0);
                  const tSide = String(t.side || "").toUpperCase();
                  const isBuy = tSide === "BUY";
                  return (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{t.symbol}</td>
                      <td>
                        <span style={{
                          display: "inline-flex", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600,
                          background: isBuy ? "rgba(8,153,129,0.15)" : "rgba(242,54,69,0.15)",
                          color: isBuy ? "var(--tv-positive)" : "var(--tv-negative)"
                        }}>{tSide || "—"}</span>
                      </td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>{t.quantity}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>${Number(t.price || 0).toFixed(2)}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums", color: tPnl >= 0 ? "var(--tv-positive)" : "var(--tv-negative)", fontWeight: 600 }}>
                        ${money(tPnl)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

    </div>
  );
}
