#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/deploy_ingest.sh <service-account-email>
# Example:
#   ./scripts/deploy_ingest.sh ingest-runner@my-project.iam.gserviceaccount.com

SERVICE_ACCOUNT="${1:-}"
if [[ -z "${SERVICE_ACCOUNT}" ]]; then
  echo "Usage: ./scripts/deploy_ingest.sh <service-account-email>"
  exit 1
fi

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
ASSETS_DATASET="${BQ_ASSETS_DATASET:-${BQ_DATASET}}"
ASSETS_TABLE="${BQ_ASSETS_TABLE:-assets}"
VIOLATIONS_TABLE="${BQ_VIOLATIONS_TABLE:-violations}"
RAW_BUCKET="${GCS_RAW_BUCKET}"
KEYFRAMES_BUCKET="${GCS_KEYFRAMES_BUCKET:-${GCS_RAW_BUCKET}}"
EVIDENCE_BUCKET="${GCS_EVIDENCE_BUCKET:-${GCS_RAW_BUCKET}}"

echo "Creating/validating storage buckets..."
gcloud storage buckets describe "gs://${RAW_BUCKET}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${RAW_BUCKET}" --project "${PROJECT}" --location "${REGION}" --uniform-bucket-level-access
gcloud storage buckets describe "gs://${KEYFRAMES_BUCKET}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${KEYFRAMES_BUCKET}" --project "${PROJECT}" --location "${REGION}" --uniform-bucket-level-access
gcloud storage buckets describe "gs://${EVIDENCE_BUCKET}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${EVIDENCE_BUCKET}" --project "${PROJECT}" --location "${REGION}" --uniform-bucket-level-access

echo "Creating/validating Pub/Sub topics..."
gcloud pubsub topics describe asset-uploaded --project "${PROJECT}" >/dev/null 2>&1 || gcloud pubsub topics create asset-uploaded --project "${PROJECT}"
gcloud pubsub topics describe match-found --project "${PROJECT}" >/dev/null 2>&1 || gcloud pubsub topics create match-found --project "${PROJECT}"
gcloud pubsub topics describe high-severity-violation --project "${PROJECT}" >/dev/null 2>&1 || gcloud pubsub topics create high-severity-violation --project "${PROJECT}"

echo "Creating/validating BigQuery dataset and tables..."
bq --project_id="${PROJECT}" mk --dataset --location="${REGION}" "${PROJECT}:${ASSETS_DATASET}" >/dev/null 2>&1 || true

bq --project_id="${PROJECT}" query --use_legacy_sql=false "
CREATE TABLE IF NOT EXISTS \`${PROJECT}.${ASSETS_DATASET}.${ASSETS_TABLE}\` (
  asset_id STRING NOT NULL,
  org_id STRING NOT NULL,
  asset_type STRING NOT NULL,
  event_name STRING,
  storage_uri STRING NOT NULL,
  keyframe_uris ARRAY<STRING>,
  fingerprint_status STRING NOT NULL,
  deleted BOOL,
  hard_deleted BOOL,
  created_at TIMESTAMP,
  updated_at TIMESTAMP,
  deleted_at TIMESTAMP
);"

bq --project_id="${PROJECT}" query --use_legacy_sql=false "
CREATE TABLE IF NOT EXISTS \`${PROJECT}.${ASSETS_DATASET}.fingerprints\` (
  fingerprint_id STRING,
  asset_id STRING,
  asset_type STRING,
  embedding ARRAY<FLOAT64>,
  model_version STRING,
  created_at TIMESTAMP
);"

bq --project_id="${PROJECT}" query --use_legacy_sql=false "
CREATE TABLE IF NOT EXISTS \`${PROJECT}.${ASSETS_DATASET}.${VIOLATIONS_TABLE}\` (
  violation_id STRING,
  asset_id STRING,
  source_url STRING,
  platform STRING,
  similarity_score FLOAT64,
  severity STRING,
  status STRING,
  anomaly_flagged BOOL,
  anomaly_type STRING,
  evidence_uri STRING,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);"

echo "Building image..."
gcloud builds submit --project "${PROJECT}" --tag "gcr.io/${PROJECT}/ingest-service:latest" -f services/ingest/Dockerfile .

echo "Deploying Cloud Run ingest-service..."
gcloud run deploy ingest-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/ingest-service:latest" \
  --set-env-vars "GCS_KEYFRAMES_BUCKET=${KEYFRAMES_BUCKET},GCS_EVIDENCE_BUCKET=${EVIDENCE_BUCKET},BQ_VIOLATIONS_TABLE=${VIOLATIONS_TABLE}" \
  --set-env-vars-file setup.env

echo "Ingest deploy complete."
