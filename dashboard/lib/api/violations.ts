import { apiRequest } from "@/lib/api/client";
import type { ViolationDetail, ViolationStatus, ViolationSummary, ViolationsStats } from "@/lib/types";

const base = process.env.NEXT_PUBLIC_VIOLATIONS_URL ?? "";

export function getViolationsStats(orgId: string, fromDate?: string, toDate?: string) {
  const params = new URLSearchParams({ org_id: orgId });
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  return apiRequest<ViolationsStats>(`${base}/violations/stats?${params.toString()}`, {
    next: { revalidate: 60 },
  });
}

export function getViolations(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  return apiRequest<{ violations: ViolationSummary[]; total: number; page: number }>(
    `${base}/violations?${search.toString()}`,
  );
}

export function getViolation(violationId: string) {
  return apiRequest<ViolationDetail>(`${base}/violations/${violationId}`);
}

export function updateViolationStatus(violationId: string, status: ViolationStatus, note?: string) {
  return apiRequest<{ violation_id: string; status: string; updated_at: string }>(
    `${base}/violations/${violationId}/status`,
    {
      method: "PATCH",
      body: { status, note },
    },
  );
}
