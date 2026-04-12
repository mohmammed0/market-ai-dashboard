import { translateNode } from "../../lib/i18n";


export default function SymbolBadge({ symbol, meta }) {
  return (
    <span className="symbol-badge">
      <strong>{translateNode(symbol)}</strong>
      {meta ? <small>{translateNode(meta)}</small> : null}
    </span>
  );
}
