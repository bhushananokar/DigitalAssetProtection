"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import type { ViolationsStats } from "@/lib/types";

export function OverviewClient({ stats, anomalyCount }: { stats: ViolationsStats; anomalyCount: number }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        {[
          ["Total Violations", stats.total_violations],
          ["Open Violations", stats.open_violations],
          ["Critical Violations", stats.critical_violations],
          ["Anomaly-Flagged count", anomalyCount],
        ].map(([title, value]) => (
          <div key={title} className="card">
            <p className="text-sm" style={{ color: "var(--muted)" }}>{title}</p>
            <p className="mt-2 text-2xl font-semibold">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-3 text-sm font-medium">Violations by Severity</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[
                  { severity: "low", count: stats.violations_by_severity.low, fill: "#a1a1aa" },
                  { severity: "medium", count: stats.violations_by_severity.medium, fill: "#eab308" },
                  { severity: "high", count: stats.violations_by_severity.high, fill: "#f97316" },
                  { severity: "critical", count: stats.violations_by_severity.critical, fill: "#ef4444" },
                ]}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="severity" stroke="var(--muted)" />
                <YAxis stroke="var(--muted)" />
                <Bar dataKey="count" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card">
          <h3 className="mb-3 text-sm font-medium">Violations Over Time</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stats.violations_over_time}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" stroke="var(--muted)" />
                <YAxis stroke="var(--muted)" />
                <Line dataKey="count" stroke="#60a5fa" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-3 text-sm font-medium">Top Affected Assets</h3>
          <table className="w-full text-sm">
            <thead style={{ color: "var(--muted)" }}>
              <tr>
                <th className="pb-2 text-left">Asset Name</th>
                <th className="pb-2 text-left">Violation Count</th>
              </tr>
            </thead>
            <tbody>
              {stats.top_affected_assets.map((a) => (
                <tr key={a.asset_id} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="py-2">{a.asset_name}</td>
                  <td className="py-2">{a.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card">
          <h3 className="mb-3 text-sm font-medium">Violations by Platform</h3>
          <div className="space-y-2">
            {stats.violations_by_platform.map((p) => (
              <div key={p.platform}>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{p.platform}</span>
                  <span>{p.count}</span>
                </div>
                <div className="h-2 rounded" style={{ background: "var(--border)" }}>
                  <div className="h-2 rounded bg-blue-500" style={{ width: `${Math.min(100, p.count)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
