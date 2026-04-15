/**
 * TradingViewWidget — شارت TradingView الاحترافي المدمج
 */
import { useEffect, useRef, memo } from "react";

let _counter = 0;

const TradingViewWidget = memo(function TradingViewWidget({
  symbol = "NASDAQ:AAPL",
  interval = "D",
  height = 500,
  theme = "dark",
  style = "1",
  showToolbar = true,
  showVolume = true,
  locale = "ar_AE",
  studies = [],
}) {
  const containerRef = useRef(null);
  const idRef = useRef(`tv_${++_counter}`);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.innerHTML = "";
    el.id = idRef.current;

    const cfg = {
      autosize: true,
      symbol: normalizeSymbol(symbol),
      interval,
      timezone: "America/New_York",
      theme,
      style,
      locale,
      toolbar_bg: "#0f172a",
      enable_publishing: false,
      allow_symbol_change: true,
      save_image: true,
      hide_top_toolbar: !showToolbar,
      hide_volume: !showVolume,
      details: false,
      hotlist: false,
      calendar: false,
      show_popup_button: false,
      container_id: idRef.current,
      studies: studies.length > 0 ? studies : ["RSI@tv-basicstudies","MACD@tv-basicstudies"],
      overrides: {
        "paneProperties.background": "#0f172a",
        "paneProperties.backgroundType": "solid",
        "paneProperties.vertGridProperties.color": "#1e293b",
        "paneProperties.horzGridProperties.color": "#1e293b",
        "scalesProperties.textColor": "#94a3b8",
        "scalesProperties.backgroundColor": "#0f172a",
        "candleStyle.upColor": "#22c55e",
        "candleStyle.downColor": "#ef4444",
        "candleStyle.borderUpColor": "#22c55e",
        "candleStyle.borderDownColor": "#ef4444",
        "candleStyle.wickUpColor": "#22c55e",
        "candleStyle.wickDownColor": "#ef4444",
      },
      studies_overrides: {
        "volume.volume.color.0": "#ef444466",
        "volume.volume.color.1": "#22c55e66",
      },
      loading_screen: { backgroundColor: "#0f172a", foregroundColor: "#3b82f6" },
    };

    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    s.async = true;
    s.innerHTML = JSON.stringify(cfg);
    el.appendChild(s);

    return () => { if (el) el.innerHTML = ""; };
  }, [symbol, interval, theme, style, showToolbar, showVolume, locale]);

  return (
    <div ref={containerRef} style={{ width:"100%", height:`${height}px`, borderRadius:"8px", overflow:"hidden", background:"#0f172a" }} />
  );
});

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

export default TradingViewWidget;
