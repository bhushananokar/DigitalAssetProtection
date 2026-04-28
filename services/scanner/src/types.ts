export type Platform = "youtube" | "web";
export type JobStatus = "running" | "completed" | "failed";

export interface RunScanBody {
  org_id: string;
  keywords: string[];
  platforms: Platform[];
}

export interface ScanJob {
  job_id: string;
  org_id: string;
  triggered_at: string;
  completed_at: string | null;
  status: JobStatus;
  urls_scanned: number;
  matches_found: number;
  errors: string[];
}

export interface MatchResponse {
  matched: boolean;
  matches: Array<{
    asset_id: string;
    asset_name: string;
    similarity_score: number;
    confidence: "high" | "medium" | "low";
  }>;
}
