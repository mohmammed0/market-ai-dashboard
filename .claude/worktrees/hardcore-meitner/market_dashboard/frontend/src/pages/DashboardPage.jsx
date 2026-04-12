import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import PageFrame from "../components/PageFrame";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import ActionButton from "../components/ui/ActionButton";
import MetricCard from "../components/ui/MetricCard";
import SectionCard from "../components/ui/SectionCard";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import SymbolWorkspaceBar from "../components/ui/SymbolWorkspaceBar";
import { fetchAlertHistory, fetchDashboardSummary, fetchLiveSnapshots } from "../lib/api";
import { useSymbolLibrary } from "../lib/useSymbolLibrary";
import { t } from "../lib/i18n";


function statusTone(runtimeStatus) {
  const normalized = String(runtimeStatus || "").toLowerCase();
  if (normalized === "running") return "accent";
  if (normalized === "error" || normalized === "failed") return "warning";
  return "subtle";
}


export default function DashboardPage() {
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [workspaceQuotes, setWorkspaceQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { pinned, recent } = useSymbolLibrary();

  useEffect(() => {
    let active = true;

    fetchDashboardSummary()
      .then((data) => {
        if (active) {
          setSummary(data);
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message || "Dashboard summary failed.");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    fetchAlertHistory()
      .then((data) => {
        if (active) {
          setAlerts((data?.items || []).slice(0, 4));
        }
      })
      .catch(() => {});

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const symbols = [...pinned, ...recent].map((item) => item.symbol).filter(Boolean).slice(0, 6);
    if (!symbols.length) {
      setWorkspaceQuotes([]);
      return;
    }
    let active = true;
    fetchLiveSnapshots({ symbols })
      .then((payload) => {
        if (active) {
          setWorkspaceQuotes(payload?.items || []);
        }
      })
      .catch(() => {
        if (active) {
          setWorkspaceQuotes([]);
        }
      });
    return () => {
      active = false;
    };
  }, [pinned, recent]);

  const opportunities = useMemo(
    () => (summary?.watchlists?.momentum_leaders || []).slice(0, 5),
    [summary]
  );

  const learningState = summary?.continuous_learning?.state || {};
  const marketProvider = summary?.market_data_status?.primary_provider || "-";
  const bestCandidate = learningState?.latest_metrics?.best_candidate?.candidate_name || learningState?.best_strategy_name || "-";

  return (
    <PageFrame
      title="لوحة التداول"
      description="واجهة أقصر وأوضح تبدأ بما يهم القرار الآن ثم تترك التفاصيل الداعمة في الخلفية."
      eyebrow="الرئيسية"
      headerActions={
        <>
          <ActionButton to="/live-market" variant="secondary">السوق</ActionButton>
          <ActionButton to="/strategy-lab" variant="secondary">الاستراتيجية</ActionButton>
          <StatusBadge label={marketProvider !== "-" ? `البيانات ${marketProvider}` : "البيانات"} tone="accent" />
        </>
      }
    >
      <SectionCard
        title="نبض الجلسة"
        description="ملخص سريع لحالة السوق، المحرك البحثي، وأهم ما يستحق المتابعة."
        action={<StatusBadge label={loading ? "جارٍ التحديث" : learningState.active_stage || "idle"} tone={statusTone(learningState.runtime_status)} />}
      >
        <ErrorBanner message={error} />
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : summary ? (
          <SummaryStrip
            compact
            items={[
              { label: "أفضل مرشح", value: summary.scan_ranking?.top_pick || "-" },
              { label: "اتساع السوق", value: summary.breadth?.breadth_ratio ?? "-" },
              { label: "مزود البيانات", value: marketProvider },
              { label: "مرحلة التعلم", value: learningState.active_stage || "-" },
              { label: "أفضل مرشح آلي", value: bestCandidate },
              { label: "المراكز المفتوحة", value: summary.portfolio?.summary?.open_positions ?? 0 },
            ]}
          />
        ) : (
          <div className="empty-state">
            <strong>{t("No dashboard summary")}</strong>
            <p>{t("The backend summary endpoint did not return data.")}</p>
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="مساحة العمل"
        description="رمز موحد، انتقال مباشر، وقائمة متابعة قصيرة بدل لوحة مزدحمة."
        action={<StatusBadge label={workspaceQuotes.length ? `${workspaceQuotes.length} رموز` : "رموز العمل"} tone="subtle" />}
      >
        <SymbolWorkspaceBar />
        {workspaceQuotes.length ? (
          <div className="result-grid dashboard-watchlist-grid">
            {workspaceQuotes.map((item) => (
              <MetricCard
                key={item.symbol}
                label={item.symbol}
                value={item.price ?? "-"}
                detail={`${item.change_pct ?? 0}% · ${item.exchange_name || item.source || "snapshot"}`}
                tone={Number(item.change_pct || 0) >= 0 ? "accent" : "warning"}
              />
            ))}
          </div>
        ) : (
          <div className="empty-state compact-empty">
            <strong>ابدأ برمز واحد</strong>
            <p>اختر رمزاً من شريط العمل ثم ثبّته أو انقلّه مباشرة إلى التحليل أو الاستراتيجية.</p>
          </div>
        )}
      </SectionCard>

      <SectionCard
        className="span-7"
        title="قائمة المتابعة"
        description="الفرص الأقرب للانتقال الفوري من الشاشة الرئيسية إلى التنفيذ الورقي أو التحليل."
        action={<StatusBadge label={opportunities.length ? `${opportunities.length} فرص` : "بدون فرص"} tone="subtle" />}
      >
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : opportunities.length ? (
          <div className="dashboard-decision-list">
            {opportunities.map((item) => (
              <div className="dashboard-decision-item" key={item.symbol}>
                <div className="dashboard-decision-primary">
                  <strong>{item.symbol}</strong>
                  <p>{item.security_name || "فرصة متابعة"}</p>
                </div>
                <div className="dashboard-decision-metrics">
                  <span className={Number(item.change_pct || 0) >= 0 ? "quote-positive" : "quote-negative"}>{`${item.change_pct ?? 0}%`}</span>
                  <small>{item.price ?? "-"}</small>
                </div>
                <div className="dashboard-decision-actions">
                  <Link className="inline-link inline-link-chip" to={`/analyze?symbol=${encodeURIComponent(item.symbol)}`}>تحليل</Link>
                  <Link className="inline-link inline-link-chip" to={`/paper-trading?symbol=${encodeURIComponent(item.symbol)}`}>ورقي</Link>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state compact-empty">
            <strong>لا توجد فرص متابعة حالياً</strong>
            <p>ستظهر هنا الرموز التي تستحق الانتقال السريع إلى التحليل أو التداول التجريبي.</p>
          </div>
        )}
      </SectionCard>

      <SectionCard
        className="span-5"
        title="المحرك والتنبيهات"
        description="صورة مختصرة لحالة التعلم المستمر والتنبيهات التي تستحق الانتباه الآن."
        action={<StatusBadge label={learningState.runtime_status || "idle"} tone={statusTone(learningState.runtime_status)} />}
      >
        {loading ? (
          <LoadingSkeleton lines={4} />
        ) : (
          <>
            <SummaryStrip
              compact
              items={[
                { label: "آخر نجاح", value: learningState.last_success_at || "-" },
                { label: "الدورة التالية", value: learningState.next_cycle_at || "-" },
                { label: "الأثر الأخير", value: summary?.continuous_learning?.recent_artifacts?.[0]?.artifact_type || "-" },
                { label: "تنبيهات المخاطر", value: summary?.risk?.portfolio_warnings?.length ?? 0, tone: "warning" },
              ]}
            />
            {alerts.length ? (
              <div className="dashboard-feed-list">
                {alerts.map((alert) => (
                  <div className="dashboard-feed-item" key={alert.id}>
                    <div className="dashboard-feed-copy">
                      <strong>{`${alert.symbol || "SYSTEM"} · ${alert.alert_type}`}</strong>
                      <p>{alert.message}</p>
                    </div>
                    <StatusBadge label={alert.severity} tone={alert.severity === "warning" ? "warning" : "subtle"} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state compact-empty">
                <strong>{t("No recent alerts")}</strong>
                <p>{t("Paper-trading alerts will appear here after signal refresh activity.")}</p>
              </div>
            )}
          </>
        )}
      </SectionCard>
    </PageFrame>
  );
}
