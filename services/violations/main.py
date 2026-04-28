from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.shared.gcs_client import GcsClient
from services.violations.bigquery import ViolationsBigQuery
from services.violations.subscriber import create_default_subscriber

app = FastAPI(title="Violations Service", version="1.0.0")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("dap.violations")

_stats_cache: dict = {"ts": 0.0, "data": None}
_stats_lock = threading.Lock()
_subscriber_thread: Optional[threading.Thread] = None
_subscriber_stop = threading.Event()


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


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _getenv(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


_load_setup_env_if_present()


def _bq() -> ViolationsBigQuery:
    project_id = _require("GCP_PROJECT_ID")
    dataset = _getenv("BQ_ASSETS_DATASET", _getenv("BQ_DATASET", "digital_asset_protection"))
    return ViolationsBigQuery(
        project_id=project_id,
        dataset=dataset,
        violations_table=_getenv("BQ_VIOLATIONS_TABLE", "violations"),
        assets_table=_getenv("BQ_ASSETS_TABLE", "assets"),
    )


class StatusUpdateRequest(BaseModel):
    status: str = Field(..., min_length=1)
    note: Optional[str] = None


@app.on_event("startup")
def startup() -> None:
    global _subscriber_thread
    enable_subscriber = _getenv("VIOLATIONS_ENABLE_SUBSCRIBER", "false").lower() in ("1", "true", "yes")
    logger.info("service_startup enable_subscriber=%s", enable_subscriber)
    if not enable_subscriber:
        return

    subscriber = create_default_subscriber()

    def _runner() -> None:
        subscriber.run_forever(stop_event=_subscriber_stop)

    _subscriber_thread = threading.Thread(target=_runner, daemon=True, name="violations-subscriber")
    _subscriber_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    logger.info("service_shutdown requested")
    _subscriber_stop.set()
    if _subscriber_thread and _subscriber_thread.is_alive():
        _subscriber_thread.join(timeout=3)


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


@app.get("/violations")
def list_violations(
    org_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    platform: Optional[str] = Query(default=None),
    asset_id: Optional[str] = Query(default=None),
    from_date: Optional[date] = Query(default=None),
    to_date: Optional[date] = Query(default=None),
    anomaly_flagged: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
) -> dict:
    logger.info(
        "violations_list_query org_id=%s severity=%s status=%s platform=%s asset_id=%s page=%d limit=%d",
        org_id,
        severity,
        status,
        platform,
        asset_id,
        page,
        limit,
    )
    return _bq().list_violations(
        org_id=org_id,
        severity=severity,
        status=status,
        platform=platform,
        asset_id=asset_id,
        from_date=from_date,
        to_date=to_date,
        anomaly_flagged=anomaly_flagged,
        page=page,
        limit=limit,
    )


@app.get("/violations/stats")
def get_stats() -> dict:
    now = time.time()
    with _stats_lock:
        if _stats_cache["data"] and now - float(_stats_cache["ts"]) <= 300:
            logger.info("violations_stats_cache_hit")
            return _stats_cache["data"]

    fresh = _bq().compute_stats()
    with _stats_lock:
        _stats_cache["data"] = fresh
        _stats_cache["ts"] = now
    logger.info("violations_stats_cache_refresh")
    return fresh


@app.get("/violations/{violation_id}")
def get_violation(violation_id: str) -> dict:
    logger.info("violation_detail_query violation_id=%s", violation_id)
    row = _bq().get_violation(violation_id)
    if not row:
        raise HTTPException(status_code=404, detail="Violation not found.")

    evidence_uri = row.get("evidence_uri")
    evidence_bundle = None
    if evidence_uri:
        try:
            evidence_bytes = GcsClient.default().download_bytes(str(evidence_uri))
            evidence_bundle = json.loads(evidence_bytes.decode("utf-8"))
        except Exception:
            evidence_bundle = None
    row["evidence_bundle"] = evidence_bundle
    return row


@app.patch("/violations/{violation_id}/status")
def patch_status(violation_id: str, body: StatusUpdateRequest) -> dict:
    logger.info("violation_status_update violation_id=%s status=%s", violation_id, body.status)
    updated = _bq().update_violation_status(
        violation_id=violation_id,
        status=body.status,
        note=body.note,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Violation not found.")
    logger.info("violation_status_updated violation_id=%s", violation_id)
    return updated
