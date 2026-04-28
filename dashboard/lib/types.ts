export type Severity = "low" | "medium" | "high" | "critical";
export type ViolationStatus = "open" | "resolved" | "escalated" | "dismissed";
export type Confidence = "high" | "medium" | "low";
export type FingerprintStatus = "pending" | "ready" | "failed";
export type AssetType = "video" | "image" | "graphic";
export type JobStatus = "running" | "completed" | "failed";

export interface ViolationSummary {
  violation_id: string;
  source_url: string;
  discovered_at: string;
  matched_asset_id: string;
  similarity_score: number;
  severity: Severity;
  platform: string;
  anomaly_flagged: boolean;
  status: ViolationStatus;
  evidence_uri: string;
}

export interface ViolationDetail extends ViolationSummary {
  asset_name: string;
  evidence: { screenshot_url: string; content_hash: string; detection_timestamp: string };
}

export interface ViolationsStats {
  total_violations: number;
  open_violations: number;
  critical_violations: number;
  violations_by_severity: { low: number; medium: number; high: number; critical: number };
  violations_by_platform: { platform: string; count: number }[];
  violations_over_time: { date: string; count: number }[];
  top_affected_assets: { asset_id: string; asset_name: string; count: number }[];
}

export interface AssetSummary {
  asset_id: string;
  asset_type: AssetType;
  event_name: string;
  upload_timestamp: string;
  fingerprint_status: FingerprintStatus;
}

export interface AssetDetail extends AssetSummary {
  org_id: string;
  storage_uri: string;
  violation_count: number;
}

export interface ScanJob {
  job_id: string;
  triggered_at: string;
  status: JobStatus;
  urls_scanned: number;
  matches_found: number;
}

export interface ScanJobDetail extends ScanJob {
  completed_at: string | null;
  errors: string[];
}

export interface FingerprintMatch {
  asset_id: string;
  asset_name: string;
  similarity_score: number;
  confidence: Confidence;
}

export interface FingerprintMatchResponse {
  matched: boolean;
  matches: FingerprintMatch[];
}

export interface ApiError {
  error: true;
  code: string;
  message: string;
  status: number;
}
