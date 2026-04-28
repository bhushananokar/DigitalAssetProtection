# Fingerprint + Matching Service Contract

## Pipeline

The fingerprint pipeline downloads an uploaded asset from GCS, generates multimodal embeddings (`multimodalembedding@001`) using Vertex AI, stores embedding rows in BigQuery, and upserts vectors into Matching Engine. Images generate one embedding. Videos generate up to 10 uniformly sampled keyframe embeddings plus one mean-pooled embedding for whole-video matching.

## Index Configuration

- Embedding dimension: `1408`
- Distance metric: `cosine` (similarity computed as `1 - distance`)

## Endpoints

### Fingerprint Service

#### `POST /fingerprint/generate`

Request:

```json
{
  "asset_id": "asset-123",
  "storage_uri": "gs://bucket/path/file.mp4",
  "asset_type": "video"
}
```

Success response:

```json
{
  "fingerprint_id": "uuid",
  "asset_id": "asset-123",
  "model_version": "multimodalembedding@001",
  "generated_at": "2026-04-28T12:34:56.000000+00:00",
  "status": "ready"
}
```

Error envelope:

```json
{
  "error": true,
  "code": "FINGERPRINT_FAILED",
  "message": "error details",
  "status": 500
}
```

#### `POST /pubsub/asset-uploaded` (worker service)

Pub/Sub push payload envelope with base64-encoded message data containing:

```json
{
  "asset_id": "asset-123",
  "storage_uri": "gs://bucket/path/file.mp4",
  "asset_type": "video",
  "org_id": "org-1"
}
```

### Matching Service

#### `POST /matching/query`

Request:

```json
{
  "embedding": [0.01, 0.02],
  "top_k": 5,
  "threshold": 0.7
}
```

Response:

```json
{
  "matches": [
    {
      "asset_id": "asset-123",
      "fingerprint_id": "fp-abc",
      "similarity_score": 0.91,
      "asset_type": "video"
    }
  ]
}
```

#### `POST /matching/index/upsert`

Request:

```json
{
  "fingerprint_id": "fp-abc",
  "asset_id": "asset-123",
  "embedding": [0.01, 0.02]
}
```

Response:

```json
{
  "success": true
}
```

#### `POST /fingerprint/match`

Multipart request accepts either `source_url` or `file`:

Response:

```json
{
  "matched": true,
  "matches": [
    {
      "asset_id": "asset-123",
      "asset_name": "asset-123",
      "fingerprint_id": "fp-abc",
      "similarity_score": 0.88,
      "confidence": "medium"
    }
  ]
}
```

Confidence mapping:
- `>=0.90`: `high`
- `0.80-0.89`: `medium`
- `0.70-0.79`: `low`

## Curl Examples

Generate fingerprint:

```bash
curl -X POST http://localhost:8080/fingerprint/generate \
  -H "Content-Type: application/json" \
  -d '{"asset_id":"asset-1","storage_uri":"gs://bucket/img.jpg","asset_type":"image"}'
```

Query matching:

```bash
curl -X POST http://localhost:8081/matching/query \
  -H "Content-Type: application/json" \
  -d '{"embedding":[0.1,0.2],"top_k":5,"threshold":0.7}'
```

Manual match by URL:

```bash
curl -X POST http://localhost:8081/fingerprint/match \
  -F "source_url=https://example.com/video.mp4"
```

Manual match by upload:

```bash
curl -X POST http://localhost:8081/fingerprint/match \
  -F "file=@tests/fixtures/sample_video.mp4"
```

Index upsert:

```bash
curl -X POST http://localhost:8081/matching/index/upsert \
  -H "Content-Type: application/json" \
  -d '{"fingerprint_id":"fp-1","asset_id":"asset-1","embedding":[0.1,0.2]}'
```

## Robustness Test

Run:

```bash
python tests/robustness_test.py
```

Requires:
- one image and one video in `tests/fixtures`
- valid Google ADC auth
- ffmpeg available on PATH (or set `FFMPEG_BIN`)

## Known Limitations

- Horizontal flip can be unstable depending on content and model behavior.
- Very short clips under ~2 seconds may not produce stable pooled video embeddings.
- Audio-only content is not supported by the current image/video embedding pipeline.
