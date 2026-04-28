"use client";

import { useState } from "react";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { checkFingerprintByFile, checkFingerprintByUrl } from "@/lib/api/fingerprint";
import type { FingerprintMatchResponse } from "@/lib/types";

const scoreColor = (score: number) => (score >= 0.85 ? "text-red-400" : score >= 0.7 ? "text-orange-400" : "text-zinc-300");

export default function CheckPage() {
  const [tab, setTab] = useState<"url" | "file">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FingerprintMatchResponse | null>(null);
  const [error, setError] = useState("");

  const run = async () => {
    setError("");
    setLoading(true);
    setResult(null);
    try {
      const data = tab === "url" ? await checkFingerprintByUrl(url) : await checkFingerprintByFile(file as File);
      setResult(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <ErrorBoundary>
      <h2 className="mb-6 text-2xl font-semibold">Manual Fingerprint Check</h2>
      <div className="mb-4 flex gap-2">
        <button onClick={() => setTab("url")} className={`btn ${tab === "url" ? "btn-primary" : "btn-secondary"}`}>Check by URL</button>
        <button onClick={() => setTab("file")} className={`btn ${tab === "file" ? "btn-primary" : "btn-secondary"}`}>Upload File</button>
      </div>
      <div className="card">
        {tab === "url" ? (
          <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://..." />
        ) : (
          <input type="file" className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        )}
        <button onClick={run} disabled={loading || (tab === "url" ? !url : !file)} className="btn-primary mt-3">
          {loading ? "Analyzing..." : "Analyze"}
        </button>
        {error ? <p className="mt-3 rounded-lg p-2 text-sm" style={{ background: "color-mix(in oklab, var(--danger) 20%, transparent)", color: "var(--danger)" }}>{error}</p> : null}
      </div>
      {loading ? <div className="card mt-4">Analyzing...</div> : null}
      {result ? (
        <div className="card mt-4">
          {!result.matched ? (
            <p>No matches found</p>
          ) : (
            <table className="w-full text-sm">
              <thead style={{ color: "var(--muted)" }}><tr><th className="p-2 text-left">Asset Name</th><th className="p-2 text-left">Similarity Score</th><th className="p-2 text-left">Confidence</th></tr></thead>
              <tbody>
                {result.matches.map((m) => (
                  <tr key={m.asset_id} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="p-2">{m.asset_name}</td>
                    <td className={`p-2 ${scoreColor(m.similarity_score)}`}>{(m.similarity_score * 100).toFixed(1)}%</td>
                    <td className={`p-2 ${m.confidence === "high" ? "text-green-400" : m.confidence === "medium" ? "text-yellow-400" : "text-red-400"}`}>{m.confidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button onClick={() => { setResult(null); setUrl(""); setFile(null); }} className="btn-secondary btn mt-3">Check another</button>
        </div>
      ) : null}
    </ErrorBoundary>
  );
}
