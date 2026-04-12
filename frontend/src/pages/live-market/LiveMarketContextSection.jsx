import { memo } from "react";

import DecisionPanel from "../../components/ui/DecisionPanel";
import EmptyState from "../../components/ui/EmptyState";
import LoadingSkeleton from "../../components/ui/LoadingSkeleton";
import MetricCard from "../../components/ui/MetricCard";
import SectionCard from "../../components/ui/SectionCard";
import StatusBadge from "../../components/ui/StatusBadge";
import SummaryStrip from "../../components/ui/SummaryStrip";
import { formatUnsignedPercent } from "./formatters";


function LiveMarketContextSection({ contextLoading, contextPayload }) {
  return (
    <>
      <DecisionPanel
        className="span-5"
        decision={contextPayload?.decision}
        loading={contextLoading}
        title="لوحة القرار"
        description="قرار منظم مرتبط مباشرة بالشارت النشط مع شرح ومخاطر وروابط الاستراتيجية."
      />
      <SectionCard
        className="span-7"
        title="سياق المخاطر والتنبيهات"
        description="المخاطر العامة والتنبيهات والأحداث القريبة حتى يبقى القرار مشفوعاً بسياق التشغيل."
      >
        {contextLoading ? (
          <LoadingSkeleton lines={6} />
        ) : contextPayload ? (
          <>
            <SummaryStrip
              compact
              items={[
                {
                  label: "حالة المخاطر",
                  value: formatUnsignedPercent(contextPayload.risk?.gross_exposure_pct),
                  detail: contextPayload.risk?.portfolio_warnings?.[0] || "لا توجد تحذيرات بارزة الآن.",
                  badge: "Risk",
                  tone: contextPayload.risk?.portfolio_warnings?.length ? "warning" : "accent",
                },
                {
                  label: "التنبيهات",
                  value: contextPayload.alerts?.length ?? 0,
                  badge: "Alert",
                },
                {
                  label: "الأحداث",
                  value: contextPayload.events?.length ?? 0,
                  badge: "Event",
                },
              ]}
            />
            <div className="terminal-context-grid">
              <MetricCard
                label="ملخص الإشارة"
                value={contextPayload.signal?.signal || "-"}
                detail={`الثقة ${contextPayload.signal?.confidence ?? "-"} · Best ${contextPayload.signal?.best_setup || "-"}`}
                badge={contextPayload.signal?.setup_type || "Signal"}
                tone={String(contextPayload.signal?.signal || "").toLowerCase().includes("buy") ? "accent" : "warning"}
              />
              <MetricCard
                label="التحذير الأبرز"
                value={contextPayload.risk?.portfolio_warnings?.length ? "متابعة" : "منخفض"}
                detail={contextPayload.risk?.portfolio_warnings?.[0] || "لا توجد تحذيرات بارزة الآن."}
                badge="Portfolio"
                tone={contextPayload.risk?.portfolio_warnings?.length ? "warning" : "accent"}
              />
            </div>
            <div className="decision-feed-list">
              {contextPayload.alerts?.length ? contextPayload.alerts.map((alert) => (
                <div className="decision-feed-item" key={`alert-${alert.id}`}>
                  <div>
                    <strong>{alert.alert_type || "تنبيه"}</strong>
                    <p>{alert.message || "تم تسجيل حدث تنبيهي مرتبط بالرمز النشط."}</p>
                  </div>
                  <StatusBadge label={alert.severity || "info"} tone={alert.severity === "high" ? "warning" : "subtle"} />
                </div>
              )) : (
                <EmptyState title="لا توجد تنبيهات حديثة" description="هذا جيد غالباً؛ لا توجد إشارات تنبيهية حديثة مرتبطة بالرمز المختار." />
              )}
            </div>
            {contextPayload.events?.length ? (
              <div className="decision-feed-list">
                {contextPayload.events.map((event, index) => (
                  <div className="decision-feed-item" key={`event-${event.id || index}`}>
                    <div>
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
          </>
        ) : (
          <EmptyState title="السياق غير متاح" description="تعذر إحضار الإشارات والمخاطر والأحداث للرمز النشط في هذه الجولة." />
        )}
      </SectionCard>
    </>
  );
}


export default memo(LiveMarketContextSection);
