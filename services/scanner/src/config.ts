import dotenv from "dotenv";
import path from "node:path";

// Single source of truth: shared repo-root setup.env only.
const scannerRoot = process.cwd();
const sharedSetupEnv = path.resolve(scannerRoot, "../../setup.env");
dotenv.config({ path: sharedSetupEnv, override: true });

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

export const config = {
  port: Number(process.env.PORT ?? 3003),
  youtubeApiKey: process.env.YOUTUBE_API_KEY ?? "",
  customSearchApiKey: process.env.CUSTOM_SEARCH_API_KEY ?? "",
  customSearchCx: process.env.CUSTOM_SEARCH_CX ?? "",
  matchingServiceUrl: required("MATCHING_SERVICE_URL"),
  bigQueryProjectId: process.env.BIGQUERY_PROJECT_ID ?? process.env.GCP_PROJECT_ID ?? "",
  bigQueryDataset: process.env.BIGQUERY_DATASET ?? process.env.BQ_DATASET ?? "",
};

export const canUseBigQuery =
  Boolean(config.bigQueryProjectId) && Boolean(config.bigQueryDataset);
