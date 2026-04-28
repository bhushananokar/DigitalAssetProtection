# Digital Asset Protection

Monorepo for a media fingerprinting and unauthorized content detection platform.

## Services and ports (local)

- `dashboard` -> `http://localhost:3000`
- `ingest` -> `http://localhost:3001`
- `violations` -> `http://localhost:3002`
- `scanner` -> `http://localhost:3003`
- `matching` -> `http://localhost:3004`
- `fingerprint` -> `http://localhost:3005`

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm
- Google Cloud SDK (`gcloud`)

## 1) Clone and install

From repo root:

```powershell
cd "C:\Users\Ameya\Documents\GitHub\DigitalAssetProtection"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pip install -r services/ingest/requirements.txt -r services/violations/requirements.txt
```

Install dashboard and scanner deps:

```powershell
cd dashboard
npm install
cd ..\services\scanner
npm install
cd ..\..
```

## 2) Environment setup

Use `setup.env` as the central env file. It already includes:

- shared GCP vars
- scanner vars
- dashboard URL vars

Dashboard also needs `dashboard/.env.local`:

```env
NEXT_PUBLIC_INGEST_URL=http://localhost:3001
NEXT_PUBLIC_VIOLATIONS_URL=http://localhost:3002
NEXT_PUBLIC_SCANNER_URL=http://localhost:3003
FINGERPRINT_URL=http://localhost:3004
```

Scanner also needs `services/scanner/.env`:

```env
PORT=3003
YOUTUBE_API_KEY=
CUSTOM_SEARCH_API_KEY=
CUSTOM_SEARCH_CX=
MATCHING_SERVICE_URL=http://localhost:3004
BIGQUERY_PROJECT_ID=
BIGQUERY_DATASET=
```

> For local scanner testing without ADC, keep scanner `BIGQUERY_*` empty to use in-memory fallback.

## 3) Google auth (required for ingest/violations and cloud-backed flows)

```powershell
gcloud auth application-default login
gcloud config set project gen-lang-client-0647383072
```

## 4) Load `setup.env` into each Python service terminal

Run this once per terminal before starting `uvicorn`:

```powershell
Get-Content .\setup.env | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
  $name, $value = $_ -split '=', 2
  [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
}
```

## 5) Start all services (separate terminals)

### Terminal A - matching

```powershell
cd "C:\Users\Ameya\Documents\GitHub\DigitalAssetProtection"
.\.venv\Scripts\activate
uvicorn services.matching.main:app --host 0.0.0.0 --port 3004
```

### Terminal B - fingerprint

```powershell
cd "C:\Users\Ameya\Documents\GitHub\DigitalAssetProtection"
.\.venv\Scripts\activate
uvicorn services.fingerprint.main:app --host 0.0.0.0 --port 3005
```

### Terminal C - ingest

```powershell
cd "C:\Users\Ameya\Documents\GitHub\DigitalAssetProtection"
.\.venv\Scripts\activate
# load setup.env using snippet above
uvicorn services.ingest.main:app --host 0.0.0.0 --port 3001
```

### Terminal D - violations

```powershell
cd "C:\Users\Ameya\Documents\GitHub\DigitalAssetProtection"
.\.venv\Scripts\activate
# load setup.env using snippet above
uvicorn services.violations.main:app --host 0.0.0.0 --port 3002
```

### Terminal E - scanner

```powershell
cd "C:\Users\Ameya\Documents\GitHub\DigitalAssetProtection\services\scanner"
npm run dev
```

### Terminal F - dashboard

```powershell
cd "C:\Users\Ameya\Documents\GitHub\DigitalAssetProtection\dashboard"
npm run dev -- -p 3000
```

## 6) Health checks

```powershell
curl http://localhost:3001/healthz
curl http://localhost:3002/healthz
curl http://localhost:3003/healthz
curl http://localhost:3004/healthz
curl http://localhost:3005/healthz
```

Open dashboard:

- [http://localhost:3000](http://localhost:3000)

## 7) Dry-run checklist

1. Open `/assets` and upload an official image/video.
2. Open `/check` and run "Upload File" with same file (expect `matched: true` when indexing is ready).
3. Open `/scanner`, add keyword(s), run scan, verify jobs table updates.
4. Open `/violations` and `/` (overview) to confirm violations service responses.

## Troubleshooting

- `Errno 10048` -> port already in use. Stop old process or run on another port.
- `DefaultCredentialsError` -> run `gcloud auth application-default login`.
- `POST /api/assets/upload 500` -> ingest not running or ingest env missing.
- `/api/violations/* 500` -> violations not running or BigQuery auth/env issue.
- Scanner all `matched: false` -> scanner working, but no vector match above threshold for discovered sources.
