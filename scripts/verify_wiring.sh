#!/usr/bin/env bash
set -euo pipefail

# Read-only integration wiring checks for Phase 5.
#
# Usage:
#   ./scripts/verify_wiring.sh [service-account-email-or-name]

source ./setup.env

PROJECT="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"
DATASET="${BQ_ASSETS_DATASET:-${BQ_DATASET}}"
VIOLATIONS_TABLE="${BQ_VIOLATIONS_TABLE:-violations}"
ASSET_SUB="${PUBSUB_ASSET_SUB:-fingerprint-asset-sub}"
MATCH_SUB="${PUBSUB_MATCH_SUB:-violations-match-sub}"
HIGH_TOPIC="${PUBSUB_HIGH_SEVERITY_TOPIC:-high-severity-violation}"

SA_INPUT="${1:-dap-backend}"
if [[ "${SA_INPUT}" == *"@"* ]]; then
  EXPECTED_SA="${SA_INPUT}"
else
  EXPECTED_SA="${SA_INPUT}@${PROJECT}.iam.gserviceaccount.com"
fi

echo "== Pub/Sub Wiring =="
for topic in asset-uploaded match-found "${HIGH_TOPIC}"; do
  if gcloud pubsub topics describe "${topic}" --project "${PROJECT}" >/dev/null 2>&1; then
    echo "OK topic exists: ${topic}"
  else
    echo "FAIL missing topic: ${topic}"
  fi
done

if gcloud pubsub subscriptions describe "${ASSET_SUB}" --project "${PROJECT}" >/dev/null 2>&1; then
  echo "OK asset-uploaded subscriber exists: ${ASSET_SUB}"
else
  echo "FAIL missing asset-uploaded subscriber: ${ASSET_SUB}"
fi

if gcloud pubsub subscriptions describe "${MATCH_SUB}" --project "${PROJECT}" >/dev/null 2>&1; then
  echo "OK match-found subscriber exists: ${MATCH_SUB}"
else
  echo "FAIL missing match-found subscriber: ${MATCH_SUB}"
fi

if gcloud functions describe alerting-pipeline --gen2 --region "${REGION}" --project "${PROJECT}" >/dev/null 2>&1; then
  echo "OK alerting function exists: alerting-pipeline"
else
  echo "FAIL missing alerting function: alerting-pipeline"
fi

echo
echo "== Cloud Run Wiring =="
for svc in fingerprint-service ingest-service matching-service scanner-service violations-service anomaly-service; do
  if ! gcloud run services describe "${svc}" --project "${PROJECT}" --region "${REGION}" >/dev/null 2>&1; then
    echo "FAIL missing service: ${svc}"
    continue
  fi
  sa="$(gcloud run services describe "${svc}" --project "${PROJECT}" --region "${REGION}" --format='value(spec.template.spec.serviceAccountName)')"
  if [[ "${sa}" == "${EXPECTED_SA}" ]]; then
    echo "OK ${svc} service account: ${sa}"
  else
    echo "WARN ${svc} service account mismatch: ${sa} (expected ${EXPECTED_SA})"
  fi
done

echo
echo "== Config + Internal URL Checks =="
scanner_matching="$(gcloud run services describe scanner-service --project "${PROJECT}" --region "${REGION}" --format='value(spec.template.spec.containers[0].env[?name=MATCHING_SERVICE_URL].value)' 2>/dev/null || true)"
if [[ -z "${scanner_matching}" ]]; then
  echo "WARN scanner MATCHING_SERVICE_URL not found"
else
  echo "scanner MATCHING_SERVICE_URL=${scanner_matching}"
  if [[ "${scanner_matching}" == *"localhost"* ]]; then
    echo "FAIL scanner uses localhost for matching URL"
  elif [[ "${scanner_matching}" == *".run.internal"* ]]; then
    echo "OK scanner uses Cloud Run internal URL"
  else
    echo "WARN scanner uses public URL (acceptable fallback): ${scanner_matching}"
  fi
fi

echo
echo "== Schema Check =="
bq --project_id="${PROJECT}" query --use_legacy_sql=false "
SELECT
  COUNT(1) AS violations_rows,
  COUNTIF(status='open') AS open_violations
FROM \`${PROJECT}.${DATASET}.${VIOLATIONS_TABLE}\`;"

echo
echo "Wiring check complete."
