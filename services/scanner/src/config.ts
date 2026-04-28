import dotenv from "dotenv";

dotenv.config();

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
  bigQueryProjectId: process.env.BIGQUERY_PROJECT_ID ?? "",
  bigQueryDataset: process.env.BIGQUERY_DATASET ?? "",
};

export const canUseBigQuery =
  Boolean(config.bigQueryProjectId) && Boolean(config.bigQueryDataset);
