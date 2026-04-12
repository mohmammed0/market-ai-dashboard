import { getJson } from "./client";


export async function fetchJobs(params = {}, options = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.set("limit", String(params.limit));
  if (params.type) query.set("type", String(params.type));
  if (params.status) query.set("status", String(params.status));
  return getJson(`/api/jobs${query.size ? `?${query.toString()}` : ""}`, {
    cacheTtlMs: options.cacheTtlMs ?? 1200,
    forceFresh: Boolean(options.forceFresh),
    signal: options.signal,
  });
}


export async function fetchJob(jobId, options = {}) {
  return getJson(`/api/jobs/${encodeURIComponent(jobId)}`, {
    cacheTtlMs: options.cacheTtlMs ?? 0,
    forceFresh: Boolean(options.forceFresh),
    signal: options.signal,
  });
}
