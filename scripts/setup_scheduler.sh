#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/setup_scheduler.sh <anomaly-service-url> [oidc-service-account-email]

SERVICE_URL="${1:-}"
OIDC_SA="${2:-}"
if [[ -z "${SERVICE_URL}" ]]; then
  echo "Usage: ./scripts/setup_scheduler.sh <anomaly-service-url> [oidc-service-account-email]"
  exit 1
fi

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
JOB_NAME="anomaly-runner-15m"
TARGET="${SERVICE_URL%/}/anomaly/run"

if gcloud scheduler jobs describe "${JOB_NAME}" --project "${PROJECT}" --location "${REGION}" >/dev/null 2>&1; then
  gcloud scheduler jobs delete "${JOB_NAME}" --quiet --project "${PROJECT}" --location "${REGION}"
fi

if [[ -n "${OIDC_SA}" ]]; then
  gcloud scheduler jobs create http "${JOB_NAME}" \
    --project "${PROJECT}" \
    --location "${REGION}" \
    --schedule "*/15 * * * *" \
    --http-method POST \
    --uri "${TARGET}" \
    --oidc-service-account-email "${OIDC_SA}" \
    --headers "Content-Type=application/json" \
    --message-body "{}"
else
  gcloud scheduler jobs create http "${JOB_NAME}" \
    --project "${PROJECT}" \
    --location "${REGION}" \
    --schedule "*/15 * * * *" \
    --http-method POST \
    --uri "${TARGET}" \
    --headers "Content-Type=application/json" \
    --message-body "{}"
fi

echo "Scheduler created: ${JOB_NAME} -> POST ${TARGET} every 15 minutes."
