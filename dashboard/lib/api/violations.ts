import { apiRequest } from "@/lib/api/client";
import type { ViolationDetail, ViolationStatus, ViolationSummary, ViolationsStats } from "@/lib/types";

const base = "/api/violations";

export function getViolationsStats(orgId: string, fromDate?: string, toDate?: string) {
  const params = new URLSearchParams({ org_id: orgId });
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  return apiRequest<ViolationsStats>(`${base}/stats?${params.toString()}`, {
    next: { revalidate: 60 },
  });
}

export function getViolations(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  return apiRequest<{ violations?: ViolationSummary[]; items?: ViolationSummary[]; total?: number; page?: number }>(
    `${base}?${search.toString()}`,
  ).then((payload) => ({
    violations: Array.isArray(payload.violations)
      ? payload.violations
      : Array.isArray(payload.items)
        ? payload.items
        : [],
    total: Number(payload.total ?? 0),
    page: Number(payload.page ?? 1),
  }));
}

export function getViolation(violationId: string) {
  return apiRequest<ViolationDetail>(`${base}/${violationId}`);
}

export function updateViolationStatus(violationId: string, status: ViolationStatus, note?: string) {
  return apiRequest<{ violation_id: string; status: string; updated_at: string }>(
    `${base}/${violationId}/status`,
    {
      method: "PATCH",
      body: { status, note },
    },
  );
}
