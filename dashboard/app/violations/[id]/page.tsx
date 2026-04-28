"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ApiRequestError } from "@/lib/api/client";
import { getViolation, updateViolationStatus } from "@/lib/api/violations";
import type { ViolationDetail, ViolationStatus } from "@/lib/types";

const scoreColor = (score: number) => (score >= 0.85 ? "text-red-400" : score >= 0.7 ? "text-orange-400" : "text-zinc-300");
const severityBadge: Record<string, string> = {
  low: "bg-zinc-700 text-zinc-100",
  medium: "bg-yellow-600 text-black",
  high: "bg-orange-600 text-white",
  critical: "bg-red-600 text-white",
};

export default function ViolationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<ViolationDetail | null>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState<ViolationStatus | null>(null);

  const load = () => getViolation(id).then(setItem);

  useEffect(() => {
    load();
  }, [id]);

  const mutate = async (status: ViolationStatus) => {
    try {
      setSaving(status);
      await updateViolationStatus(id, status, note || undefined);
      await load();
      toast.success("Status updated");
    } catch (error) {
      const e = error as ApiRequestError;
      toast.error(e.message);
    } finally {
      setSaving(null);
    }
  };

  if (!item) return <div className="card animate-pulse">Loading violation details...</div>;

  return (
    <ErrorBoundary>
      <Link href="/violations" className="mb-4 inline-block text-sm" style={{ color: "var(--primary)" }}>Back to violations</Link>
      <div className="card">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-xl font-semibold">{item.asset_name}</h2>
            <p className="text-sm" style={{ color: "var(--muted)" }}>{item.violation_id}</p>
          </div>
          <div className={`text-4xl font-bold ${scoreColor(item.similarity_score)}`}>{(item.similarity_score * 100).toFixed(1)}%</div>
        </div>
        <div className="grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
          <p>Platform: {item.platform}</p>
          <p>
            Severity: <span className={`rounded px-2 py-1 text-xs ${severityBadge[item.severity] ?? "bg-zinc-700 text-zinc-100"}`}>{item.severity}</span>
          </p>
          <p>Status: <span className="rounded bg-zinc-700 px-2 py-1 text-xs">{item.status}</span></p>
          <p>Anomaly: {item.anomaly_flagged ? "Yes" : "No"}</p>
          <a href={item.source_url} className="underline" style={{ color: "var(--primary)" }} target="_blank" rel="noreferrer">Source URL</a>
          <p>Discovered: {new Date(item.discovered_at).toLocaleString()}</p>
        </div>
        {item.evidence_uri ? (
          <div className="mt-4 border-t pt-4" style={{ borderColor: "var(--border)" }}>
            <h3 className="mb-2 font-medium">Evidence</h3>
            <img src={item.evidence?.screenshot_url} alt="evidence" className="mb-2 max-h-72 rounded" />
            <p className="font-mono text-xs">Hash: {item.evidence?.content_hash}</p>
            <p className="text-sm" style={{ color: "var(--muted)" }}>Detection: {new Date(item.evidence?.detection_timestamp).toLocaleString()}</p>
          </div>
        ) : null}
        <textarea className="input mt-4" placeholder="Optional note" value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="mt-3 flex gap-2">
          {(["resolved", "escalated", "dismissed"] as ViolationStatus[]).map((s) => (
            <button key={s} disabled={item.status === s || saving === s} onClick={() => mutate(s)} className="btn-secondary btn">
              {saving === s ? "Saving..." : s[0].toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>
    </ErrorBoundary>
  );
}
