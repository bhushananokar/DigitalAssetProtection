# Digital Asset Protection

Monorepo for ingesting official media, generating robust fingerprints, detecting unauthorized reuse, scoring violations, alerting rights holders, and surfacing results in a dashboard.

## Repo Components

- `services/ingest` - upload API, GCS storage, BigQuery asset records, keyframe extraction, `asset-uploaded` publish
- `services/fingerprint` - embedding generation + indexing pipeline (ML-owned)
- `services/matching` - similarity lookup + manual match API (ML-owned)
- `services/violations` - `match-found` consumer, severity scoring, violations APIs
- `services/alerting` - Pub/Sub-triggered Cloud Function for evidence bundle + webhook/log alerts
- `services/anomaly` - scheduled anomaly detection engine and run endpoint
- `services/scanner` - YouTube/web scan service (full stack-owned)
- `dashboard` - Next.js UI

## Prerequisites

- Python 3.11+
- Node.js 20+
- Google Cloud SDK (`gcloud`)
- BigQuery, Pub/Sub, Cloud Storage access in your target GCP project

## Local Setup

### 1) Python dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Node dependencies

```powershell
cd dashboard
npm install
cd ..\services\scanner
npm install
cd ..\..
```

### 3) Environment configuration

- Copy/maintain values in `setup.env` from `setup.env.example`.
- `setup.env` is the shared source for Python services and deploy scripts.
- Dashboard uses `dashboard/.env.local`.
- Scanner also reads from shared `setup.env` (no per-service `.env`).

### 4) Google credentials (local cloud-backed testing)

Use one of:

```powershell
gcloud auth application-default login
```

or set:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\service-account.json"
```

## Recommended Local Ports

- dashboard: `3000`
- scanner: `3003`
- matching: `3004`
- fingerprint: `3005`
- ingest: `8080`
- violations: `8090`
- anomaly: `8081`

## Run Services Locally (example)

```powershell
# matching
.\.venv\Scripts\python -m uvicorn services.matching.main:app --host 127.0.0.1 --port 3004

# fingerprint
.\.venv\Scripts\python -m uvicorn services.fingerprint.main:app --host 127.0.0.1 --port 3005

# ingest
.\.venv\Scripts\python -m uvicorn services.ingest.main:app --host 127.0.0.1 --port 8080

# violations
.\.venv\Scripts\python -m uvicorn services.violations.main:app --host 127.0.0.1 --port 8090

# anomaly
.\.venv\Scripts\python -m uvicorn services.anomaly.main:app --host 127.0.0.1 --port 8081
```

## Deployment Scripts

- `scripts/deploy.sh` - fingerprint + matching (+ worker)
- `scripts/deploy_ingest.sh` - ingest service + infra bootstrap for ingest-side resources
- `scripts/deploy_violations.sh` - violations API + worker
- `scripts/deploy_alerting.sh` - alerting Cloud Function (Gen2)
- `scripts/deploy_anomaly.sh` - anomaly Cloud Run service
- `scripts/deploy_dashboard.sh` - Next.js dashboard on Cloud Run with backend URL wiring
- `scripts/setup_scheduler.sh` - 15-minute scheduler for anomaly run endpoint
- `scripts/deploy_all.sh` - full-stack orchestration in integration order
- `scripts/verify_wiring.sh` - read-only checks for Pub/Sub, Cloud Run, service account wiring

## Production Deployment (GCP)

### 1) One-time project bootstrap

```powershell
gcloud config set project <YOUR_PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com `
  pubsub.googleapis.com bigquery.googleapis.com cloudfunctions.googleapis.com cloudscheduler.googleapis.com `
  eventarc.googleapis.com storage.googleapis.com
```

### 2) Configure `setup.env`

Set at least:

- `GCP_PROJECT_ID`, `GCP_REGION`
- `GCS_RAW_BUCKET`, `GCS_KEYFRAMES_BUCKET`, `GCS_EVIDENCE_BUCKET`
- `BQ_DATASET` (and optional table overrides)
- `PUBSUB_*` topic/sub names
- `YOUTUBE_API_KEY`, `CUSTOM_SEARCH_API_KEY`, `CUSTOM_SEARCH_CX`
- `DASHBOARD_SERVICE_NAME` (optional override, default `dashboard-service`)

### 3) Create service account + IAM

```powershell
gcloud iam service-accounts create dap-backend --display-name "DAP backend runtime"
```

Grant minimum required roles (adjust to your org policy):

```powershell
gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> --member serviceAccount:dap-backend@<YOUR_PROJECT_ID>.iam.gserviceaccount.com --role roles/run.invoker
gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> --member serviceAccount:dap-backend@<YOUR_PROJECT_ID>.iam.gserviceaccount.com --role roles/pubsub.publisher
gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> --member serviceAccount:dap-backend@<YOUR_PROJECT_ID>.iam.gserviceaccount.com --role roles/pubsub.subscriber
gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> --member serviceAccount:dap-backend@<YOUR_PROJECT_ID>.iam.gserviceaccount.com --role roles/bigquery.dataEditor
gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> --member serviceAccount:dap-backend@<YOUR_PROJECT_ID>.iam.gserviceaccount.com --role roles/bigquery.jobUser
gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> --member serviceAccount:dap-backend@<YOUR_PROJECT_ID>.iam.gserviceaccount.com --role roles/storage.objectAdmin
gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> --member serviceAccount:dap-backend@<YOUR_PROJECT_ID>.iam.gserviceaccount.com --role roles/cloudscheduler.admin
gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> --member serviceAccount:dap-backend@<YOUR_PROJECT_ID>.iam.gserviceaccount.com --role roles/eventarc.eventReceiver
```

### 4) Deploy everything

```powershell
bash ./scripts/deploy_all.sh dap-backend
```

This deploys:

- Cloud Run: `fingerprint-service`, `fingerprint-worker-service`, `ingest-service`, `matching-service`, `scanner-service`, `violations-service`, `violations-subscriber-service`, `anomaly-service`, dashboard service
- Cloud Function Gen2: `alerting-pipeline`
- Cloud Scheduler job for anomaly runs

### 5) Verify wiring

```powershell
bash ./scripts/verify_wiring.sh dap-backend
```

## Frontend on Cloudflare Zero Trust Subdomain

1. Deploy dashboard to Cloud Run (`deploy_all.sh` already does this, or run `bash ./scripts/deploy_dashboard.sh dap-backend`).
2. Get dashboard URL:

```powershell
gcloud run services describe dashboard-service --region <REGION> --format "value(status.url)"
```

3. In Cloudflare DNS, create `CNAME` for your subdomain (for example `dap.example.com`) to the Cloud Run host (the `https://` URL host only, no scheme/path).
4. Keep Cloudflare proxy enabled (orange cloud) so Zero Trust policies apply.
5. In Cloudflare Zero Trust -> Access -> Applications, add a **Self-hosted** app:
   - Domain: your subdomain
   - Session policy: your allowed emails/groups
   - Identity providers: as required
6. Validate end-to-end:
   - Access login page appears on subdomain
   - Dashboard loads
   - `/api/assets`, `/api/violations`, `/api/scanner` calls succeed through server-side proxying.

### Optional: Cloud Run custom domain mapping

If you prefer native Cloud Run domain mapping first, create mapping and then point DNS as instructed by Google:

```powershell
gcloud beta run domain-mappings create --service dashboard-service --domain <subdomain.yourdomain.com> --region <REGION>
```

## Tests

### Service-level integration tests

```powershell
.\.venv\Scripts\python -m services.ingest.test_upload
.\.venv\Scripts\python -m services.violations.test_mock_violation
.\.venv\Scripts\python -m services.alerting.test_alert
.\.venv\Scripts\python -m services.anomaly.test_anomaly
```

### End-to-end integration test

```powershell
.\.venv\Scripts\python scripts/e2e_test.py
```

The E2E flow verifies:

1. ingest upload
2. matching submission on modified media
3. violation in BigQuery
4. violation visible via violations API
5. alert topic event for high/critical severity

## Known Behavior / Notes

- BigQuery may reject immediate `UPDATE` on rows still in streaming buffer; alerting handles this gracefully and still sends notifications.
- `scripts/e2e_test.py` includes a local fallback path for violation processing when a background violations subscriber is not running.
- For scanner-to-matching calls in Cloud Run, use internal URL via `MATCHING_SERVICE_URL_INTERNAL` when available; otherwise public URL is used.

## Troubleshooting

- `DefaultCredentialsError` -> configure ADC (`gcloud auth application-default login`) or `GOOGLE_APPLICATION_CREDENTIALS`
- Port already in use -> stop old process (`Get-NetTCPConnection -LocalPort <port>`)
- Ingest upload `500` -> check `setup.env` values and GCP IAM on bucket/topic/table
- Violations API empty after publish -> ensure `PUBSUB_MATCH_SUB` consumer is running (`violations-subscriber-service`)
