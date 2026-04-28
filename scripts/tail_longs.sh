#!/usr/bin/env bash
set -euo pipefail

# Tail logs for DigitalAssetProtection services/functions.
#
# Usage:
#   ./scripts/tail_longs.sh <target>
#
# Targets:
#   ingest-service
#   fingerprint-service
#   fingerprint-worker-service
#   matching-service
#   scanner-service
#   violations-service
#   violations-subscriber-service
#   anomaly-service
#   alerting-pipeline
#   all
#
# Examples:
#   ./scripts/tail_longs.sh ingest-service
#   ./scripts/tail_longs.sh alerting-pipeline
#   ./scripts/tail_longs.sh all

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
TARGET="${1:-all}"

run_filter() {
  case "$1" in
    ingest-service|fingerprint-service|fingerprint-worker-service|matching-service|scanner-service|violations-service|violations-subscriber-service|anomaly-service)
      echo "resource.type=cloud_run_revision AND resource.labels.service_name=\"$1\""
      ;;
    alerting-pipeline)
      # Gen2 function logs usually appear under Cloud Run revision resource.
      echo "(resource.type=cloud_run_revision AND resource.labels.service_name=\"alerting-pipeline\") OR (resource.type=cloud_function AND resource.labels.function_name=\"alerting-pipeline\")"
      ;;
    all)
      echo "(resource.type=cloud_run_revision AND resource.labels.service_name=~\"(ingest-service|fingerprint-service|fingerprint-worker-service|matching-service|scanner-service|violations-service|violations-subscriber-service|anomaly-service|alerting-pipeline)\") OR (resource.type=cloud_function AND resource.labels.function_name=\"alerting-pipeline\")"
      ;;
    *)
      echo ""
      ;;
  esac
}

FILTER="$(run_filter "${TARGET}")"
if [[ -z "${FILTER}" ]]; then
  echo "Invalid target: ${TARGET}"
  echo "Run './scripts/tail_longs.sh all' or pass a valid service/function target."
  exit 1
fi

echo "Project: ${PROJECT}"
echo "Target: ${TARGET}"
echo "Filter: ${FILTER}"
echo

# Prefer true streaming when beta tail exists.
if gcloud beta logging tail --help >/dev/null 2>&1; then
  echo "Using gcloud beta logging tail (live stream). Press Ctrl+C to stop."
  gcloud beta logging tail "${FILTER}" --project "${PROJECT}" --format="value(timestamp,resource.labels.service_name,resource.labels.function_name,severity,textPayload,jsonPayload.message)"
  exit 0
fi

echo "gcloud beta logging tail not available. Falling back to polling every 10s."
echo "Press Ctrl+C to stop."

while true; do
  gcloud logging read "${FILTER}" \
    --project "${PROJECT}" \
    --limit=50 \
    --freshness=30s \
    --order=desc \
    --format="value(timestamp,resource.labels.service_name,resource.labels.function_name,severity,textPayload,jsonPayload.message)"
  sleep 10
done
