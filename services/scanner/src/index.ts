import express from "express";
import { v4 as uuidv4 } from "uuid";
import { config } from "./config.js";
import { runWebScan, runYouTubeScan } from "./scanners.js";
import { store } from "./store.js";
import type { RunScanBody, ScanJob } from "./types.js";

export const app = express();

app.use((req, res, next) => {
  const started = Date.now();
  res.on("finish", () => {
    const durationMs = Date.now() - started;
    console.log(`[scanner] ${req.method} ${req.path} status=${res.statusCode} duration_ms=${durationMs}`);
  });
  next();
});

app.use((req, res, next) => {
  res.header("Access-Control-Allow-Origin", "*");
  res.header("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  res.header("Access-Control-Allow-Headers", "Content-Type, Authorization");
  if (req.method === "OPTIONS") {
    return res.sendStatus(204);
  }
  next();
});

app.use(express.json());

app.get("/healthz", (_req, res) => {
  res.json({ ok: true });
});

app.post("/scanner/run", async (req, res) => {
  const body = req.body as RunScanBody;
  if (!body?.org_id || !Array.isArray(body.keywords) || !Array.isArray(body.platforms)) {
    return res.status(400).json({
      error: true,
      code: "INVALID_REQUEST",
      message: "org_id, keywords, and platforms are required",
      status: 400,
    });
  }
  if (!body.platforms.length || body.platforms.some((platform) => platform !== "youtube" && platform !== "web")) {
    return res.status(400).json({
      error: true,
      code: "INVALID_REQUEST",
      message: "platforms must include one or both of: youtube, web",
      status: 400,
    });
  }

  const job: ScanJob = {
    job_id: uuidv4(),
    org_id: body.org_id,
    triggered_at: new Date().toISOString(),
    completed_at: null,
    status: "running",
    urls_scanned: 0,
    matches_found: 0,
    errors: [],
  };

  await store.createJob(job);

  res.json({
    job_id: job.job_id,
    status: "started",
    triggered_at: job.triggered_at,
  });

  void (async () => {
    try {
      const tasks: Array<Promise<void>> = [];
      if (body.platforms.includes("youtube")) {
        tasks.push(
          runYouTubeScan({ orgId: body.org_id, keywords: body.keywords, job }).catch((error) => {
            job.errors.push(error instanceof Error ? error.message : "YouTube scan failed");
            throw error;
          }),
        );
      }
      if (body.platforms.includes("web")) {
        tasks.push(runWebScan({ orgId: body.org_id, keywords: body.keywords, job }));
      }

      await Promise.all(tasks);
      job.status = job.status === "failed" ? "failed" : "completed";
      job.completed_at = new Date().toISOString();
      await store.updateJob(job.job_id, () => ({ ...job }));
    } catch (error) {
      job.status = "failed";
      job.completed_at = new Date().toISOString();
      job.errors.push(error instanceof Error ? error.message : "Unhandled scan error");
      await store.updateJob(job.job_id, () => ({ ...job }));
    }
  })();
});

app.get("/scanner/jobs", async (req, res) => {
  const orgId = String(req.query.org_id ?? "");
  const limit = Number(req.query.limit ?? 20);
  if (!orgId) {
    return res.status(400).json({
      error: true,
      code: "INVALID_REQUEST",
      message: "org_id is required",
      status: 400,
    });
  }

  const jobs = await store.listJobs(orgId, limit);
  return res.json({
    jobs: jobs.map((job) => ({
      job_id: job.job_id,
      triggered_at: job.triggered_at,
      status: job.status,
      urls_scanned: job.urls_scanned,
      matches_found: job.matches_found,
    })),
  });
});

app.get("/scanner/jobs/:job_id", async (req, res) => {
  const jobId = req.params.job_id;
  const job = await store.getJob(jobId);
  if (!job) {
    return res.status(404).json({
      error: true,
      code: "JOB_NOT_FOUND",
      message: "Scan job not found",
      status: 404,
    });
  }
  return res.json({
    job_id: job.job_id,
    status: job.status,
    triggered_at: job.triggered_at,
    completed_at: job.completed_at,
    urls_scanned: job.urls_scanned,
    matches_found: job.matches_found,
    errors: job.errors,
  });
});

if (process.env.NODE_ENV !== "test") {
  app.listen(config.port, () => {
    console.log(`Scanner service listening on ${config.port}`);
  });
}
