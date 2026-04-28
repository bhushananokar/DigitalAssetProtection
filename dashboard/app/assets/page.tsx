"use client";

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { deleteAsset, getAsset, getAssets, uploadAsset } from "@/lib/api/assets";
import { ApiRequestError } from "@/lib/api/client";
import { usePagination } from "@/lib/hooks/usePagination";
import type { AssetSummary, AssetType } from "@/lib/types";

const allowedExt = [".mp4", ".mov", ".jpg", ".png", ".svg"];
type AssetRow = AssetSummary & { violation_count?: number };

export default function AssetsPage() {
  const [rows, setRows] = useState<AssetRow[]>([]);
  const [total, setTotal] = useState(0);
  const [assetType, setAssetType] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [eventName, setEventName] = useState("");
  const [typeInput, setTypeInput] = useState<AssetType>("video");
  const pagination = usePagination(total, 20, 1);

  const query = useMemo(
    () => ({ org_id: "demo-org", page: pagination.currentPage, limit: 20, asset_type: assetType || undefined }),
    [pagination.currentPage, assetType],
  );

  const load = () =>
    getAssets(query).then((data) => {
      const assets = Array.isArray(data.assets) ? data.assets : [];
      setRows(assets);
      setTotal(data.total);
      void Promise.all(
        assets.map(async (asset) => {
          const detail = await getAsset(asset.asset_id);
          setRows((prev) =>
            prev.map((row) =>
              row.asset_id === asset.asset_id ? { ...row, violation_count: detail.violation_count } : row,
            ),
          );
        }),
      );
    });

  useEffect(() => {
    load();
  }, [query]);

  useEffect(() => {
    const pendingIds = new Set(rows.filter((r) => r.fingerprint_status === "pending").map((r) => r.asset_id));
    if (!pendingIds.size) return;
    const timer = setInterval(async () => {
      const ids = Array.from(pendingIds);
      await Promise.all(
        ids.map(async (id) => {
          const detail = await getAsset(id);
          if (detail.fingerprint_status !== "pending") {
            setRows((prev) => prev.map((r) => (r.asset_id === id ? { ...r, fingerprint_status: detail.fingerprint_status } : r)));
            pendingIds.delete(id);
          }
        }),
      );
    }, 10000);
    return () => clearInterval(timer);
  }, [rows]);

  const onUpload = async () => {
    if (!file) return;
    const lowered = file.name.toLowerCase();
    if (!allowedExt.some((ext) => lowered.endsWith(ext))) {
      toast.error("Invalid file type");
      return;
    }
    try {
      setUploading(true);
      const fd = new FormData();
      fd.append("file", file);
      fd.append("org_id", "demo-org");
      fd.append("asset_type", typeInput);
      fd.append("event_name", eventName);
      await uploadAsset(fd);
      toast.success("Asset uploaded");
      setFile(null);
      setEventName("");
      load();
    } catch (error) {
      toast.error((error as ApiRequestError).message);
    } finally {
      setUploading(false);
    }
  };

  const onDelete = async (assetId: string) => {
    const old = rows;
    setRows((prev) => prev.filter((r) => r.asset_id !== assetId));
    try {
      await deleteAsset(assetId);
      toast.success("Asset deleted");
    } catch (error) {
      setRows(old);
      toast.error((error as ApiRequestError).message);
    }
  };

  return (
    <ErrorBoundary>
      <h2 className="mb-6 text-2xl font-semibold">Assets</h2>
      <div className="card mb-4">
        <h3 className="mb-2 text-sm font-medium" style={{ color: "var(--muted)" }}>Upload Asset</h3>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="input" />
          <select value={typeInput} onChange={(e) => setTypeInput(e.target.value as AssetType)} className="input">
            <option value="video">video</option><option value="image">image</option><option value="graphic">graphic</option>
          </select>
          <input value={eventName} onChange={(e) => setEventName(e.target.value)} placeholder="Event name" className="input" />
          <button onClick={onUpload} disabled={uploading} className="btn-primary">{uploading ? "Uploading..." : "Upload"}</button>
        </div>
      </div>
      <div className="mb-4">
        <select className="input max-w-xs" value={assetType} onChange={(e) => setAssetType(e.target.value)}>
          <option value="">All types</option><option value="video">video</option><option value="image">image</option><option value="graphic">graphic</option>
        </select>
      </div>
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead style={{ background: "var(--panel-2)", color: "var(--muted)" }}><tr><th className="p-3 text-left">Asset ID</th><th className="p-3 text-left">Event</th><th className="p-3 text-left">Type</th><th className="p-3 text-left">Uploaded</th><th className="p-3 text-left">Fingerprint</th><th className="p-3 text-left">Violation Count</th><th className="p-3 text-left">Delete</th></tr></thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.asset_id} className="border-t" style={{ borderColor: "var(--border)" }}>
                <td className="p-3">{a.asset_id.slice(0, 10)}...</td>
                <td className="p-3">{a.event_name}</td>
                <td className="p-3"><span className="badge" style={{ background: "var(--panel-2)" }}>{a.asset_type}</span></td>
                <td className="p-3">{new Date(a.upload_timestamp).toLocaleString()}</td>
                <td className="p-3"><span className="badge" style={{ background: "var(--panel-2)" }}>{a.fingerprint_status}</span></td>
                <td className="p-3">{a.violation_count ?? "-"}</td>
                <td className="p-3"><button onClick={() => onDelete(a.asset_id)} className="btn-secondary btn" style={{ color: "var(--danger)" }}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex gap-2">
        <button className="btn-secondary btn" disabled={!pagination.hasPrev} onClick={pagination.prevPage}>Prev</button>
        <span className="btn-secondary btn">{pagination.currentPage}</span>
        <button className="btn-secondary btn" disabled={!pagination.hasNext} onClick={pagination.nextPage}>Next</button>
      </div>
    </ErrorBoundary>
  );
}
