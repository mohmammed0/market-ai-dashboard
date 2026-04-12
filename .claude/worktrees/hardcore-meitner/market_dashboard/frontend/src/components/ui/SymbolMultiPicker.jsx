import { useMemo, useState } from "react";

import SymbolPicker from "./SymbolPicker";


function normalizeSymbols(symbols) {
  const nextValues = [];
  const seen = new Set();
  for (const value of symbols || []) {
    const symbol = String(value || "").trim().toUpperCase();
    if (!symbol || seen.has(symbol)) {
      continue;
    }
    seen.add(symbol);
    nextValues.push(symbol);
  }
  return nextValues;
}


export default function SymbolMultiPicker({
  label = "الرموز",
  symbols = [],
  onChange,
  helperText = "",
  error = "",
  maxSymbols = 150,
}) {
  const normalizedSymbols = useMemo(() => normalizeSymbols(symbols), [symbols]);
  const [draftSymbol, setDraftSymbol] = useState("");

  function updateSymbols(nextSymbols) {
    onChange?.(normalizeSymbols(nextSymbols).slice(0, maxSymbols));
  }

  function addSymbol(item) {
    const symbol = String(item?.symbol || draftSymbol || "").trim().toUpperCase();
    if (!symbol) {
      return;
    }
    updateSymbols([...normalizedSymbols, symbol]);
    setDraftSymbol("");
  }

  function removeSymbol(symbol) {
    updateSymbols(normalizedSymbols.filter((item) => item !== symbol));
  }

  return (
    <div className="field symbol-multi-picker-field">
      <span>{label}</span>
      <div className="symbol-multi-picker-panel">
        <SymbolPicker
          compact
          label="إضافة رمز"
          value={draftSymbol}
          onChange={setDraftSymbol}
          onSelect={addSymbol}
          placeholder="أضف رمزاً إلى القائمة"
          helperText="ابحث بالرمز أو اسم الشركة ثم أضفه إلى القائمة الحالية."
        />
        <div className="symbol-chip-toolbar">
          <strong>{normalizedSymbols.length} رمز</strong>
          <button
            className="secondary-button"
            type="button"
            onClick={() => addSymbol({ symbol: draftSymbol })}
            disabled={!draftSymbol.trim()}
          >
            إضافة الرمز المكتوب
          </button>
        </div>
        <div className="symbol-chip-wrap">
          {normalizedSymbols.length ? normalizedSymbols.map((symbol) => (
            <button
              key={symbol}
              className="symbol-chip"
              type="button"
              onClick={() => removeSymbol(symbol)}
              title="إزالة الرمز من القائمة"
            >
              <strong>{symbol}</strong>
              <span>إزالة</span>
            </button>
          )) : <div className="symbol-chip-empty">لا توجد رموز مضافة بعد.</div>}
        </div>
      </div>
      {helperText ? <small className="field-help">{helperText}</small> : null}
      {error ? <small className="field-error">{error}</small> : null}
    </div>
  );
}
