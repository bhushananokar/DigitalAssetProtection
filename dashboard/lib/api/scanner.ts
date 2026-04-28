import { apiRequest } from "@/lib/api/client";
import type { ScanJob, ScanJobDetail } from "@/lib/types";

const base = process.env.NEXT_PUBLIC_SCANNER_URL ?? "";

export function runScan(body: { org_id: string; keywords: string[]; platforms: ("youtube" | "web")[] }) {
  return apiRequest<{ job_id: string; status: string; triggered_at: string }>(`${base}/scanner/run`, {
    method: "POST",
    body,
  });
}

export function getScanJobs(orgId: string, limit = 20) {
  return apiRequest<{ jobs: ScanJob[] }>(`${base}/scanner/jobs?org_id=${orgId}&limit=${limit}`);
}

export function getScanJob(jobId: string) {
  return apiRequest<ScanJobDetail>(`${base}/scanner/jobs/${jobId}`);
}
