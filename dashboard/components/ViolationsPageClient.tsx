"use client";

import { AlertTriangle } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { getViolations } from "@/lib/api/violations";
import { usePagination } from "@/lib/hooks/usePagination";
import type { ViolationSummary } from "@/lib/types";

const scoreColor = (score: number) => (score >= 0.85 ? "text-red-400" : score >= 0.7 ? "text-orange-400" : "text-zinc-300");
const severityBadge: Record<string, string> = {
  low: "bg-zinc-700 text-zinc-100",
  medium: "bg-yellow-600 text-black",
  high: "bg-orange-600 text-white",
  critical: "bg-red-600 text-white",
};

export function ViolationsPageClient() {
  const params = useSearchParams();
  const router = useRouter();
  const [rows, setRows] = useState<ViolationSummary[]>([]);
  const [total, setTotal] = useState(0);
  const currentPageParam = Number(params.get("page") ?? "1");
  const pagination = usePagination(total, 20, currentPageParam);

  const query = useMemo(
    () => ({
      org_id: "demo-org",
      page: currentPageParam,
      limit: 20,
      severity: params.get("severity") ?? undefined,
      status: params.get("status") ?? undefined,
      platform: params.get("platform") ?? undefined,
      from_date: params.get("from_date") ?? undefined,
      to_date: params.get("to_date") ?? undefined,
      anomaly_flagged: params.get("anomaly_flagged") ?? undefined,
    }),
    [params, currentPageParam],
  );

  useEffect(() => {
    getViolations(query).then((data) => {
      setRows(data.violations);
      setTotal(data.total);
    });
  }, [query]);

  const updateParam = (key: string, value?: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.set("page", "1");
    router.push(`/violations?${next.toString()}`);
  };

  return (
    <ErrorBoundary>
      <h2 className="mb-6 text-2xl font-semibold">Violations</h2>
      <div className="card mb-4 grid grid-cols-2 gap-3 md:grid-cols-6">
        <select className="input" onChange={(e) => updateParam("severity", e.target.value)} defaultValue={params.get("severity") ?? ""}>
          <option value="">Severity</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option>
        </select>
        <select className="input" onChange={(e) => updateParam("status", e.target.value)} defaultValue={params.get("status") ?? ""}>
          <option value="">Status</option><option value="open">Open</option><option value="resolved">Resolved</option><option value="escalated">Escalated</option><option value="dismissed">Dismissed</option>
        </select>
        <input className="input" placeholder="Platform" defaultValue={params.get("platform") ?? ""} onBlur={(e) => updateParam("platform", e.target.value)} />
        <input type="date" className="input" defaultValue={params.get("from_date") ?? ""} onChange={(e) => updateParam("from_date", e.target.value)} />
        <input type="date" className="input" defaultValue={params.get("to_date") ?? ""} onChange={(e) => updateParam("to_date", e.target.value)} />
        <label className="input flex items-center gap-2 text-sm">
          <input type="checkbox" defaultChecked={params.get("anomaly_flagged") === "true"} onChange={(e) => updateParam("anomaly_flagged", e.target.checked ? "true" : "")} />
          Anomaly
        </label>
      </div>
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead style={{ color: "var(--muted)", background: "var(--panel-2)" }}><tr><th className="p-3 text-left">Source URL</th><th className="p-3 text-left">Discovered</th><th className="p-3 text-left">Matched Asset</th><th className="p-3 text-left">Similarity</th><th className="p-3 text-left">Severity</th><th className="p-3 text-left">Platform</th><th className="p-3 text-left">Anomaly</th><th className="p-3 text-left">Status</th></tr></thead>
          <tbody>
            {rows.map((v) => (
              <tr
                key={v.violation_id}
                className="cursor-pointer border-t hover:bg-black/5 dark:hover:bg-white/5"
                style={{ borderColor: "var(--border)" }}
                onClick={() => router.push(`/violations/${v.violation_id}`)}
              >
                <td className="p-3">
                  <a className="text-blue-300" href={v.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                    {v.source_url.slice(0, 40)}...
                  </a>
                </td>
                <td className="p-3">{new Date(v.discovered_at).toLocaleString()}</td>
                <td className="p-3">{v.matched_asset_id}</td>
                <td className={`p-3 font-medium ${scoreColor(v.similarity_score)}`}>{(v.similarity_score * 100).toFixed(1)}%</td>
                <td className="p-3">
                  <span className={`badge ${severityBadge[v.severity] ?? "bg-zinc-700 text-zinc-100"}`}>
                    {v.severity}
                  </span>
                </td>
                <td className="p-3">{v.platform}</td>
                <td className="p-3">{v.anomaly_flagged ? <AlertTriangle className="h-4 w-4 text-yellow-500" /> : null}</td>
                <td className="p-3">
                  <span className="badge" style={{ background: "var(--panel-2)" }}>{v.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex items-center gap-2">
        <button className="btn-secondary btn" disabled={!pagination.hasPrev} onClick={() => updateParam("page", String(currentPageParam - 1))}>Prev</button>
        {pagination.pageNumbers.slice(0, 6).map((n) => (
          <button key={n} className={`btn ${n === currentPageParam ? "btn-primary" : "btn-secondary"}`} onClick={() => updateParam("page", String(n))}>{n}</button>
        ))}
        <button className="btn-secondary btn" disabled={!pagination.hasNext} onClick={() => updateParam("page", String(currentPageParam + 1))}>Next</button>
      </div>
    </ErrorBoundary>
  );
}
