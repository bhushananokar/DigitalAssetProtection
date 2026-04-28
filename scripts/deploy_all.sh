#!/usr/bin/env bash
set -euo pipefail

# Deploy the full platform stack in integration order.
#
# Usage:
#   ./scripts/deploy_all.sh [service-account-email-or-name]
#
# Examples:
#   ./scripts/deploy_all.sh dap-backend
#   ./scripts/deploy_all.sh dap-backend@my-project.iam.gserviceaccount.com

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
RAW_BUCKET="${GCS_RAW_BUCKET}"
KEYFRAMES_BUCKET="${GCS_KEYFRAMES_BUCKET:-${GCS_RAW_BUCKET}}"
EVIDENCE_BUCKET="${GCS_EVIDENCE_BUCKET:-${GCS_RAW_BUCKET}}"
DATASET="${BQ_ASSETS_DATASET:-${BQ_DATASET}}"
VIOLATIONS_TABLE="${BQ_VIOLATIONS_TABLE:-violations}"

SA_INPUT="${1:-dap-backend}"
if [[ "${SA_INPUT}" == *"@"* ]]; then
  SERVICE_ACCOUNT="${SA_INPUT}"
else
  SERVICE_ACCOUNT="${SA_INPUT}@${PROJECT}.iam.gserviceaccount.com"
fi

echo "Using service account: ${SERVICE_ACCOUNT}"

echo "Ensuring core Pub/Sub topics exist..."
gcloud pubsub topics describe asset-uploaded --project "${PROJECT}" >/dev/null 2>&1 || gcloud pubsub topics create asset-uploaded --project "${PROJECT}"
gcloud pubsub topics describe match-found --project "${PROJECT}" >/dev/null 2>&1 || gcloud pubsub topics create match-found --project "${PROJECT}"
gcloud pubsub topics describe high-severity-violation --project "${PROJECT}" >/dev/null 2>&1 || gcloud pubsub topics create high-severity-violation --project "${PROJECT}"

echo "Ensuring required subscriptions exist..."
gcloud pubsub subscriptions describe "${PUBSUB_ASSET_SUB:-fingerprint-asset-sub}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud pubsub subscriptions create "${PUBSUB_ASSET_SUB:-fingerprint-asset-sub}" --topic=asset-uploaded --project "${PROJECT}"
gcloud pubsub subscriptions describe "${PUBSUB_MATCH_SUB:-violations-match-sub}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud pubsub subscriptions create "${PUBSUB_MATCH_SUB:-violations-match-sub}" --topic=match-found --project "${PROJECT}"

echo "Ensuring storage buckets exist..."
gcloud storage buckets describe "gs://${RAW_BUCKET}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${RAW_BUCKET}" --project "${PROJECT}" --location "${REGION}" --uniform-bucket-level-access
gcloud storage buckets describe "gs://${KEYFRAMES_BUCKET}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${KEYFRAMES_BUCKET}" --project "${PROJECT}" --location "${REGION}" --uniform-bucket-level-access
gcloud storage buckets describe "gs://${EVIDENCE_BUCKET}" --project "${PROJECT}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${EVIDENCE_BUCKET}" --project "${PROJECT}" --location "${REGION}" --uniform-bucket-level-access

echo "Ensuring BigQuery dataset exists..."
bq --project_id="${PROJECT}" mk --dataset --location="${REGION}" "${PROJECT}:${DATASET}" >/dev/null 2>&1 || true

# 1) Deploy fingerprint service (ML)
echo "Deploying fingerprint service..."
gcloud builds submit --project "${PROJECT}" --tag "gcr.io/${PROJECT}/fingerprint-service:latest" -f services/fingerprint/Dockerfile .
gcloud run deploy fingerprint-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/fingerprint-service:latest" \
  --set-env-vars-file setup.env
gcloud run deploy fingerprint-worker-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --no-allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/fingerprint-service:latest" \
  --set-env-vars-file setup.env \
  --command gunicorn \
  --args "-k","uvicorn.workers.UvicornWorker","-w","2","-b","0.0.0.0:8080","services.fingerprint.pubsub_worker:app"

# 2) Deploy ingest
./scripts/deploy_ingest.sh "${SERVICE_ACCOUNT}"

# 3) Deploy matching service (ML)
echo "Deploying matching service..."
gcloud builds submit --project "${PROJECT}" --tag "gcr.io/${PROJECT}/matching-service:latest" -f services/matching/Dockerfile .
gcloud run deploy matching-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/matching-service:latest" \
  --set-env-vars-file setup.env

# 4) Deploy scanner service (full stack)
echo "Deploying scanner service..."
gcloud builds submit services/scanner --project "${PROJECT}" --tag "gcr.io/${PROJECT}/scanner-service:latest"
MATCHING_PUBLIC_URL="$(gcloud run services describe matching-service --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"
SCANNER_MATCHING_URL="${MATCHING_SERVICE_URL_INTERNAL:-${MATCHING_PUBLIC_URL}}"
gcloud run deploy scanner-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/scanner-service:latest" \
  --set-env-vars "MATCHING_SERVICE_URL=${SCANNER_MATCHING_URL},BIGQUERY_PROJECT_ID=${PROJECT},BIGQUERY_DATASET=${DATASET},YOUTUBE_API_KEY=${YOUTUBE_API_KEY:-},CUSTOM_SEARCH_API_KEY=${CUSTOM_SEARCH_API_KEY:-},CUSTOM_SEARCH_CX=${CUSTOM_SEARCH_CX:-}"

# 5) Deploy violations
./scripts/deploy_violations.sh "${SERVICE_ACCOUNT}"

# 6) Deploy anomaly
./scripts/deploy_anomaly.sh "${SERVICE_ACCOUNT}"

# 7) Deploy alerting function
./scripts/deploy_alerting.sh "${SERVICE_ACCOUNT}"

# 8) Set up scheduler for anomaly run
ANOMALY_URL="$(gcloud run services describe anomaly-service --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"
./scripts/setup_scheduler.sh "${ANOMALY_URL}" "${SERVICE_ACCOUNT}"

echo "All services deployed and scheduler configured."
