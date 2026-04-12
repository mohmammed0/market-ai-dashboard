import { useDeferredValue, useEffect, useRef, useState } from "react";

import { searchMarketUniverse } from "../../api/market";
import { useSymbolLibrary } from "../../lib/useSymbolLibrary";
import StatusBadge from "./StatusBadge";


function dedupeItems(items) {
  const nextItems = [];
  const seen = new Set();
  for (const item of items) {
    const symbol = String(item?.symbol || "").trim().toUpperCase();
    if (!symbol || seen.has(symbol)) {
      continue;
    }
    seen.add(symbol);
    nextItems.push(item);
  }
  return nextItems;
}


function SymbolOption({ item, active, onSelect, onTogglePin, pinned, onHover }) {
  return (
    <div
      className={`symbol-option${active ? " active" : ""}`}
      onMouseDown={(event) => event.preventDefault()}
      onClick={() => onSelect(item)}
      onMouseEnter={onHover}
      aria-selected={active}
    >
      <div className="symbol-option-copy">
        <div className="symbol-option-topline">
          <strong>{item.symbol}</strong>
          <div className="status-badge-stack">
            {item.exchange ? <StatusBadge label={item.exchange} tone="subtle" /> : null}
            {item.listing_category_label ? <StatusBadge label={item.listing_category_label} tone="subtle" /> : null}
          </div>
        </div>
        <small>{item.security_name || "رمز بدون اسم شركة متاح حالياً"}</small>
      </div>
      <div className="symbol-option-actions">
        <span className="symbol-option-price">{item.price ? `$${Number(item.price).toFixed(2)}` : ""}</span>
        <button
          className={`symbol-pin-button${pinned ? " pinned" : ""}`}
          type="button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={(event) => {
            event.stopPropagation();
            onTogglePin(item);
          }}
        >
          {pinned ? "مثبّت" : "تثبيت"}
        </button>
      </div>
    </div>
  );
}


export default function SymbolPicker({
  label = "الرمز",
  value = "",
  onChange,
  onSelect,
  placeholder = "ابحث بالرمز أو اسم الشركة",
  helperText = "",
  error = "",
  compact = false,
  limit = 10,
}) {
  const { pinned, recent, rememberSymbol, togglePinnedSymbol, isPinnedSymbol } = useSymbolLibrary();
  const [query, setQuery] = useState(value || "");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const deferredQuery = useDeferredValue(query.trim());
  const containerRef = useRef(null);

  useEffect(() => {
    setQuery(value || "");
  }, [value]);

  useEffect(() => {
    function handleClickOutside(event) {
      if (!containerRef.current || containerRef.current.contains(event.target)) {
        return;
      }
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!open || !deferredQuery) {
      setResults([]);
      setLoading(false);
      setHighlightedIndex(0);
      return;
    }
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      searchMarketUniverse({ q: deferredQuery, limit, signal: controller.signal })
        .then((payload) => {
          if (active) {
            setResults(payload?.items || []);
            setHighlightedIndex(0);
          }
        })
        .catch((error) => {
          if (error?.name === "AbortError") {
            return;
          }
          if (active) {
            setResults([]);
            setHighlightedIndex(0);
          }
        })
        .finally(() => {
          if (active) {
            setLoading(false);
          }
        });
    }, 120);
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [deferredQuery, limit, open]);

  const quickItems = dedupeItems([...pinned, ...recent]).slice(0, 10);
  const visibleItems = deferredQuery ? results : quickItems;
  const sectionTitle = deferredQuery ? "نتائج البحث" : pinned.length ? "الرموز المثبتة والأخيرة" : "اختيارات سريعة";

  function selectSymbol(item) {
    const symbol = String(item?.symbol || query || "").trim().toUpperCase();
    if (!symbol) {
      return;
    }
    const normalizedItem = {
      ...item,
      symbol,
    };
    setQuery(symbol);
    onChange?.(symbol);
    rememberSymbol(normalizedItem);
    onSelect?.(normalizedItem);
    setOpen(false);
  }

  function handleKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setHighlightedIndex((current) => Math.min(current + 1, Math.max(visibleItems.length - 1, 0)));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((current) => Math.max(current - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (visibleItems.length) {
        selectSymbol(visibleItems[Math.min(highlightedIndex, visibleItems.length - 1)]);
        return;
      }
      selectSymbol({ symbol: query.trim().toUpperCase() });
    }
    if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <label className={`field symbol-picker-field${compact ? " symbol-picker-field-compact" : ""}`}>
      <span>{label}</span>
      <div className="symbol-picker-shell" ref={containerRef}>
        <div className="symbol-picker-input-row">
          <input
            value={query}
            placeholder={placeholder}
            onFocus={() => setOpen(true)}
            onChange={(event) => {
              const nextValue = event.target.value;
              setQuery(nextValue);
              onChange?.(nextValue);
              if (!open) {
                setOpen(true);
              }
            }}
            onKeyDown={handleKeyDown}
          />
          <button
            className="secondary-button symbol-picker-commit"
            type="button"
            onClick={() => selectSymbol({ symbol: query.trim().toUpperCase() })}
          >
            اختيار
          </button>
        </div>
        {open ? (
          <div className="symbol-picker-dropdown">
            <div className="symbol-picker-dropdown-header">
              <strong>{sectionTitle}</strong>
              <span>{loading ? "جارٍ البحث..." : "بحث سريع في جميع الأسهم الأمريكية"}</span>
            </div>
            {visibleItems.length ? (
              <div className="symbol-picker-options">
                {visibleItems.map((item, index) => (
                  <SymbolOption
                    key={`${item.symbol}-${index}`}
                    item={item}
                    active={index === highlightedIndex || String(item.symbol || "").trim().toUpperCase() === String(value || "").trim().toUpperCase()}
                    pinned={isPinnedSymbol(item.symbol)}
                    onHover={() => setHighlightedIndex(index)}
                    onSelect={selectSymbol}
                    onTogglePin={togglePinnedSymbol}
                  />
                ))}
              </div>
            ) : (
              <div className="symbol-picker-empty">
                {deferredQuery ? "لا توجد نتيجة مطابقة. اضغط اختيار لاعتماد الرمز المكتوب." : "ابدأ بكتابة رمز أو اسم شركة، أو اختر من آخر الرموز المستخدمة."}
              </div>
            )}
          </div>
        ) : null}
      </div>
      {helperText ? <small className="field-help">{helperText}</small> : null}
      {error ? <small className="field-error">{error}</small> : null}
    </label>
  );
}
