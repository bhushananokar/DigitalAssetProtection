"use client";
import { useEffect, useState } from "react";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { OverviewClient } from "@/components/OverviewClient";
import { apiRequest } from "@/lib/api/client";
import type { ViolationsStats } from "@/lib/types";

export default function Home() {
  const [stats, setStats] = useState<ViolationsStats | null>(null);
  const [anomalyCount, setAnomalyCount] = useState(0);
  useEffect(() => {
    const toDate = new Date();
    const fromDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
    const search = new URLSearchParams({
      org_id: "demo-org",
      from_date: fromDate.toISOString().slice(0, 10),
      to_date: toDate.toISOString().slice(0, 10),
    });
    apiRequest<ViolationsStats>(`/api/violations/stats?${search.toString()}`)
      .then((payload) => {
        // #region agent log
        fetch("http://127.0.0.1:7578/ingest/a77b7fa5-1608-4fab-928b-0a39f4afb14f", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "1309cd" },
          body: JSON.stringify({
            sessionId: "1309cd",
            runId: "pre-fix-shape",
            hypothesisId: "H6",
            location: "dashboard/app/page.tsx:21",
            message: "home_stats_payload_received",
            data: {
              keys: payload ? Object.keys(payload as Record<string, unknown>) : [],
              hasViolationsBySeverity: Boolean((payload as any)?.violations_by_severity),
              hasCountBySeverity: Boolean((payload as any)?.count_by_severity),
            },
            timestamp: Date.now(),
          }),
        }).catch(() => {});
        // #endregion
        setStats(payload);
      })
      .catch((error) => {
        // #region agent log
        fetch("http://127.0.0.1:7578/ingest/a77b7fa5-1608-4fab-928b-0a39f4afb14f", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "1309cd" },
          body: JSON.stringify({
            sessionId: "1309cd",
            runId: "pre-fix-shape",
            hypothesisId: "H6",
            location: "dashboard/app/page.tsx:42",
            message: "home_stats_payload_error",
            data: { message: error instanceof Error ? error.message : String(error) },
            timestamp: Date.now(),
          }),
        }).catch(() => {});
        // #endregion
      });
    apiRequest<{ total: number }>(`/api/violations/anomaly-count?org_id=demo-org`)
      .then((result) => setAnomalyCount(result.total))
      .catch(() => setAnomalyCount(0));
  }, []);
  return (
    <ErrorBoundary>
      <h2 className="mb-6 text-2xl font-semibold">Overview</h2>
      {stats ? (
        <OverviewClient stats={stats} anomalyCount={anomalyCount} />
      ) : (
        <div className="card animate-pulse">Loading dashboard insights...</div>
      )}
    </ErrorBoundary>
  );
}
