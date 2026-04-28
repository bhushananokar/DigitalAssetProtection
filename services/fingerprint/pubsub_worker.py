from __future__ import annotations

import base64
import json

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from services.fingerprint.processor import generate_fingerprint
from services.shared.schemas import FingerprintGenerateRequest, PubSubPushEnvelope

app = FastAPI(title="Fingerprint PubSub Worker", version="1.0.0")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/pubsub/asset-uploaded")
def handle_asset_uploaded(envelope: PubSubPushEnvelope):
    try:
        raw = base64.b64decode(envelope.data_b64).decode("utf-8")
        payload = json.loads(raw)
        req = FingerprintGenerateRequest(
            asset_id=payload["asset_id"],
            storage_uri=payload["storage_uri"],
            asset_type=payload["asset_type"],
            org_id=payload.get("org_id"),
        )
        _ = generate_fingerprint(req)
        # For push subscriptions: 2xx means ack.
        return {"ok": True}
    except Exception as e:
        # Non-2xx means retry/backoff from Pub/Sub push delivery.
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

