from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from services.fingerprint.processor import _set_asset_status, generate_fingerprint
from services.shared.schemas import ErrorEnvelope, FingerprintGenerateRequest

app = FastAPI(title="Fingerprint Service", version="1.0.0")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/fingerprint/generate")
def fingerprint_generate(req: FingerprintGenerateRequest):
    try:
        resp = generate_fingerprint(req)
        return resp.model_dump()
    except Exception as e:
        try:
            _set_asset_status(req.asset_id, "failed")
        except Exception:
            pass
        err = ErrorEnvelope(
            code="FINGERPRINT_FAILED",
            message=str(e),
            status=500,
        )
        return JSONResponse(status_code=500, content=err.model_dump())

