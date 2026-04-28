#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./deploy.sh <service-account-email>
# Example:
#   ./deploy.sh fingerprint-runner@my-project.iam.gserviceaccount.com

SERVICE_ACCOUNT="${1:-}"
if [[ -z "${SERVICE_ACCOUNT}" ]]; then
  echo "Usage: ./deploy.sh <service-account-email>"
  exit 1
fi

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"

gcloud run deploy fingerprint-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/fingerprint-service:latest" \
  --set-env-vars-file setup.env

gcloud run deploy matching-service \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/matching-service:latest" \
  --set-env-vars-file setup.env

# Optional third service for Pub/Sub push processing.
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

# Build images (run before deploy commands if tags don't exist yet):
# gcloud builds submit --project "${PROJECT}" --tag "gcr.io/${PROJECT}/fingerprint-service:latest" -f services/fingerprint/Dockerfile .
# gcloud builds submit --project "${PROJECT}" --tag "gcr.io/${PROJECT}/matching-service:latest" -f services/matching/Dockerfile .
