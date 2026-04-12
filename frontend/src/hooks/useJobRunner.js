import { useCallback, useEffect, useRef, useState } from "react";

import { fetchJob, fetchJobs } from "../api/jobs";


const ACTIVE_JOB_STATUSES = new Set(["pending", "running"]);

const getPollInterval = (pollCount) => {
  if (pollCount < 15) return 2000;
  if (pollCount < 30) return 4000;
  return 8000;
};

const MAX_POLLS = 150;


export default function useJobRunner(jobType, options = {}) {
  const {
    recentLimit = 6,
    pollIntervalMs = 2000,
    autoLoadRecent = true,
  } = options;
  const [currentJob, setCurrentJob] = useState(null);
  const [recentJobs, setRecentJobs] = useState([]);
  const [loadingRecent, setLoadingRecent] = useState(autoLoadRecent);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const lastTerminalRefreshRef = useRef("");
  const pollCountRef = useRef(0);

  const refreshRecentJobs = useCallback(async (override = {}) => {
    if (!jobType && !override.type) {
      setRecentJobs([]);
      setLoadingRecent(false);
      return { items: [], count: 0 };
    }
    setLoadingRecent(true);
    try {
      const payload = await fetchJobs(
        {
          limit: recentLimit,
          type: override.type || jobType,
          status: override.status,
        },
        { forceFresh: true, cacheTtlMs: 0 }
      );
      setRecentJobs(payload?.items || []);
      return payload;
    } catch (requestError) {
      setError(requestError.message || "تعذر تحميل سجل المهام.");
      throw requestError;
    } finally {
      setLoadingRecent(false);
    }
  }, [jobType, recentLimit]);

  const submit = useCallback(async (launcher) => {
    setSubmitting(true);
    setError("");
    try {
      const payload = await launcher();
      if (payload?.job_id) {
        setCurrentJob(payload);
        pollCountRef.current = 0;
      } else if (payload) {
        setCurrentJob({
          job_id: `local-${Date.now()}`,
          status: "completed",
          progress: 100,
          result: payload,
          result_summary: payload?.summary || null,
        });
      } else {
        setCurrentJob(null);
      }
      refreshRecentJobs().catch(() => {});
      return payload;
    } catch (requestError) {
      setError(requestError.message || "تعذر إرسال المهمة.");
      throw requestError;
    } finally {
      setSubmitting(false);
    }
  }, [refreshRecentJobs]);

  useEffect(() => {
    if (!autoLoadRecent) {
      return;
    }
    refreshRecentJobs().catch(() => {});
  }, [autoLoadRecent, refreshRecentJobs]);

  useEffect(() => {
    if (!currentJob?.job_id || !ACTIVE_JOB_STATUSES.has(String(currentJob.status || "").toLowerCase())) {
      return undefined;
    }

    let cancelled = false;
    const timer = window.setInterval(async () => {
      pollCountRef.current += 1;
      if (pollCountRef.current > MAX_POLLS) {
        cancelled = true;
        window.clearInterval(timer);
        setError("المهمة تجاوزت الوقت المتوقع. تحقق من صفحة العمليات.");
        return;
      }
      try {
        const payload = await fetchJob(currentJob.job_id, { forceFresh: true });
        if (!cancelled) {
          setCurrentJob(payload);
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError.message || "تعذر تتبع حالة المهمة.");
        }
      }
    }, getPollInterval(pollCountRef.current));

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [currentJob?.job_id, currentJob?.status]);

  useEffect(() => {
    if (!currentJob?.job_id) {
      return;
    }
    const normalizedStatus = String(currentJob.status || "").toLowerCase();
    if (ACTIVE_JOB_STATUSES.has(normalizedStatus)) {
      return;
    }
    const refreshKey = `${currentJob.job_id}:${normalizedStatus}`;
    if (lastTerminalRefreshRef.current === refreshKey) {
      return;
    }
    lastTerminalRefreshRef.current = refreshKey;
    refreshRecentJobs().catch(() => {});
  }, [currentJob?.job_id, currentJob?.status, refreshRecentJobs]);

  return {
    currentJob,
    recentJobs,
    loadingRecent,
    submitting,
    error,
    setError,
    setCurrentJob,
    clearCurrentJob: () => setCurrentJob(null),
    refreshRecentJobs,
    submit,
  };
}
