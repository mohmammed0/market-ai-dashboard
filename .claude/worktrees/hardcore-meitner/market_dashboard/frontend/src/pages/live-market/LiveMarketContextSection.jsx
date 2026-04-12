import { memo } from "react";

import EmptyState from "../../components/ui/EmptyState";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton";
import MetricCard from "../../components/ui/MetricCard";
import SectionCard from "../../components/ui/SectionCard";
import SectionHeader from "../../components/ui/SectionHeader";
import StatusBadge from "../../components/ui/StatusBadge";
import { formatUnsignedPercent } from "./formatters";


function LiveMarketContextSection({ contextLoading, contextPayload }) {
  return (
    <SectionCard
      className="span-7"
      title="سياق القرار"
      description="بطاقات مرتبطة مباشرة بالرمز النشط: الإشارة، المخاطر، التنبيهات، والأحداث حتى تبقى القراءة مركزة على القرار."
    >
      {contextLoading ? (
        <LoadingSkeleton lines={6} />
      ) : contextPayload ? (
        <div className="terminal-context-grid">
          <MetricCard
            label="ملخص الإشارة"
            value={contextPayload.signal?.signal || "-"}
            detail={`الثقة ${contextPayload.signal?.confidence ?? "-"} · Best ${contextPayload.signal?.best_setup || "-"}`}
            badge={contextPayload.signal?.setup_type || "Signal"}
            tone={String(contextPayload.signal?.signal || "").toLowerCase().includes("buy") ? "accent" : "warning"}
          />
          <MetricCard
            label="حالة المخاطر"
            value={formatUnsignedPercent(contextPayload.risk?.gross_exposure_pct)}
            detail={contextPayload.risk?.portfolio_warnings?.[0] || "لا توجد تحذيرات بارزة الآن."}
            badge="Risk"
            tone={contextPayload.risk?.portfolio_warnings?.length ? "warning" : "accent"}
          />
          <div className="panel result-panel terminal-context-panel">
            <SectionHeader title="التنبيهات الأخيرة" description="آخر الإشعارات المرتبطة بالرمز الحالي." />
            {contextPayload.alerts?.length ? (
              <div className="dashboard-feed-list">
                {contextPayload.alerts.map((alert) => (
                  <div className="dashboard-feed-item" key={`alert-${alert.id}`}>
                    <div className="dashboard-feed-copy">
                      <strong>{alert.alert_type || "تنبيه"}</strong>
                      <p>{alert.message || "تم تسجيل حدث تنبيهي مرتبط بالرمز النشط."}</p>
                    </div>
                    <StatusBadge label={alert.severity || "info"} tone={alert.severity === "high" ? "warning" : "subtle"} />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="لا توجد تنبيهات حديثة" description="هذا جيد غالباً؛ لا توجد إشارات تنبيهية حديثة مرتبطة بالرمز المختار." />
            )}
          </div>
          <div className="panel result-panel terminal-context-panel">
            <SectionHeader title="الأحداث والمحركات" description="أقرب المحفزات أو الأحداث المرجعية للرمز النشط." />
            {contextPayload.events?.length ? (
              <div className="dashboard-feed-list">
                {contextPayload.events.map((event, index) => (
                  <div className="dashboard-feed-item" key={`event-${event.id || index}`}>
                    <div className="dashboard-feed-copy">
                      <strong>{event.title || event.event || "حدث سوقي"}</strong>
                      <p>{event.summary || event.description || "حدث مرتبط بسياق السوق أو الشركة."}</p>
                    </div>
                    <StatusBadge label={event.sentiment || event.category || "حدث"} tone="subtle" />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState title="لا توجد أحداث بارزة" description="لم ترجع خدمة الأحداث محفزات حديثة لهذا الرمز حالياً." />
            )}
          </div>
        </div>
      ) : (
        <EmptyState title="السياق غير متاح" description="تعذر إحضار الإشارات والمخاطر والأحداث للرمز النشط في هذه الجولة." />
      )}
    </SectionCard>
  );
}


export default memo(LiveMarketContextSection);
