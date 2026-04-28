import { BigQuery } from "@google-cloud/bigquery";
import { canUseBigQuery, config } from "./config.js";
import type { ScanJob } from "./types.js";

interface JobStore {
  createJob(job: ScanJob): Promise<void>;
  updateJob(jobId: string, updater: (current: ScanJob) => ScanJob): Promise<void>;
  listJobs(orgId: string, limit: number): Promise<ScanJob[]>;
  getJob(jobId: string): Promise<ScanJob | null>;
  isUrlScannedRecently(url: string, orgId: string): Promise<boolean>;
  markUrlScanned(url: string, orgId: string): Promise<void>;
}

class InMemoryStore implements JobStore {
  private jobs = new Map<string, ScanJob>();
  private dedup = new Map<string, number>();
  private readonly dedupWindowMs = 86_400_000;

  async createJob(job: ScanJob): Promise<void> {
    this.jobs.set(job.job_id, job);
  }

  async updateJob(jobId: string, updater: (current: ScanJob) => ScanJob): Promise<void> {
    const current = this.jobs.get(jobId);
    if (!current) return;
    this.jobs.set(jobId, updater(current));
  }

  async listJobs(orgId: string, limit: number): Promise<ScanJob[]> {
    return Array.from(this.jobs.values())
      .filter((job) => job.org_id === orgId)
      .sort((a, b) => new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime())
      .slice(0, limit);
  }

  async getJob(jobId: string): Promise<ScanJob | null> {
    return this.jobs.get(jobId) ?? null;
  }

  async isUrlScannedRecently(url: string, orgId: string): Promise<boolean> {
    const key = `${url}::${orgId}`;
    const ts = this.dedup.get(key);
    if (!ts) return false;
    return Date.now() - ts < this.dedupWindowMs;
  }

  async markUrlScanned(url: string, orgId: string): Promise<void> {
    this.dedup.set(`${url}::${orgId}`, Date.now());
  }
}

class BigQueryStore extends InMemoryStore {
  private client: BigQuery;
  private dataset: string;

  constructor() {
    super();
    this.client = new BigQuery({ projectId: config.bigQueryProjectId });
    this.dataset = config.bigQueryDataset;
  }

  async createJob(job: ScanJob): Promise<void> {
    await super.createJob(job);
    await this.client.dataset(this.dataset).table("scan_jobs").insert([job]);
  }

  async updateJob(jobId: string, updater: (current: ScanJob) => ScanJob): Promise<void> {
    await super.updateJob(jobId, updater);
    const updated = await super.getJob(jobId);
    if (!updated) return;
    const query = `
      UPDATE \`${config.bigQueryProjectId}.${this.dataset}.scan_jobs\`
      SET status = @status, completed_at = @completed_at, urls_scanned = @urls_scanned,
          matches_found = @matches_found, errors = @errors
      WHERE job_id = @job_id
    `;
    await this.client.query({
      query,
      params: {
        job_id: updated.job_id,
        status: updated.status,
        completed_at: updated.completed_at,
        urls_scanned: updated.urls_scanned,
        matches_found: updated.matches_found,
        errors: updated.errors,
      },
    });
  }

  async listJobs(orgId: string, limit: number): Promise<ScanJob[]> {
    const query = `
      SELECT job_id, org_id, triggered_at, completed_at, status, urls_scanned, matches_found, errors
      FROM \`${config.bigQueryProjectId}.${this.dataset}.scan_jobs\`
      WHERE org_id = @org_id
      ORDER BY triggered_at DESC
      LIMIT @limit
    `;
    const [rows] = await this.client.query({ query, params: { org_id: orgId, limit } });
    return rows as ScanJob[];
  }

  async getJob(jobId: string): Promise<ScanJob | null> {
    const query = `
      SELECT job_id, org_id, triggered_at, completed_at, status, urls_scanned, matches_found, errors
      FROM \`${config.bigQueryProjectId}.${this.dataset}.scan_jobs\`
      WHERE job_id = @job_id
      LIMIT 1
    `;
    const [rows] = await this.client.query({ query, params: { job_id: jobId } });
    if (!rows.length) return null;
    return rows[0] as ScanJob;
  }

  async isUrlScannedRecently(url: string, orgId: string): Promise<boolean> {
    const query = `
      SELECT 1
      FROM \`${config.bigQueryProjectId}.${this.dataset}.scanned_urls\`
      WHERE url = @url
        AND org_id = @org_id
        AND scanned_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
      LIMIT 1
    `;
    const [rows] = await this.client.query({ query, params: { url, org_id: orgId } });
    return rows.length > 0;
  }

  async markUrlScanned(url: string, orgId: string): Promise<void> {
    await this.client
      .dataset(this.dataset)
      .table("scanned_urls")
      .insert([{ url, org_id: orgId, scanned_at: new Date().toISOString() }]);
  }
}

export const store: JobStore = canUseBigQuery ? new BigQueryStore() : new InMemoryStore();
