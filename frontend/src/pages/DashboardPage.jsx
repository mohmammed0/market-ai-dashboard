import { useAppData } from "../store/AppDataStore";

function pct(v) { const n = Number(v ?? 0); return (n >= 0 ? "+" : "") + n.toFixed(2) + "%"; }
function money(v) { return Number(v ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

function StatCard({ label, value, sub, subTone }) {
  const subColor = subTone === "pos" ? "var(--tv-positive)" : subTone === "neg" ? "var(--tv-negative)" : "var(--tv-text-muted)";
  return (
    <div className="tv-card" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span style={{ fontSize: 11, color: "var(--tv-text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</span>
      <span style={{ fontSize: 22, fontWeight: 700, color: "var(--tv-text)", fontVariantNumeric: "tabular-nums" }}>{value}</span>
      {sub && <span style={{ fontSize: 12, color: subColor }}>{sub}</span>}
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
  const { data: market, loading: mktLoading } = useAppData("marketOverview");
  const { data: portfolio }                   = useAppData("paperPortfolio");
  const { data: broker }                      = useAppData("brokerStatus");
  const { data: ai }                          = useAppData("aiStatus");
  const { data: news }                        = useAppData("newsFeed");
  const { data: signals }                     = useAppData("paperSignals");

  const indices    = market?.indices ?? [];
  const newsItems  = (news?.items ?? []).slice(0, 8);
  const pnl        = portfolio?.summary?.total_unrealized_pnl ?? 0;
  const mv         = portfolio?.summary?.total_market_value   ?? 0;
  const positions  = portfolio?.summary?.open_positions       ?? 0;
  const signalList = (signals?.items ?? signals ?? []).slice(0, 5);

  return (
    <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 20 }}>

      <div className="tv-card-grid">
        <StatCard label="المراكز المفتوحة" value={positions}       sub={positions === 0 ? "لا مراكز نشطة" : positions + " مركز"} subTone="neutral" />
        <StatCard label="القيمة السوقية"  value={"$" + money(mv)} sub={mv === 0 ? "—" : null}                                           subTone="neutral" />
        <StatCard label="الربح / الخسارة" value={"$" + money(pnl)} subTone={pnl >= 0 ? "pos" : "neg"}                                      sub={pnl >= 0 ? "▲ ربح غير محقق" : "▼ خسارة"} />
        <StatCard label="الوسيط" value={broker?.mode === "paper" ? "ورقي" : (broker?.provider || "—")} sub={broker?.connected ? "متصل" : "غير متصل"} subTone={broker?.connected ? "pos" : "neutral"} />
        <StatCard label="الذكاء الاصطناعي"  value={ai?.effective_status === "ready" ? "جاهز" : "غير متصل"} sub={ai?.ollama?.model || "—"} subTone={ai?.effective_status === "ready" ? "pos" : "neutral"} />
      </div>

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
          <p className="tv-section-title">آخر الأخبار</p>
          {newsItems.length === 0
            ? <p style={{ color: "var(--tv-text-muted)", fontSize: 13 }}>لا أخبار اليوم</p>
            : <div>{newsItems.map((n, i) => <NewsRow key={i} item={n} />)}</div>
          }
        </div>
      </div>

      {signalList.length > 0 && (
        <div className="tv-card">
          <p className="tv-section-title">آخر الإشارات</p>
          <table className="tv-table" style={{ width: "100%" }}>
            <thead><tr><th>الرمز</th><th>الإشارة</th><th>الثقة</th><th>الوقت</th></tr></thead>
            <tbody>
              {signalList.map((s, i) => {
                const dir = String(s.signal || s.direction || "").toUpperCase();
                const up = dir === "BUY" || dir === "BULLISH" || dir === "LONG";
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
        </div>
      )}

    </div>
  );
}
