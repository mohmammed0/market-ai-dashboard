import EmptyState from "./EmptyState";
import ErrorBanner from "./ErrorBanner";
import LoadingSkeleton from "./LoadingSkeleton";
import SectionCard from "./SectionCard";
import StatusBadge from "./StatusBadge";
import SummaryStrip from "./SummaryStrip";


function toneForStatus(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "completed") return "accent";
  if (normalized === "failed") return "negative";
  if (normalized === "running") return "warning";
  return "subtle";
}


function labelForType(type) {
  const mapping = {
    backtest_classic: "Backtest",
    backtest_vectorbt: "VectorBT",
    scan_batch: "Scan",
    ranking_scan_batch: "Ranking",
    strategy_evaluation: "Strategy",
    paper_signal_refresh: "Paper Refresh",
    intelligence_infer_batch: "Batch Inference",
  };
  return mapping[String(type || "").trim().toLowerCase()] || type || "Job";
}


function summaryPreview(summary) {
  if (!summary || typeof summary !== "object") {
    return "لا يوجد ملخص بعد.";
  }
  return Object.entries(summary)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${value}`)
    .join(" | ") || "لا يوجد ملخص بعد.";
}


function JobCard({ job }) {
  return (
    <div className="job-card">
      <div className="job-card-topline">
        <div>
          <strong>{labelForType(job.type)}</strong>
          <p>{job.job_id}</p>
        </div>
        <StatusBadge label={job.status || "pending"} tone={toneForStatus(job.status)} />
      </div>
      <div className="job-progress-bar">
        <div className={`job-progress-fill status-${toneForStatus(job.status)}`} style={{ width: `${Math.max(4, Number(job.progress || 0))}%` }} />
      </div>
      <small>{summaryPreview(job.result_summary)}</small>
      {job.error_message ? <div className="status-message error">{job.error_message}</div> : null}
    </div>
  );
}


export default function JobRunPanel({
  title,
  description,
  currentJob,
  recentJobs = [],
  loadingRecent = false,
  submitting = false,
  error = "",
  className = "",
  action,
}) {
  return (
    <SectionCard
      title={title}
      description={description}
      className={className}
      action={action || <StatusBadge label={submitting ? "جارٍ الإرسال" : currentJob?.status || "جاهز"} tone={submitting ? "warning" : toneForStatus(currentJob?.status)} />}
    >
      <ErrorBanner message={error} />
      {submitting && !currentJob ? <div className="status-message">تم قبول الطلب محلياً وجارٍ انتظار معرّف المهمة من الخادم.</div> : null}
      {currentJob ? (
        <div className="job-current-card">
          <SummaryStrip
            compact
            items={[
              { label: "المهمة الحالية", value: labelForType(currentJob.type), badge: currentJob.job_id || "job" },
              { label: "الحالة", value: currentJob.status || "-", tone: toneForStatus(currentJob.status) },
              { label: "التقدم", value: `${Number(currentJob.progress || 0)}%` },
              { label: "المدة", value: currentJob.duration_seconds ?? "-", badge: "ث" },
            ]}
          />
          <div className="job-progress-bar">
            <div className={`job-progress-fill status-${toneForStatus(currentJob.status)}`} style={{ width: `${Math.max(4, Number(currentJob.progress || 0))}%` }} />
          </div>
          {currentJob.result_summary ? <div className="status-message">{summaryPreview(currentJob.result_summary)}</div> : null}
          {currentJob.error_message ? <div className="status-message error">{currentJob.error_message}</div> : null}
        </div>
      ) : null}
      <div className="job-card-list">
        {loadingRecent ? (
          <LoadingSkeleton lines={4} />
        ) : recentJobs.length ? (
          recentJobs.map((job) => <JobCard job={job} key={job.job_id} />)
        ) : (
          <EmptyState title="لا توجد مهام حديثة" description="ستظهر هنا آخر المهام المقبولة أو المكتملة أو الفاشلة لهذا المسار." />
        )}
      </div>
    </SectionCard>
  );
}
