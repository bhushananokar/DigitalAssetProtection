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
      .then((payload) => setStats(payload))
      .catch(() => setStats(null));
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
