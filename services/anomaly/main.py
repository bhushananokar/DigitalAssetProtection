from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi import Request

from services.anomaly.detector import create_default_detector

app = FastAPI(title="Anomaly Engine", version="1.0.0")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("dap.anomaly")


def _load_setup_env_if_present() -> None:
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent
    env_path = repo_root / "setup.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_setup_env_if_present()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.exception("request_failed method=%s path=%s duration_ms=%d", request.method, request.url.path, elapsed_ms)
        raise
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "request_completed method=%s path=%s status=%d duration_ms=%d",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.post("/anomaly/run")
def run_anomaly() -> dict:
    logger.info("anomaly_run_requested")
    detector = create_default_detector()
    result = detector.run()
    response = {
        "run_id": result["run_id"],
        "started_at": result["started_at"],
        "violations_flagged": result["violations_flagged"],
        "breakdown": result.get("breakdown", {}),
    }
    logger.info(
        "anomaly_run_completed run_id=%s violations_flagged=%s breakdown=%s",
        response["run_id"],
        response["violations_flagged"],
        response["breakdown"],
    )
    return response
