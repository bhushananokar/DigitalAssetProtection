#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/deploy_alerting.sh <service-account-email>

SERVICE_ACCOUNT="${1:-}"
if [[ -z "${SERVICE_ACCOUNT}" ]]; then
  echo "Usage: ./scripts/deploy_alerting.sh <service-account-email>"
  exit 1
fi

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
TOPIC="${PUBSUB_HIGH_SEVERITY_TOPIC:-high-severity-violation}"
EVIDENCE_BUCKET="${GCS_EVIDENCE_BUCKET:-${GCS_RAW_BUCKET}}"
DATASET="${BQ_ASSETS_DATASET:-${BQ_DATASET}}"
VIOLATIONS_TABLE="${BQ_VIOLATIONS_TABLE:-violations}"
ASSETS_TABLE="${BQ_ASSETS_TABLE:-assets}"

echo "Ensuring high-severity Pub/Sub topic exists..."
gcloud pubsub topics describe "${TOPIC}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud pubsub topics create "${TOPIC}" --project "${PROJECT}"

echo "Ensuring evidence bucket exists..."
gcloud storage buckets describe "gs://${EVIDENCE_BUCKET}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${EVIDENCE_BUCKET}" --project "${PROJECT}" --location "${REGION}" --uniform-bucket-level-access

echo "Deploying Cloud Function alerting-pipeline..."
gcloud functions deploy alerting-pipeline \
  --gen2 \
  --runtime python311 \
  --region "${REGION}" \
  --project "${PROJECT}" \
  --source "services/alerting" \
  --entry-point handle_high_severity_violation \
  --trigger-topic "${TOPIC}" \
  --service-account "${SERVICE_ACCOUNT}" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT},BQ_ASSETS_DATASET=${DATASET},BQ_ASSETS_TABLE=${ASSETS_TABLE},BQ_VIOLATIONS_TABLE=${VIOLATIONS_TABLE},GCS_EVIDENCE_BUCKET=${EVIDENCE_BUCKET},GCS_RAW_BUCKET=${GCS_RAW_BUCKET},ALERT_WEBHOOK_URL=${ALERT_WEBHOOK_URL:-}"

echo "Alerting function deploy complete."
