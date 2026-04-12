import { memo } from "react";

import EmptyState from "../../components/ui/EmptyState";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton";
import SectionCard from "../../components/ui/SectionCard";
import SectionHeader from "../../components/ui/SectionHeader";
import { formatCompact, formatPercent } from "./formatters";


function LiveMarketMarketPulse({ bootLoading, marketPulse, onSelectSymbol }) {
  return (
    <SectionCard
      className="span-5"
      title="الزخم والنشاط"
      description="أسرع لوحتين لمراقبة السوق الحالي من داخل نتائج المستكشف، من دون الحاجة لفتح صفحة إضافية."
    >
      {bootLoading ? (
        <LoadingSkeleton lines={6} />
      ) : (
        <div className="market-board-grid">
          <div className="market-board-column">
            <SectionHeader title="أكبر المتحركات" description="الحركة النسبية الأعلى ضمن المجموعة الحالية." />
            <div className="market-card-stack">
              {marketPulse.movers.length ? marketPulse.movers.map((item) => (
                <div className="market-list-card" key={`mover-${item.symbol}`}>
                  <div>
                    <strong>{item.symbol}</strong>
                    <p>{item.security_name || item.short_name || item.exchange}</p>
                  </div>
                  <div className="market-list-card-metrics">
                    <span className={Number(item.change_pct || 0) >= 0 ? "quote-positive" : "quote-negative"}>{formatPercent(item.change_pct)}</span>
                    <button className="inline-link" type="button" onClick={() => onSelectSymbol(item.symbol)}>فتح</button>
                  </div>
                </div>
              )) : <EmptyState title="لا توجد متحركات حالياً" description="وسّع نطاق الفلاتر أو اترك التحديث الحي يعمل قليلاً لإظهار الحركة." />}
            </div>
          </div>
          <div className="market-board-column">
            <SectionHeader title="الأكثر نشاطاً" description="أعلى السيولة الظاهرة داخل الكون الحالي." />
            <div className="market-card-stack">
              {marketPulse.active.length ? marketPulse.active.map((item) => (
                <div className="market-list-card" key={`active-${item.symbol}`}>
                  <div>
                    <strong>{item.symbol}</strong>
                    <p>{item.security_name || item.short_name || item.exchange}</p>
                  </div>
                  <div className="market-list-card-metrics">
                    <span>{formatCompact(item.volume)}</span>
                    <button className="inline-link" type="button" onClick={() => onSelectSymbol(item.symbol)}>فتح</button>
                  </div>
                </div>
              )) : <EmptyState title="لا توجد سيولة بارزة" description="ستظهر هنا الأسماء الأكثر نشاطاً ضمن نتائج المستكشف الحالية." />}
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}


export default memo(LiveMarketMarketPulse);
