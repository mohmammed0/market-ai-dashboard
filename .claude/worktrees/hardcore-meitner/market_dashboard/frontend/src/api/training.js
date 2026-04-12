import { getJson, postJson } from "./client";

export async function startTrainingJob(payload) {
  return postJson("/api/training/jobs/start", payload);
}

export async function fetchTrainingJobs(limit = 20) {
  return getJson(`/api/training/jobs?limit=${encodeURIComponent(limit)}`);
}

export async function fetchTrainingDashboard(limit = 25) {
  return getJson(`/api/training/dashboard?limit=${encodeURIComponent(limit)}`);
}

export async function fetchTrainingJob(jobId) {
  return getJson(`/api/training/jobs/${encodeURIComponent(jobId)}`);
}
