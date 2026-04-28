from __future__ import annotations

from fastapi import FastAPI

from services.anomaly.detector import create_default_detector

app = FastAPI(title="Anomaly Engine", version="1.0.0")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/anomaly/run")
def run_anomaly() -> dict:
    detector = create_default_detector()
    result = detector.run()
    return {
        "run_id": result["run_id"],
        "started_at": result["started_at"],
        "violations_flagged": result["violations_flagged"],
        "breakdown": result.get("breakdown", {}),
    }
