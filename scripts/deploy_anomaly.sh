#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/deploy_anomaly.sh <service-account-email>

SERVICE_ACCOUNT="${1:-}"
if [[ -z "${SERVICE_ACCOUNT}" ]]; then
  echo "Usage: ./scripts/deploy_anomaly.sh <service-account-email>"
  exit 1
fi

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
DATASET="${BQ_ASSETS_DATASET:-${BQ_DATASET}}"
VIOLATIONS_TABLE="${BQ_VIOLATIONS_TABLE:-violations}"
HIGH_TOPIC="${PUBSUB_HIGH_SEVERITY_TOPIC:-high-severity-violation}"

echo "Ensuring high-severity topic exists..."
gcloud pubsub topics describe "${HIGH_TOPIC}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud pubsub topics create "${HIGH_TOPIC}" --project "${PROJECT}"

echo "Building anomaly image..."
gcloud builds submit --project "${PROJECT}" --tag "gcr.io/${PROJECT}/anomaly-service:latest" -f services/anomaly/Dockerfile .

echo "Deploying anomaly service..."
gcloud run deploy anomaly-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/anomaly-service:latest" \
  --set-env-vars "BQ_ASSETS_DATASET=${DATASET},BQ_VIOLATIONS_TABLE=${VIOLATIONS_TABLE},PUBSUB_HIGH_SEVERITY_TOPIC=${HIGH_TOPIC}" \
  --set-env-vars-file setup.env

echo "Anomaly deploy complete."
