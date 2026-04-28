"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ApiRequestError } from "@/lib/api/client";
import { getScanJob, getScanJobs, runScan } from "@/lib/api/scanner";
import type { ScanJobDetail } from "@/lib/types";
const statusBadge: Record<string, string> = {
  running: "bg-blue-600 text-white animate-pulse",
  completed: "bg-green-600 text-white",
  failed: "bg-red-600 text-white",
};

export default function ScannerPage() {
  const [keywords, setKeywords] = useState<string[]>([]);
  const [keywordInput, setKeywordInput] = useState("");
  const [youtube, setYoutube] = useState(true);
  const [web, setWeb] = useState(true);
  const [running, setRunning] = useState(false);
  const [jobs, setJobs] = useState<ScanJobDetail[]>([]);
  const [selected, setSelected] = useState<ScanJobDetail | null>(null);
  const [lastRun, setLastRun] = useState<{ job_id: string; status: string } | null>(null);

  const load = async () => {
    const data = await getScanJobs("demo-org", 20);
    setJobs((prev) =>
      data.jobs.map((j) => {
        const existing = prev.find((p) => p.job_id === j.job_id);
        return {
          ...j,
          completed_at: existing?.completed_at ?? null,
          errors: existing?.errors ?? [],
        };
      }),
    );
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);

  const addKeyword = () => {
    const k = keywordInput.trim();
    if (!k) return;
    setKeywords((prev) => Array.from(new Set([...prev, k])));
    setKeywordInput("");
  };

  const onRun = async () => {
    if (!youtube && !web) {
      toast.error("Select at least one platform");
      return;
    }
    if (!keywords.length) {
      toast.error("Add at least one keyword");
      return;
    }
    try {
      setRunning(true);
      const result = await runScan({
        org_id: "demo-org",
        keywords,
        platforms: [youtube ? "youtube" : null, web ? "web" : null].filter(Boolean) as ("youtube" | "web")[],
      });
      setLastRun({ job_id: result.job_id, status: result.status });
      toast.success("Scan started");
      await load();
    } catch (error) {
      toast.error((error as ApiRequestError).message);
    } finally {
      setRunning(false);
    }
  };

  const openJob = async (jobId: string) => {
    const detail = await getScanJob(jobId);
    setSelected(detail);
  };

  return (
    <ErrorBoundary>
      <h2 className="mb-6 text-2xl font-semibold">Scanner Control</h2>
      <div className="card mb-4">
        <p className="mb-2 text-sm">org_id</p>
        <input className="input mb-2" value="demo-org" readOnly />
        <div className="mb-2 flex gap-2">
          <input className="input flex-1" value={keywordInput} onChange={(e) => setKeywordInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addKeyword()} placeholder="Type keyword + Enter" />
          <button className="btn-secondary btn" onClick={addKeyword}>Add</button>
        </div>
        <div className="mb-2 flex flex-wrap gap-2">
          {keywords.map((k) => (
            <button key={k} onClick={() => setKeywords((prev) => prev.filter((v) => v !== k))} className="badge" style={{ background: "var(--panel-2)" }}>{k} x</button>
          ))}
        </div>
        <div className="mb-3 flex gap-4 text-sm">
          <label><input type="checkbox" checked={youtube} onChange={(e) => setYoutube(e.target.checked)} /> YouTube</label>
          <label><input type="checkbox" checked={web} onChange={(e) => setWeb(e.target.checked)} /> Web</label>
        </div>
        <button disabled={running} onClick={onRun} className="btn-primary">{running ? "Running..." : "Run Scan"}</button>
        {lastRun ? <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>Last job: {lastRun.job_id} ({lastRun.status})</p> : null}
      </div>
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead style={{ background: "var(--panel-2)", color: "var(--muted)" }}><tr><th className="p-3 text-left">Job ID</th><th className="p-3 text-left">Triggered</th><th className="p-3 text-left">Status</th><th className="p-3 text-left">URLs</th><th className="p-3 text-left">Matches</th></tr></thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.job_id} onClick={() => openJob(job.job_id)} className="cursor-pointer border-t hover:bg-black/5 dark:hover:bg-white/5" style={{ borderColor: "var(--border)" }}>
                <td className="p-3">{job.job_id.slice(0, 8)}</td>
                <td className="p-3">{new Date(job.triggered_at).toLocaleString()}</td>
                <td className="p-3">
                  <span className={`badge ${statusBadge[job.status] ?? "bg-zinc-700 text-zinc-100"}`}>
                    {job.status}
                  </span>
                </td>
                <td className="p-3">{job.urls_scanned}</td>
                <td className="p-3">{job.matches_found}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {selected ? (
        <div className="fixed right-0 top-0 h-full w-full max-w-md border-l p-4" style={{ borderColor: "var(--border)", background: "var(--panel)" }}>
          <button className="btn-secondary btn mb-3" onClick={() => setSelected(null)}>Close</button>
          <h3 className="mb-2 font-medium">{selected.job_id}</h3>
          <p className="text-sm">Status: {selected.status}</p>
          <p className="text-sm">Completed: {selected.completed_at ?? "-"}</p>
          <h4 className="mt-3 text-sm font-medium">Errors</h4>
          <ul className="list-disc pl-5 text-sm" style={{ color: "var(--muted)" }}>{selected.errors.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      ) : null}
    </ErrorBoundary>
  );
}
