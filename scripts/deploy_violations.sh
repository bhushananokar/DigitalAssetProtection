#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/deploy_violations.sh <service-account-email>

SERVICE_ACCOUNT="${1:-}"
if [[ -z "${SERVICE_ACCOUNT}" ]]; then
  echo "Usage: ./scripts/deploy_violations.sh <service-account-email>"
  exit 1
fi

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
MATCH_TOPIC="${PUBSUB_MATCH_TOPIC:-match-found}"
MATCH_SUB="${PUBSUB_MATCH_SUB:-violations-match-sub}"
HIGH_TOPIC="${PUBSUB_HIGH_SEVERITY_TOPIC:-high-severity-violation}"
DATASET="${BQ_ASSETS_DATASET:-${BQ_DATASET}}"
VIOLATIONS_TABLE="${BQ_VIOLATIONS_TABLE:-violations}"

echo "Validating Pub/Sub resources..."
gcloud pubsub topics describe "${MATCH_TOPIC}" --project "${PROJECT}" >/dev/null 2>&1 || gcloud pubsub topics create "${MATCH_TOPIC}" --project "${PROJECT}"
gcloud pubsub topics describe "${HIGH_TOPIC}" --project "${PROJECT}" >/dev/null 2>&1 || gcloud pubsub topics create "${HIGH_TOPIC}" --project "${PROJECT}"
gcloud pubsub subscriptions describe "${MATCH_SUB}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud pubsub subscriptions create "${MATCH_SUB}" --topic="${MATCH_TOPIC}" --project "${PROJECT}"

echo "Validating BigQuery violations table..."
bq --project_id="${PROJECT}" mk --dataset --location="${REGION}" "${PROJECT}:${DATASET}" >/dev/null 2>&1 || true
bq --project_id="${PROJECT}" query --use_legacy_sql=false "
CREATE TABLE IF NOT EXISTS \`${PROJECT}.${DATASET}.${VIOLATIONS_TABLE}\` (
  violation_id STRING,
  org_id STRING,
  asset_id STRING,
  source_url STRING,
  platform STRING,
  similarity_score FLOAT64,
  severity STRING,
  status STRING,
  note STRING,
  anomaly_flagged BOOL,
  anomaly_type STRING,
  evidence_uri STRING,
  discovered_at TIMESTAMP,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);"

echo "Building violations image..."
gcloud builds submit --project "${PROJECT}" --tag "gcr.io/${PROJECT}/violations-service:latest" -f services/violations/Dockerfile .

echo "Deploying violations API service..."
gcloud run deploy violations-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/violations-service:latest" \
  --set-env-vars "BQ_VIOLATIONS_TABLE=${VIOLATIONS_TABLE},PUBSUB_MATCH_SUB=${MATCH_SUB},PUBSUB_HIGH_SEVERITY_TOPIC=${HIGH_TOPIC},VIOLATIONS_ENABLE_SUBSCRIBER=false" \
  --set-env-vars-file setup.env

echo "Deploying violations subscriber worker service..."
gcloud run deploy violations-subscriber-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --no-allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/violations-service:latest" \
  --set-env-vars "BQ_VIOLATIONS_TABLE=${VIOLATIONS_TABLE},PUBSUB_MATCH_SUB=${MATCH_SUB},PUBSUB_HIGH_SEVERITY_TOPIC=${HIGH_TOPIC}" \
  --set-env-vars-file setup.env \
  --command python \
  --args "-m","services.violations.subscriber"

echo "Violations deploy complete."
