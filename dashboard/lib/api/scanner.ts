import { apiRequest } from "@/lib/api/client";
import type { ScanJob, ScanJobDetail } from "@/lib/types";

const base = "/api/scanner";

export function runScan(body: { org_id: string; keywords: string[]; platforms: ("youtube" | "web")[] }) {
  return apiRequest<{ job_id: string; status: string; triggered_at: string }>(`${base}/run`, {
    method: "POST",
    body,
  });
}

export function getScanJobs(orgId: string, limit = 20) {
  return apiRequest<{ jobs: ScanJob[] }>(`${base}/jobs?org_id=${orgId}&limit=${limit}`);
}

export function getScanJob(jobId: string) {
  return apiRequest<ScanJobDetail>(`${base}/jobs/${jobId}`);
}
