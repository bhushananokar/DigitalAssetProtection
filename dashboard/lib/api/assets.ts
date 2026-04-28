import { apiRequest } from "@/lib/api/client";
import type { AssetDetail, AssetSummary } from "@/lib/types";

const base = process.env.NEXT_PUBLIC_INGEST_URL ?? "";

export function getAssets(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  return apiRequest<{ assets: AssetSummary[]; total: number; page: number }>(`${base}/assets?${search.toString()}`);
}

export function getAsset(assetId: string) {
  return apiRequest<AssetDetail>(`${base}/assets/${assetId}`);
}

export function uploadAsset(formData: FormData) {
  return apiRequest<{ asset_id: string; storage_uri: string; upload_timestamp: string; status: string }>(
    "/api/assets/upload",
    {
      method: "POST",
      body: formData,
    },
  );
}

export function deleteAsset(assetId: string) {
  return apiRequest<{ success: true }>(`${base}/assets/${assetId}`, {
    method: "DELETE",
  });
}
