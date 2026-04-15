/**
 * MultiChartPage — صفحة متعدد الشارتات (2×2 TradingView grid)
 */
import { useState, useCallback, useRef } from "react";
import TradingViewWidget from "../components/charts/TradingViewWidget";

export function normalizeSymbol(sym) {
  if (!sym) return "NASDAQ:AAPL";
  if (sym.includes(":")) return sym.toUpperCase();
  const s = sym.toUpperCase();
  const AMEX = new Set(["SPY","QQQ","IWM","DIA","GLD","SLV","TLT","HYG","XLF","XLK","XLE","XLV","XLI","XLC","XLB","XLP","XLU","XLRE","VNQ","VTI","VOO","VEA","EEM","ARKK","ARKG","ARKW","ARKF"]);
  if (AMEX.has(s)) return `AMEX:${s}`;
  const CRYPTO = ["BTC","ETH","BNB","SOL","XRP","ADA","DOGE","AVAX","DOT","MATIC"];
  if (CRYPTO.includes(s)) return `BINANCE:${s}USDT`;
  if (/^[A-Z]{6}$/.test(s)) return `FX:${s}`;
  return `NASDAQ:${s}`;
}

const PRESETS = {
  american: { label: "أمريكي", symbols: ["AAPL", "MSFT", "NVDA", "SPY"] },
  tech:     { label: "تقنية",  symbols: ["GOOGL", "META", "AMZN", "TSLA"] },
  etf:      { label: "ETF",    symbols: ["SPY", "QQQ", "IWM", "GLD"] },
};

const INTERVALS = [
  { value: "D",  label: "1د" },
  { value: "W",  label: "1أ" },
  { value: "M",  label: "1ش" },
];

const LAYOUTS = [
  { id: "2x2",  label: "2×2" },
  { id: "1x3",  label: "1+3" },
  { id: "2p1",  label: "2+1" },
];

const DEFAULT_PANELS = [
  { id: 0, symbol: "AAPL", interval: "D" },
  { id: 1, symbol: "MSFT", interval: "D" },
  { id: 2, symbol: "NVDA", interval: "D" },
  { id: 3, symbol: "SPY",  interval: "D" },
];

/* ── styles ── */
const S = {
  page: {
    display: "flex",
    flexDirection: "column",
    height: "calc(100vh - 48px)", // subtract topbar height
    background: "#020617",
    color: "#e2e8f0",
    fontFamily: "inherit",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "6px 12px",
    background: "#0f172a",
    borderBottom: "1px solid #1e293b",
    flexShrink: 0,
    flexWrap: "wrap",
    minHeight: 44,
  },
  headerTitle: {
    fontSize: 15,
    fontWeight: 700,
    color: "#f1f5f9",
    whiteSpace: "nowrap",
  },
  sep: { color: "#334155", fontSize: 18 },
  btn: {
    padding: "4px 10px",
    borderRadius: 6,
    border: "1px solid #334155",
    background: "#1e293b",
    color: "#94a3b8",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    transition: "all .15s",
    whiteSpace: "nowrap",
  },
  btnActive: {
    background: "#1d4ed8",
    borderColor: "#3b82f6",
    color: "#fff",
  },
  btnGreen: {
    background: "#14532d",
    borderColor: "#22c55e",
    color: "#22c55e",
  },
  grid: {
    flex: 1,
    display: "grid",
    overflow: "hidden",
  },
  panel: {
    display: "flex",
    flexDirection: "column",
    border: "1px solid #1e293b",
    background: "#0f172a",
    overflow: "hidden",
    transition: "border-color .15s",
    cursor: "default",
    minHeight: 0,
  },
  panelActive: {
    borderColor: "#3b82f6",
  },
  panelBar: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "3px 8px",
    background: "#0a1628",
    borderBottom: "1px solid #1e293b",
    flexShrink: 0,
    minHeight: 32,
  },
  symbolInput: {
    background: "transparent",
    border: "1px solid #334155",
    borderRadius: 4,
    color: "#f1f5f9",
    fontSize: 13,
    fontWeight: 700,
    padding: "2px 6px",
    width: 80,
    textTransform: "uppercase",
    outline: "none",
    letterSpacing: "0.05em",
  },
  intervalBtn: {
    padding: "2px 7px",
    borderRadius: 4,
    border: "1px solid #334155",
    background: "transparent",
    color: "#64748b",
    cursor: "pointer",
    fontSize: 11,
    fontWeight: 600,
  },
  intervalBtnActive: {
    background: "#1e40af",
    borderColor: "#3b82f6",
    color: "#fff",
  },
  iconBtn: {
    padding: "2px 6px",
    borderRadius: 4,
    border: "1px solid #334155",
    background: "transparent",
    color: "#64748b",
    cursor: "pointer",
    fontSize: 14,
    lineHeight: 1,
    marginRight: "auto",
  },
  chartWrap: {
    flex: 1,
    overflow: "hidden",
    minHeight: 0,
  },
};

/* ── Chart Panel ── */
function ChartPanel({ panel, isActive, isMaximized, syncMode, onActivate, onSymbolChange, onIntervalChange, onMaximize, onReset }) {
  const inputRef = useRef(null);
  const [inputVal, setInputVal] = useState(panel.symbol);

  const handleSymbolBlur = () => {
    const v = inputVal.trim().toUpperCase();
    if (v && v !== panel.symbol) onSymbolChange(panel.id, v);
    else setInputVal(panel.symbol);
  };

  const handleSymbolKey = (e) => {
    if (e.key === "Enter") {
      e.target.blur();
    }
    if (e.key === "Escape") {
      setInputVal(panel.symbol);
      e.target.blur();
    }
  };

  // keep input in sync when parent changes (e.g. preset)
  const prevSymbol = useRef(panel.symbol);
  if (panel.symbol !== prevSymbol.current) {
    prevSymbol.current = panel.symbol;
    setInputVal(panel.symbol);
  }

  return (
    <div
      style={{ ...S.panel, ...(isActive ? S.panelActive : {}) }}
      onClick={onActivate}
    >
      {/* Top bar */}
      <div style={S.panelBar} onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          style={S.symbolInput}
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value.toUpperCase())}
          onBlur={handleSymbolBlur}
          onKeyDown={handleSymbolKey}
          placeholder="رمز"
          spellCheck={false}
          dir="ltr"
        />
        {/* Interval buttons */}
        {INTERVALS.map((iv) => (
          <button
            key={iv.value}
            style={{
              ...S.intervalBtn,
              ...(panel.interval === iv.value ? S.intervalBtnActive : {}),
            }}
            onClick={() => onIntervalChange(panel.id, iv.value)}
            title={iv.label}
          >
            {iv.label}
          </button>
        ))}
        {/* Maximize */}
        <button
          style={S.iconBtn}
          onClick={() => onMaximize(panel.id)}
          title={isMaximized ? "استعادة" : "تكبير"}
        >
          {isMaximized ? "⊡" : "⛶"}
        </button>
        {/* Reset/close */}
        <button
          style={{ ...S.iconBtn, marginRight: 0, color: "#ef4444" }}
          onClick={() => onReset(panel.id)}
          title="إعادة ضبط"
        >
          ✕
        </button>
      </div>

      {/* Chart */}
      <div style={S.chartWrap}>
        <TradingViewWidget
          symbol={normalizeSymbol(panel.symbol)}
          interval={panel.interval}
          height={9999}
          showToolbar={false}
          showVolume={true}
          studies={[]}
        />
      </div>
    </div>
  );
}

/* ── Main Page ── */
export default function MultiChartPage() {
  const [panels, setPanels] = useState(DEFAULT_PANELS);
  const [activePanel, setActivePanel] = useState(0);
  const [maximizedId, setMaximizedId] = useState(null);
  const [syncMode, setSyncMode] = useState(false);
  const [layout, setLayout] = useState("2x2");

  const handleSymbolChange = useCallback((id, symbol) => {
    setPanels((prev) => prev.map((p) => (p.id === id ? { ...p, symbol } : p)));
  }, []);

  const handleIntervalChange = useCallback((id, interval) => {
    if (syncMode) {
      setPanels((prev) => prev.map((p) => ({ ...p, interval })));
    } else {
      setPanels((prev) => prev.map((p) => (p.id === id ? { ...p, interval } : p)));
    }
  }, [syncMode]);

  const handleMaximize = useCallback((id) => {
    setMaximizedId((prev) => (prev === id ? null : id));
  }, []);

  const handleReset = useCallback((id) => {
    const defaults = DEFAULT_PANELS[id];
    setPanels((prev) => prev.map((p) => (p.id === id ? { ...p, symbol: defaults.symbol, interval: defaults.interval } : p)));
  }, []);

  const applyPreset = (key) => {
    const { symbols } = PRESETS[key];
    setPanels((prev) => prev.map((p, i) => ({ ...p, symbol: symbols[i] || p.symbol })));
    setMaximizedId(null);
  };

  /* Compute grid layout */
  const getGridStyle = () => {
    if (maximizedId !== null) {
      return { ...S.grid, gridTemplateColumns: "1fr", gridTemplateRows: "1fr" };
    }
    if (layout === "2x2") {
      return { ...S.grid, gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr" };
    }
    if (layout === "1x3") {
      // Large left (row-span 2), 3 small right
      return {
        ...S.grid,
        gridTemplateColumns: "1fr 1fr",
        gridTemplateRows: "1fr 1fr 1fr",
      };
    }
    if (layout === "2p1") {
      // 2 top + 1 large bottom
      return {
        ...S.grid,
        gridTemplateColumns: "1fr 1fr",
        gridTemplateRows: "1fr 1fr",
      };
    }
    return { ...S.grid, gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr" };
  };

  const getPanelStyle = (panel, index) => {
    if (maximizedId !== null) {
      return panel.id === maximizedId
        ? { gridColumn: "1", gridRow: "1", display: "flex", flexDirection: "column", ...S.panel, ...(activePanel === panel.id ? S.panelActive : {}) }
        : { display: "none" };
    }
    if (layout === "1x3") {
      // panel 0 spans rows 1-3 on col 1, panels 1-3 on col 2
      if (index === 0) return { gridColumn: "1", gridRow: "1 / 4", ...S.panel, ...(activePanel === panel.id ? S.panelActive : {}) };
      return { gridColumn: "2", gridRow: `${index}`, ...S.panel, ...(activePanel === panel.id ? S.panelActive : {}) };
    }
    if (layout === "2p1") {
      // panels 0,1 top row; panel 2 spans cols bottom, panel 3 hidden
      if (index === 0) return { gridColumn: "1", gridRow: "1", ...S.panel, ...(activePanel === panel.id ? S.panelActive : {}) };
      if (index === 1) return { gridColumn: "2", gridRow: "1", ...S.panel, ...(activePanel === panel.id ? S.panelActive : {}) };
      if (index === 2) return { gridColumn: "1 / 3", gridRow: "2", ...S.panel, ...(activePanel === panel.id ? S.panelActive : {}) };
      return { display: "none" };
    }
    // 2x2 default
    const col = (index % 2) + 1;
    const row = Math.floor(index / 2) + 1;
    return { gridColumn: `${col}`, gridRow: `${row}`, ...S.panel, ...(activePanel === panel.id ? S.panelActive : {}) };
  };

  return (
    <div style={S.page} dir="rtl">
      {/* Header */}
      <div style={S.header}>
        <span style={S.headerTitle}>📊 متعدد الشارتات</span>
        <span style={S.sep}>|</span>

        {/* Sync toggle */}
        <button
          style={{ ...S.btn, ...(syncMode ? S.btnGreen : {}) }}
          onClick={() => setSyncMode((v) => !v)}
          title="مزامنة الفترة الزمنية بين الشارتات"
        >
          {syncMode ? "🔗 مزامنة: تشغيل" : "🔗 مزامنة الفترة"}
        </button>

        <span style={S.sep}>|</span>

        {/* Layout switcher */}
        {LAYOUTS.map((l) => (
          <button
            key={l.id}
            style={{ ...S.btn, ...(layout === l.id && maximizedId === null ? S.btnActive : {}) }}
            onClick={() => { setLayout(l.id); setMaximizedId(null); }}
          >
            {l.label}
          </button>
        ))}

        <span style={S.sep}>|</span>

        {/* Presets */}
        {Object.entries(PRESETS).map(([key, p]) => (
          <button
            key={key}
            style={S.btn}
            onClick={() => applyPreset(key)}
          >
            {p.label}
          </button>
        ))}

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Active symbol info */}
        {activePanel !== null && (
          <span style={{ fontSize: 12, color: "#64748b" }}>
            نشط: <strong style={{ color: "#3b82f6" }}>{panels[activePanel]?.symbol}</strong>
          </span>
        )}
      </div>

      {/* Chart Grid */}
      <div style={getGridStyle()}>
        {panels.map((panel, index) => {
          const styleOverride = getPanelStyle(panel, index);
          if (styleOverride.display === "none") return null;
          return (
            <div key={panel.id} style={styleOverride} onClick={() => setActivePanel(panel.id)}>
              <ChartPanel
                panel={panel}
                isActive={activePanel === panel.id}
                isMaximized={maximizedId === panel.id}
                syncMode={syncMode}
                onActivate={() => setActivePanel(panel.id)}
                onSymbolChange={handleSymbolChange}
                onIntervalChange={handleIntervalChange}
                onMaximize={handleMaximize}
                onReset={handleReset}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
