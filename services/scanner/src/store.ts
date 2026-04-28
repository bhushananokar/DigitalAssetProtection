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
  private ready: Promise<void>;

  constructor() {
    super();
    this.client = new BigQuery({ projectId: config.bigQueryProjectId });
    this.dataset = config.bigQueryDataset;
    this.ready = this.ensureTables();
  }

  private warnFallback(operation: string, error: unknown): void {
    const message = error instanceof Error ? error.message : String(error);
    console.warn(`[scanner] BigQuery ${operation} failed, using in-memory fallback: ${message}`);
  }

  private isMissingTableError(error: unknown): boolean {
    const message = error instanceof Error ? error.message : String(error);
    return message.includes("Not found: Table");
  }

  private async ensureTables(): Promise<void> {
    const datasetRef = this.client.dataset(this.dataset);
    try {
      const [datasetExists] = await datasetRef.exists();
      if (!datasetExists) {
        this.warnFallback("ensureTables", `Dataset ${this.dataset} not found`);
        return;
      }

      const scanJobs = datasetRef.table("scan_jobs");
      const [scanJobsExists] = await scanJobs.exists();
      if (!scanJobsExists) {
        await datasetRef.createTable("scan_jobs", {
          schema: [
            { name: "job_id", type: "STRING", mode: "REQUIRED" },
            { name: "org_id", type: "STRING", mode: "REQUIRED" },
            { name: "triggered_at", type: "TIMESTAMP", mode: "REQUIRED" },
            { name: "completed_at", type: "TIMESTAMP", mode: "NULLABLE" },
            { name: "status", type: "STRING", mode: "REQUIRED" },
            { name: "urls_scanned", type: "INT64", mode: "REQUIRED" },
            { name: "matches_found", type: "INT64", mode: "REQUIRED" },
            { name: "errors", type: "STRING", mode: "REPEATED" },
          ],
        });
      }

      const scannedUrls = datasetRef.table("scanned_urls");
      const [scannedUrlsExists] = await scannedUrls.exists();
      if (!scannedUrlsExists) {
        await datasetRef.createTable("scanned_urls", {
          schema: [
            { name: "url", type: "STRING", mode: "REQUIRED" },
            { name: "org_id", type: "STRING", mode: "REQUIRED" },
            { name: "scanned_at", type: "TIMESTAMP", mode: "REQUIRED" },
          ],
        });
      }
    } catch (error) {
      this.warnFallback("ensureTables", error);
    }
  }

  async createJob(job: ScanJob): Promise<void> {
    await super.createJob(job);
    await this.ready;
    try {
      await this.client.dataset(this.dataset).table("scan_jobs").insert([job]);
    } catch (error) {
      if (this.isMissingTableError(error)) {
        await this.ensureTables();
        try {
          await this.client.dataset(this.dataset).table("scan_jobs").insert([job]);
          return;
        } catch (retryError) {
          this.warnFallback("createJob", retryError);
          return;
        }
      }
      this.warnFallback("createJob", error);
    }
  }

  async updateJob(jobId: string, updater: (current: ScanJob) => ScanJob): Promise<void> {
    await super.updateJob(jobId, updater);
    await this.ready;
    const updated = await super.getJob(jobId);
    if (!updated) return;
    try {
      // Append latest job snapshot to avoid DML on streaming-buffer rows.
      await this.client.dataset(this.dataset).table("scan_jobs").insert([updated]);
    } catch (error) {
      if (this.isMissingTableError(error)) {
        await this.ensureTables();
        try {
          await this.client.dataset(this.dataset).table("scan_jobs").insert([updated]);
          return;
        } catch (retryError) {
          this.warnFallback("updateJob", retryError);
          return;
        }
      }
      this.warnFallback("updateJob", error);
    }
  }

  async listJobs(orgId: string, limit: number): Promise<ScanJob[]> {
    await this.ready;
    const query = `
      SELECT job_id, org_id, triggered_at, completed_at, status, urls_scanned, matches_found, errors
      FROM (
        SELECT
          job_id,
          org_id,
          triggered_at,
          completed_at,
          status,
          urls_scanned,
          matches_found,
          errors,
          ROW_NUMBER() OVER (
            PARTITION BY job_id
            ORDER BY completed_at DESC NULLS LAST, triggered_at DESC
          ) AS rn
        FROM \`${config.bigQueryProjectId}.${this.dataset}.scan_jobs\`
        WHERE org_id = @org_id
      )
      WHERE rn = 1
      ORDER BY triggered_at DESC
      LIMIT @limit
    `;
    try {
      const [rows] = await this.client.query({ query, params: { org_id: orgId, limit } });
      return rows as ScanJob[];
    } catch (error) {
      if (this.isMissingTableError(error)) {
        await this.ensureTables();
        try {
          const [rows] = await this.client.query({ query, params: { org_id: orgId, limit } });
          return rows as ScanJob[];
        } catch (retryError) {
          this.warnFallback("listJobs", retryError);
          return super.listJobs(orgId, limit);
        }
      }
      this.warnFallback("listJobs", error);
      return super.listJobs(orgId, limit);
    }
  }

  async getJob(jobId: string): Promise<ScanJob | null> {
    await this.ready;
    const query = `
      SELECT job_id, org_id, triggered_at, completed_at, status, urls_scanned, matches_found, errors
      FROM (
        SELECT
          job_id,
          org_id,
          triggered_at,
          completed_at,
          status,
          urls_scanned,
          matches_found,
          errors,
          ROW_NUMBER() OVER (
            PARTITION BY job_id
            ORDER BY completed_at DESC NULLS LAST, triggered_at DESC
          ) AS rn
        FROM \`${config.bigQueryProjectId}.${this.dataset}.scan_jobs\`
        WHERE job_id = @job_id
      )
      WHERE rn = 1
    `;
    try {
      const [rows] = await this.client.query({ query, params: { job_id: jobId } });
      if (!rows.length) return null;
      return rows[0] as ScanJob;
    } catch (error) {
      if (this.isMissingTableError(error)) {
        await this.ensureTables();
      }
      this.warnFallback("getJob", error);
      return super.getJob(jobId);
    }
  }

  async isUrlScannedRecently(url: string, orgId: string): Promise<boolean> {
    await this.ready;
    const query = `
      SELECT 1
      FROM \`${config.bigQueryProjectId}.${this.dataset}.scanned_urls\`
      WHERE url = @url
        AND org_id = @org_id
        AND scanned_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
      LIMIT 1
    `;
    try {
      const [rows] = await this.client.query({ query, params: { url, org_id: orgId } });
      return rows.length > 0;
    } catch (error) {
      if (this.isMissingTableError(error)) {
        await this.ensureTables();
      }
      this.warnFallback("isUrlScannedRecently", error);
      return super.isUrlScannedRecently(url, orgId);
    }
  }

  async markUrlScanned(url: string, orgId: string): Promise<void> {
    await super.markUrlScanned(url, orgId);
    await this.ready;
    try {
      await this.client
        .dataset(this.dataset)
        .table("scanned_urls")
        .insert([{ url, org_id: orgId, scanned_at: new Date().toISOString() }]);
    } catch (error) {
      if (this.isMissingTableError(error)) {
        await this.ensureTables();
        try {
          await this.client
            .dataset(this.dataset)
            .table("scanned_urls")
            .insert([{ url, org_id: orgId, scanned_at: new Date().toISOString() }]);
          return;
        } catch (retryError) {
          this.warnFallback("markUrlScanned", retryError);
          return;
        }
      }
      this.warnFallback("markUrlScanned", error);
    }
  }
}

export const store: JobStore = canUseBigQuery ? new BigQueryStore() : new InMemoryStore();
