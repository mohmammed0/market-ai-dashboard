import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getJson, postJson, deleteJson, putJson } from "../api/client";

// ─── Color token map ───────────────────────────────────────────────────────────
const COLOR_MAP = {
  blue: "#3b82f6",
  green: "#22c55e",
  red: "#ef4444",
  yellow: "#eab308",
  purple: "#a855f7",
  orange: "#f97316",
  cyan: "#06b6d4",
  pink: "#ec4899",
  indigo: "#6366f1",
  teal: "#14b8a6",
  default: "#64748b",
};

function resolveColor(token) {
  if (!token) return COLOR_MAP.default;
  if (token.startsWith("#")) return token;
  return COLOR_MAP[token] || COLOR_MAP.default;
}

// ─── Inline style constants ────────────────────────────────────────────────────
const S = {
  page: {
    display: "flex",
    height: "100%",
    minHeight: 0,
    background: "#020617",
    color: "#e2e8f0",
    fontFamily: "'Segoe UI', 'Noto Kufi Arabic', Arial, sans-serif",
    direction: "rtl",
    overflow: "hidden",
  },
  sidebar: {
    width: 300,
    minWidth: 280,
    background: "#0f172a",
    borderLeft: "1px solid #1e293b",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  sidebarHeader: {
    padding: "16px 16px 12px",
    borderBottom: "1px solid #1e293b",
    display: "flex",
    alignItems: "center",
    gap: 8,
    justifyContent: "space-between",
  },
  sidebarTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "#f1f5f9",
    margin: 0,
  },
  mainPanel: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    background: "#020617",
  },
  panelHeader: {
    padding: "16px 20px",
    borderBottom: "1px solid #1e293b",
    background: "#0f172a",
    display: "flex",
    alignItems: "center",
    gap: 12,
    justifyContent: "space-between",
  },
  card: {
    background: "#0f172a",
    border: "1px solid #1e293b",
    borderRadius: 8,
    padding: 16,
    marginBottom: 12,
  },
  btn: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 12px",
    borderRadius: 6,
    border: "1px solid #334155",
    background: "#1e293b",
    color: "#94a3b8",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 500,
    transition: "all 0.15s",
  },
  btnPrimary: {
    background: "#3b82f6",
    border: "1px solid #2563eb",
    color: "#fff",
  },
  btnDanger: {
    background: "transparent",
    border: "none",
    color: "#64748b",
    cursor: "pointer",
    padding: "2px 6px",
    borderRadius: 4,
    fontSize: 14,
    lineHeight: 1,
    transition: "color 0.15s",
  },
  input: {
    background: "#1e293b",
    border: "1px solid #334155",
    borderRadius: 6,
    color: "#f1f5f9",
    padding: "7px 10px",
    fontSize: 13,
    outline: "none",
    width: "100%",
    boxSizing: "border-box",
    direction: "ltr",
  },
  badge: {
    fontSize: 10,
    padding: "2px 6px",
    borderRadius: 10,
    background: "#1e293b",
    color: "#64748b",
    fontWeight: 600,
  },
};

// ─── Small helper components ───────────────────────────────────────────────────
function Spinner() {
  return (
    <span style={{ display: "inline-block", width: 14, height: 14, border: "2px solid #334155", borderTopColor: "#3b82f6", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
  );
}

function PriceChange({ change, changePct }) {
  const positive = change >= 0;
  const color = positive ? "#22c55e" : "#ef4444";
  const sign = positive ? "+" : "";
  return (
    <span style={{ color, fontSize: 12, fontWeight: 600 }}>
      {sign}{changePct?.toFixed(2)}% ({sign}{change?.toFixed(2)})
    </span>
  );
}

// ─── Modal ─────────────────────────────────────────────────────────────────────
function Modal({ open, title, onClose, children }) {
  if (!open) return null;
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.7)" }}
      onClick={onClose}>
      <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10, padding: 24, minWidth: 340, maxWidth: 440, width: "90%", boxShadow: "0 25px 60px rgba(0,0,0,0.6)" }}
        onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#f1f5f9" }}>{title}</h3>
          <button onClick={onClose} style={{ ...S.btnDanger, color: "#94a3b8", fontSize: 18 }}>×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ─── Watchlist tab button ──────────────────────────────────────────────────────
function WatchlistTab({ list, isActive, onClick, onDelete }) {
  const color = resolveColor(list.color_token);
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 8, padding: "9px 12px",
        cursor: "pointer", borderRadius: 6, marginBottom: 2,
        background: isActive ? "#1e293b" : "transparent",
        border: isActive ? `1px solid ${color}40` : "1px solid transparent",
        transition: "all 0.15s",
      }}
      onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = "#0f172a"; }}
      onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
    >
      <div style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
      <span style={{ flex: 1, fontSize: 13, fontWeight: isActive ? 600 : 400, color: isActive ? "#f1f5f9" : "#94a3b8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {list.name}
        {list.is_default && <span style={{ marginRight: 4, fontSize: 10, color: color }}>★</span>}
      </span>
      <span style={S.badge}>{list.items?.length || 0}</span>
      <button
        onClick={e => { e.stopPropagation(); onDelete(list); }}
        style={S.btnDanger}
        title="حذف القائمة"
      >×</button>
    </div>
  );
}

// ─── Symbol row ────────────────────────────────────────────────────────────────
function SymbolRow({ item, quote, loading, onRemove, onNavigate }) {
  const q = quote || {};
  const hasQuote = q.price != null;
  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
        borderBottom: "1px solid #1e293b", cursor: "pointer", transition: "background 0.1s",
      }}
      onMouseEnter={e => e.currentTarget.style.background = "#1e293b"}
      onMouseLeave={e => e.currentTarget.style.background = "transparent"}
      onClick={() => onNavigate(item.symbol)}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", direction: "ltr" }}>{item.symbol}</div>
        {item.notes && <div style={{ fontSize: 11, color: "#64748b", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.notes}</div>}
      </div>
      <div style={{ textAlign: "left", direction: "ltr", minWidth: 100 }}>
        {loading ? (
          <Spinner />
        ) : hasQuote ? (
          <>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9" }}>${q.price?.toFixed(2)}</div>
            <PriceChange change={q.change} changePct={q.change_pct} />
          </>
        ) : (
          <span style={{ fontSize: 11, color: "#475569" }}>—</span>
        )}
      </div>
      <button
        onClick={e => { e.stopPropagation(); onRemove(item.symbol); }}
        style={S.btnDanger}
        title="إزالة من القائمة"
        onMouseEnter={e => e.currentTarget.style.color = "#ef4444"}
        onMouseLeave={e => e.currentTarget.style.color = "#64748b"}
      >×</button>
    </div>
  );
}

// ─── Summary panel (right side when no symbol selected) ───────────────────────
function WatchlistSummary({ list, quotes }) {
  if (!list) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#475569", fontSize: 14 }}>
      اختر قائمة متابعة من الشريط الجانبي
    </div>
  );

  const items = list.items || [];
  const gainers = items.filter(it => (quotes[it.symbol]?.change_pct || 0) > 0);
  const losers = items.filter(it => (quotes[it.symbol]?.change_pct || 0) < 0);
  const color = resolveColor(list.color_token);

  return (
    <div style={{ padding: 20, overflowY: "auto", flex: 1 }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <div style={{ width: 12, height: 12, borderRadius: "50%", background: color }} />
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#f1f5f9" }}>{list.name}</h2>
        </div>
        <div style={{ fontSize: 12, color: "#64748b" }}>
          {items.length} رمز · آخر تحديث: {list.updated_at ? new Date(list.updated_at).toLocaleString("ar-SA") : "—"}
        </div>
      </div>

      {/* Stats cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 20 }}>
        {[
          { label: "إجمالي الرموز", value: items.length, color: "#3b82f6" },
          { label: "الرابحون", value: gainers.length, color: "#22c55e" },
          { label: "الخاسرون", value: losers.length, color: "#ef4444" },
        ].map(stat => (
          <div key={stat.label} style={{ ...S.card, marginBottom: 0, textAlign: "center" }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: stat.color }}>{stat.value}</div>
            <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Top movers */}
      {items.length > 0 && (
        <div style={S.card}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#94a3b8", marginBottom: 12 }}>أبرز التحركات</div>
          {[...items]
            .filter(it => quotes[it.symbol]?.change_pct != null)
            .sort((a, b) => Math.abs(quotes[b.symbol]?.change_pct || 0) - Math.abs(quotes[a.symbol]?.change_pct || 0))
            .slice(0, 5)
            .map(it => {
              const q = quotes[it.symbol] || {};
              return (
                <div key={it.symbol} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #1e293b" }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", direction: "ltr" }}>{it.symbol}</span>
                  <div style={{ direction: "ltr", textAlign: "right" }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#e2e8f0" }}>${q.price?.toFixed(2) || "—"}</div>
                    <PriceChange change={q.change} changePct={q.change_pct} />
                  </div>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────────
export default function WatchlistPage() {
  const navigate = useNavigate();

  const [watchlists, setWatchlists] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [quotes, setQuotes] = useState({});
  const [quotesLoading, setQuotesLoading] = useState({});

  // Add symbol state
  const [addSymbol, setAddSymbol] = useState("");
  const [addNotes, setAddNotes] = useState("");
  const [addingSymbol, setAddingSymbol] = useState(false);
  const [addError, setAddError] = useState(null);

  // Create watchlist modal
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColorToken, setNewColorToken] = useState("blue");
  const [creating, setCreating] = useState(false);

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // Initializing
  const [initializing, setInitializing] = useState(false);

  const refreshTimerRef = useRef(null);
  const quoteFetchRef = useRef({});

  // ── Fetch watchlists ──
  const fetchWatchlists = useCallback(async () => {
    try {
      const data = await getJson("/api/workspace/watchlists");
      const items = data?.items || [];
      setWatchlists(items);
      setError(null);
      if (items.length > 0 && !selectedId) {
        const def = items.find(w => w.is_default) || items[0];
        setSelectedId(def.id);
      }
    } catch (err) {
      setError(err.message || "فشل تحميل قوائم المتابعة");
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    fetchWatchlists();
  }, []);

  // ── Selected watchlist ──
  const selectedList = watchlists.find(w => w.id === selectedId) || null;

  // ── Fetch quotes for selected list ──
  const fetchQuotes = useCallback(async (symbols) => {
    if (!symbols || symbols.length === 0) return;
    const toFetch = symbols.filter(s => s);
    setQuotesLoading(prev => {
      const next = { ...prev };
      toFetch.forEach(s => { next[s] = true; });
      return next;
    });
    const results = await Promise.allSettled(
      toFetch.map(sym =>
        getJson(`/api/market/symbol/${sym}/snapshot`, { forceFresh: true })
          .then(data => ({ sym, quote: data?.quote || null }))
          .catch(() => ({ sym, quote: null }))
      )
    );
    const newQuotes = {};
    results.forEach(r => {
      if (r.status === "fulfilled" && r.value) {
        newQuotes[r.value.sym] = r.value.quote;
      }
    });
    setQuotes(prev => ({ ...prev, ...newQuotes }));
    setQuotesLoading(prev => {
      const next = { ...prev };
      toFetch.forEach(s => { next[s] = false; });
      return next;
    });
  }, []);

  useEffect(() => {
    if (!selectedList) return;
    const symbols = (selectedList.items || []).map(it => it.symbol);
    fetchQuotes(symbols);

    // Auto-refresh every 30s
    if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    refreshTimerRef.current = setInterval(() => fetchQuotes(symbols), 30000);
    return () => { if (refreshTimerRef.current) clearInterval(refreshTimerRef.current); };
  }, [selectedId, selectedList?.items?.length]);

  // ── Add symbol ──
  const handleAddSymbol = async () => {
    const sym = addSymbol.trim().toUpperCase();
    if (!sym || !selectedId) return;
    setAddingSymbol(true);
    setAddError(null);
    try {
      await postJson(`/api/workspace/watchlists/${selectedId}/items`, { symbol: sym, notes: addNotes.trim() });
      setAddSymbol("");
      setAddNotes("");
      await fetchWatchlists();
      await fetchQuotes([sym]);
    } catch (err) {
      setAddError(err.message || "فشل إضافة الرمز");
    } finally {
      setAddingSymbol(false);
    }
  };

  // ── Remove symbol ──
  const handleRemoveSymbol = async (symbol) => {
    if (!selectedId) return;
    try {
      await deleteJson(`/api/workspace/watchlists/${selectedId}/items/${symbol}`);
      await fetchWatchlists();
    } catch (err) {
      console.error("Remove symbol error:", err);
    }
  };

  // ── Create watchlist ──
  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const res = await postJson("/api/workspace/watchlists", { name, color_token: newColorToken, category: "custom" });
      setShowCreate(false);
      setNewName("");
      setNewColorToken("blue");
      await fetchWatchlists();
      if (res?.id) setSelectedId(res.id);
    } catch (err) {
      console.error("Create watchlist error:", err);
    } finally {
      setCreating(false);
    }
  };

  // ── Delete watchlist ──
  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteJson(`/api/workspace/watchlists/${deleteTarget.id}`);
      setDeleteTarget(null);
      if (selectedId === deleteTarget.id) setSelectedId(null);
      await fetchWatchlists();
    } catch (err) {
      console.error("Delete watchlist error:", err);
    } finally {
      setDeleting(false);
    }
  };

  // ── Initialize defaults ──
  const handleInitialize = async () => {
    setInitializing(true);
    try {
      await postJson("/api/workspace/initialize", {});
      await fetchWatchlists();
    } catch (err) {
      console.error("Initialize error:", err);
    } finally {
      setInitializing(false);
    }
  };

  // ── Navigate to AI Market ──
  const handleNavigateSymbol = (symbol) => {
    navigate(`/ai-market?symbol=${symbol}`);
  };

  // ── Render ──
  return (
    <div style={S.page}>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #020617; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
      `}</style>

      {/* ── LEFT SIDEBAR ── */}
      <aside style={S.sidebar}>
        {/* Header */}
        <div style={S.sidebarHeader}>
          <h2 style={S.sidebarTitle}>📋 قائمة المتابعة</h2>
          <button
            style={{ ...S.btn, ...S.btnPrimary, padding: "5px 10px", fontSize: 11 }}
            onClick={() => setShowCreate(true)}
            title="إنشاء قائمة جديدة"
          >
            + جديد
          </button>
        </div>

        {/* Watchlist list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "10px 8px" }}>
          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: 24 }}><Spinner /></div>
          ) : error ? (
            <div style={{ padding: 12, color: "#ef4444", fontSize: 13 }}>{error}</div>
          ) : watchlists.length === 0 ? (
            <div style={{ padding: 16, textAlign: "center" }}>
              <div style={{ color: "#475569", fontSize: 13, marginBottom: 12 }}>لا توجد قوائم متابعة بعد</div>
              <button
                style={{ ...S.btn, ...S.btnPrimary, fontSize: 12 }}
                onClick={handleInitialize}
                disabled={initializing}
              >
                {initializing ? <Spinner /> : "🚀 تهيئة القوائم الافتراضية"}
              </button>
            </div>
          ) : (
            watchlists.map(list => (
              <WatchlistTab
                key={list.id}
                list={list}
                isActive={selectedId === list.id}
                onClick={() => setSelectedId(list.id)}
                onDelete={setDeleteTarget}
              />
            ))
          )}
        </div>

        {/* Add symbol input */}
        {selectedList && (
          <div style={{ padding: "12px 12px 16px", borderTop: "1px solid #1e293b", background: "#0a1628" }}>
            <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8, fontWeight: 600, letterSpacing: "0.05em" }}>
              إضافة رمز إلى "{selectedList.name}"
            </div>
            <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
              <input
                style={{ ...S.input, flex: 1 }}
                placeholder="AAPL"
                value={addSymbol}
                onChange={e => setAddSymbol(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === "Enter" && handleAddSymbol()}
                disabled={addingSymbol}
              />
              <button
                style={{ ...S.btn, ...S.btnPrimary, padding: "6px 10px", fontSize: 13 }}
                onClick={handleAddSymbol}
                disabled={addingSymbol || !addSymbol.trim()}
                title="إضافة"
              >
                {addingSymbol ? <Spinner /> : "+"}
              </button>
            </div>
            <input
              style={{ ...S.input, fontSize: 11 }}
              placeholder="ملاحظات (اختياري)"
              value={addNotes}
              onChange={e => setAddNotes(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleAddSymbol()}
              disabled={addingSymbol}
            />
            {addError && <div style={{ color: "#ef4444", fontSize: 11, marginTop: 6 }}>{addError}</div>}
          </div>
        )}
      </aside>

      {/* ── RIGHT MAIN PANEL ── */}
      <div style={S.mainPanel}>
        {/* Panel header */}
        <div style={S.panelHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {selectedList && (
              <>
                <div style={{ width: 10, height: 10, borderRadius: "50%", background: resolveColor(selectedList.color_token) }} />
                <span style={{ fontSize: 16, fontWeight: 700, color: "#f1f5f9" }}>{selectedList.name}</span>
                {selectedList.is_default && (
                  <span style={{ fontSize: 11, background: "#1e3a5f", color: "#60a5fa", padding: "2px 8px", borderRadius: 10 }}>افتراضي</span>
                )}
                <span style={{ ...S.badge, fontSize: 11 }}>{selectedList.items?.length || 0} رمز</span>
              </>
            )}
            {!selectedList && <span style={{ color: "#475569", fontSize: 14 }}>اختر قائمة متابعة</span>}
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {selectedList && (
              <span style={{ fontSize: 11, color: "#475569" }}>
                تحديث تلقائي كل 30 ث
              </span>
            )}
            {watchlists.length === 0 && !loading && (
              <button
                style={{ ...S.btn, fontSize: 11 }}
                onClick={handleInitialize}
                disabled={initializing}
              >
                {initializing ? <Spinner /> : "🚀 تهيئة الافتراضي"}
              </button>
            )}
          </div>
        </div>

        {/* Content area: symbol list + summary */}
        <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>
          {/* Symbol list */}
          {selectedList ? (
            <div style={{ flex: 1, overflowY: "auto", borderLeft: "1px solid #1e293b" }}>
              {selectedList.items?.length === 0 ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: 200, color: "#475569" }}>
                  <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
                  <div style={{ fontSize: 14 }}>القائمة فارغة — أضف رموزاً من الشريط الجانبي</div>
                </div>
              ) : (
                (selectedList.items || [])
                  .slice()
                  .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
                  .map(item => (
                    <SymbolRow
                      key={item.symbol}
                      item={item}
                      quote={quotes[item.symbol]}
                      loading={quotesLoading[item.symbol] === true && quotes[item.symbol] == null}
                      onRemove={handleRemoveSymbol}
                      onNavigate={handleNavigateSymbol}
                    />
                  ))
              )}
            </div>
          ) : (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#475569", fontSize: 14 }}>
              اختر قائمة متابعة من الشريط الجانبي
            </div>
          )}

          {/* Summary panel */}
          <div style={{ width: 280, minWidth: 240, borderLeft: "1px solid #1e293b", overflowY: "auto", background: "#0a1628" }}>
            <WatchlistSummary list={selectedList} quotes={quotes} />
          </div>
        </div>
      </div>

      {/* ── Create Watchlist Modal ── */}
      <Modal open={showCreate} title="إنشاء قائمة متابعة جديدة" onClose={() => { setShowCreate(false); setNewName(""); }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={{ fontSize: 12, color: "#94a3b8", display: "block", marginBottom: 6 }}>اسم القائمة</label>
            <input
              style={S.input}
              placeholder="مثال: التقنية، المفضلة..."
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleCreate()}
              autoFocus
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "#94a3b8", display: "block", marginBottom: 8 }}>اللون</label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {Object.entries(COLOR_MAP).filter(([k]) => k !== "default").map(([token, hex]) => (
                <div
                  key={token}
                  onClick={() => setNewColorToken(token)}
                  style={{
                    width: 28, height: 28, borderRadius: "50%", background: hex, cursor: "pointer",
                    border: newColorToken === token ? "3px solid #f1f5f9" : "2px solid transparent",
                    boxSizing: "border-box", transition: "border 0.15s",
                  }}
                  title={token}
                />
              ))}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
            <button style={S.btn} onClick={() => { setShowCreate(false); setNewName(""); }}>إلغاء</button>
            <button
              style={{ ...S.btn, ...S.btnPrimary }}
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
            >
              {creating ? <Spinner /> : "إنشاء القائمة"}
            </button>
          </div>
        </div>
      </Modal>

      {/* ── Delete Watchlist Confirm Modal ── */}
      <Modal open={!!deleteTarget} title="حذف قائمة المتابعة" onClose={() => setDeleteTarget(null)}>
        <div style={{ fontSize: 14, color: "#94a3b8", marginBottom: 20, lineHeight: 1.6 }}>
          هل أنت متأكد من حذف قائمة <strong style={{ color: "#f1f5f9" }}>"{deleteTarget?.name}"</strong>؟
          <br />سيتم حذف جميع الرموز المضافة إليها بشكل دائم.
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button style={S.btn} onClick={() => setDeleteTarget(null)}>إلغاء</button>
          <button
            style={{ ...S.btn, background: "#7f1d1d", border: "1px solid #991b1b", color: "#fca5a5" }}
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? <Spinner /> : "حذف نهائياً"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
