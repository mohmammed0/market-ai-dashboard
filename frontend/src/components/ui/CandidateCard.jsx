import { Link } from "react-router-dom";
import SignalBadge from "./SignalBadge";
import StatusBadge from "./StatusBadge";
import { useSymbolLibrary } from "../../lib/useSymbolLibrary";
import { t } from "../../lib/i18n";


export default function CandidateCard({ item }) {
  const { isPinnedSymbol, togglePinnedSymbol } = useSymbolLibrary();
  const symbol = item.instrument ?? "-";

  return (
    <article className="candidate-card">
      <div className="candidate-topline">
        <div>
          <span>{t(`Rank #${item.rank ?? "-"}`)}</span>
          <strong>{symbol}</strong>
        </div>
        <StatusBadge label={`Conf ${item.confidence ?? "-"}`} tone="accent" />
      </div>
      <div className="candidate-body">
        <div><span>{t("Signal")}</span><SignalBadge signal={item.signal} /></div>
        <div><span>{t("Best Setup")}</span><strong>{item.best_setup || "-"}</strong></div>
        <div><span>{t("Setup Type")}</span><strong>{item.setup_type || "-"}</strong></div>
        <div><span>{t("Score")}</span><strong>{item.enhanced_combined_score ?? item.combined_score ?? "-"}</strong></div>
      </div>
      <div className="candidate-actions">
        <button className="secondary-button" type="button" onClick={() => togglePinnedSymbol({ symbol })}>
          {isPinnedSymbol(symbol) ? "إلغاء التثبيت" : "تثبيت"}
        </button>
        <Link className="inline-link inline-link-chip" to={`/analyze?symbol=${encodeURIComponent(symbol)}`}>تحليل</Link>
        <Link className="inline-link inline-link-chip" to={`/execution?symbol=${encodeURIComponent(symbol)}`}>ورقي</Link>
      </div>
    </article>
  );
}
