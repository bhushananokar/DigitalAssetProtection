import { apiRequest } from "@/lib/api/client";
import type { FingerprintMatchResponse } from "@/lib/types";

export function checkFingerprintByUrl(sourceUrl: string) {
  return apiRequest<FingerprintMatchResponse>("/api/fingerprint/match", {
    method: "POST",
    body: { source_url: sourceUrl },
  });
}

export function checkFingerprintByFile(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<FingerprintMatchResponse>("/api/fingerprint/match", {
    method: "POST",
    body: formData,
  });
}
