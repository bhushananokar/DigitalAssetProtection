#!/usr/bin/env bash
set -euo pipefail

# Deploy Next.js dashboard to Cloud Run with backend URLs wired from deployed services.
#
# Usage:
#   ./scripts/deploy_dashboard.sh <service-account-email-or-name>
#
# Examples:
#   ./scripts/deploy_dashboard.sh dap-backend
#   ./scripts/deploy_dashboard.sh dap-backend@my-project.iam.gserviceaccount.com

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
DASHBOARD_SERVICE="${DASHBOARD_SERVICE_NAME:-dashboard-service}"

SA_INPUT="${1:-dap-backend}"
if [[ "${SA_INPUT}" == *"@"* ]]; then
  SERVICE_ACCOUNT="${SA_INPUT}"
else
  SERVICE_ACCOUNT="${SA_INPUT}@${PROJECT}.iam.gserviceaccount.com"
fi

echo "Resolving backend service URLs..."
INGEST_URL="$(gcloud run services describe ingest-service --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"
VIOLATIONS_URL="$(gcloud run services describe violations-service --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"
SCANNER_URL="$(gcloud run services describe scanner-service --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"
MATCHING_URL="$(gcloud run services describe matching-service --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')"

if [[ -z "${INGEST_URL}" || -z "${VIOLATIONS_URL}" || -z "${SCANNER_URL}" || -z "${MATCHING_URL}" ]]; then
  echo "Missing one or more backend service URLs. Deploy backend services first."
  exit 1
fi

echo "Building dashboard image..."
gcloud builds submit dashboard --project "${PROJECT}" --tag "gcr.io/${PROJECT}/dashboard-service:latest"

echo "Deploying dashboard service: ${DASHBOARD_SERVICE}"
gcloud run deploy "${DASHBOARD_SERVICE}" \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --service-account "${SERVICE_ACCOUNT}" \
  --image "gcr.io/${PROJECT}/dashboard-service:latest" \
  --port 3000 \
  --set-env-vars "NODE_ENV=production,NEXT_PUBLIC_INGEST_URL=${INGEST_URL},NEXT_PUBLIC_VIOLATIONS_URL=${VIOLATIONS_URL},NEXT_PUBLIC_SCANNER_URL=${SCANNER_URL},FINGERPRINT_URL=${MATCHING_URL}"

echo "Dashboard deploy complete."
echo "Dashboard URL:"
gcloud run services describe "${DASHBOARD_SERVICE}" --project "${PROJECT}" --region "${REGION}" --format='value(status.url)'
