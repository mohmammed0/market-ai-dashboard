import { useEffect, useMemo, useState } from "react";

import PageFrame from "../components/PageFrame";
import DataTable from "../components/ui/DataTable";
import ErrorBanner from "../components/ui/ErrorBanner";
import LoadingSkeleton from "../components/ui/LoadingSkeleton";
import SectionHeader from "../components/ui/SectionHeader";
import StatusBadge from "../components/ui/StatusBadge";
import SummaryStrip from "../components/ui/SummaryStrip";
import { fetchOperationsLogs, fetchOperationsOverview } from "../api/platform";


function formatBytes(value) {
  const amount = Number(value || 0);
  if (!amount) {
    return "0 B";
  }
  if (amount >= 1024 * 1024) {
    return `${(amount / (1024 * 1024)).toFixed(2)} MB`;
  }
  if (amount >= 1024) {
    return `${(amount / 1024).toFixed(1)} KB`;
  }
  return `${amount} B`;
}


function buildEventDetail(item) {
  const priorityKeys = [
    "detail",
    "path",
    "status",
    "job_name",
    "method",
    "request_id",
    "reason",
    "error",
  ];
  const parts = [];
  for (const key of priorityKeys) {
    if (item?.[key] !== undefined && item?.[key] !== null && String(item[key]).trim()) {
      parts.push(`${key}: ${item[key]}`);
    }
  }
  return parts.join(" | ") || "-";
}


export default function OperationsPage() {
  const [overview, setOverview] = useState(null);
  const [logs, setLogs] = useState({ events: [], app_tail: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  async function loadAll(refreshMode = false) {
    if (refreshMode) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError("");
    try {
      const [overviewPayload, logsPayload] = await Promise.all([
        fetchOperationsOverview(),
        fetchOperationsLogs(80),
      ]);
      setOverview(overviewPayload);
      setLogs(logsPayload);
    } catch (requestError) {
      setError(requestError.message || "تعذر تحميل مركز العمليات.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  const eventRows = useMemo(
    () => (logs?.events || []).map((item, index) => ({
      id: `${item.timestamp || "log"}-${index}`,
      timestamp: item.timestamp || "-",
      event: item.event || item.message || "-",
      level: item.level || "-",
      logger: item.logger || "-",
      detail: buildEventDetail(item),
    })),
    [logs]
  );

  const eventColumns = useMemo(
    () => [
      { accessorKey: "timestamp", header: "الوقت" },
      { accessorKey: "event", header: "الحدث" },
      { accessorKey: "level", header: "المستوى" },
      { accessorKey: "logger", header: "المكوّن" },
      { accessorKey: "detail", header: "التفاصيل" },
    ],
    []
  );

  const backupColumns = useMemo(
    () => [
      { accessorKey: "label", header: "النسخة" },
      { accessorKey: "created_at", header: "تاريخ الإنشاء" },
      {
        accessorKey: "archive",
        header: "الحجم",
        cell: ({ row }) => formatBytes(row.original.archive?.size_bytes),
      },
      {
        accessorKey: "includes",
        header: "المحتويات",
        cell: ({ row }) => (row.original.includes || []).map((item) => item.label).join(" | ") || "-",
      },
      {
        accessorKey: "warnings",
        header: "تنبيهات",
        cell: ({ row }) => (row.original.warnings || []).join(" | ") || "-",
      },
    ],
    []
  );

  const appTailText = useMemo(
    () => (logs?.app_tail || []).join("\n").trim(),
    [logs]
  );

  return (
    <PageFrame
      title="مركز العمليات"
      description="جاهزية الدومين وSSL، مراقبة اللوجات، وحالة النسخ الاحتياطية في لوحة تشغيل واحدة مناسبة للإنتاج."
      eyebrow="المنصة"
      headerActions={<StatusBadge label={refreshing ? "جارٍ التحديث" : "جاهزية نشر"} tone="accent" />}
    >
      <div className="panel result-panel">
        <SectionHeader
          title="جاهزية الدومين وSSL"
          description="ملخص سريع لإعدادات reverse proxy والدومين والنشر نفسه."
        />
        <ErrorBanner message={error} />
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : overview ? (
          <>
            <SummaryStrip
              items={[
                { label: "اسم الخادم", value: overview.deployment?.server_name || "غير مهيأ" },
                { label: "رابط الويب العام", value: overview.deployment?.public_web_origin || "نفس النطاق" },
                { label: "رابط API العام", value: overview.deployment?.public_api_origin || "نفس النطاق" },
                { label: "رؤوس البروكسي", value: overview.deployment?.proxy_headers_enabled ? "مفعلة" : "معطلة" },
                { label: "المضيفون الموثوقون", value: (overview.deployment?.trusted_hosts || []).length || 0 },
                { label: "طبقة HTTPS", value: overview.deployment?.https_termination_mode || "بروكسي عكسي خارجي" },
              ]}
            />
            <SummaryStrip
              items={[
                { label: "الدور النشط", value: overview.control_plane?.process?.server_role || "-" },
                { label: "نمط العملية", value: overview.control_plane?.process?.process_mode || "-" },
                { label: "المجدول", value: overview.control_plane?.orchestration?.scheduler?.runtime_state || "-" },
                { label: "التعلم المستمر", value: overview.control_plane?.orchestration?.continuous_learning?.runtime_state || "-" },
                { label: "قاعدة البيانات", value: overview.control_plane?.storage?.database?.path || overview.control_plane?.storage?.database?.driver || "-" },
                { label: "الكاش", value: overview.control_plane?.cache?.provider || "-" },
              ]}
            />
            <div className="status-message">
              ملف البيئة: {overview.control_plane?.environment_bootstrap?.env_file_path || "غير متاح"} | النمط: {overview.control_plane?.environment_bootstrap?.mode || "غير متاح"}.
            </div>
            <div className="ops-note-grid">
              {(overview.deployment?.notes || []).map((note, index) => (
                <div className="status-message" key={`ops-note-${index}`}>{note}</div>
              ))}
            </div>
          </>
        ) : null}
      </div>

      <div className="panel result-panel">
        <SectionHeader
          title="مراقبة اللوجات"
          description="آخر الأحداث التشغيلية المهمة حول الإقلاع، الجاهزية، التدريب، الأتمتة، والاتصال بالوسيط."
        />
        {loading ? (
          <LoadingSkeleton lines={7} />
        ) : (
          <>
            <SummaryStrip
              items={[
                { label: "سجل التطبيق", value: formatBytes(overview?.logs?.app?.size_bytes), badge: "app.log" },
                { label: "سجل الأحداث", value: formatBytes(overview?.logs?.events?.size_bytes), badge: "events.jsonl" },
                { label: "آخر تعديل", value: overview?.logs?.events?.modified_at || overview?.logs?.app?.modified_at || "-" },
                { label: "أحداث معروضة", value: eventRows.length, badge: "لوحة المتابعة" },
              ]}
            />
            <DataTable
              columns={eventColumns}
              data={eventRows}
              emptyTitle="لا توجد أحداث تشغيلية بعد"
              emptyDescription="ستظهر هنا أحداث الإقلاع والجاهزية والتدريب والأتمتة والأخطاء التشغيلية."
            />
            <div className="log-tail-block">
              <div className="log-tail-header">
                <strong>آخر سطور `app.log`</strong>
                <span>عرض سريع لتشخيص الإقلاع والأخطاء بدون مغادرة الواجهة</span>
              </div>
              <pre className="log-tail-pre">{appTailText || "لا توجد أسطر سجل بعد."}</pre>
            </div>
          </>
        )}
      </div>

      <div className="panel result-panel">
        <SectionHeader
          title="النسخ الاحتياطية"
          description="ملفات النسخ الاحتياطي الجاهزة للاستعادة، مع إبقاء مفتاح التشفير خارج النسخة افتراضياً."
          badge={<button className="secondary-button" type="button" onClick={() => loadAll(true)} disabled={refreshing}>تحديث الحالة</button>}
        />
        {loading ? (
          <LoadingSkeleton lines={6} />
        ) : (
          <>
            <SummaryStrip
              items={[
                { label: "مجلد النسخ", value: overview?.paths?.backups_dir || "-" },
                { label: "عدد النسخ", value: overview?.backups?.count ?? 0 },
                { label: "قاعدة البيانات", value: overview?.paths?.data_dir || "-" },
                { label: "مخرجات التدريب", value: overview?.paths?.model_artifacts_dir || "-" },
              ]}
            />
            <DataTable
              columns={backupColumns}
              data={overview?.backups?.items || []}
              emptyTitle="لا توجد نسخ احتياطية بعد"
              emptyDescription="شغّل scripts/backup_runtime.py على الخادم أو ضمن cron/systemd لإنشاء أول نسخة."
            />
            <div className="ops-note-grid">
              <div className="status-message warning">المفاتيح السرية لا تُحفظ بشكل مكشوف داخل النسخة. استرجاع أسرار OpenAI وAlpaca يتطلب إما إعادة إدخالها من الواجهة أو إدارة منفصلة وآمنة لمفتاح التشفير.</div>
              <div className="status-message">الأوامر المقترحة: `python scripts/backup_runtime.py --include-logs` للنسخ، و`python scripts/restore_runtime.py backups/[archive].tar.gz --force` للاستعادة داخل بيئة صيانة.</div>
            </div>
          </>
        )}
      </div>
    </PageFrame>
  );
}
