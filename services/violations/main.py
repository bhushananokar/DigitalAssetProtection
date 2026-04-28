from __future__ import annotations

import json
import os
import threading
import time
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from services.shared.gcs_client import GcsClient
from services.violations.bigquery import ViolationsBigQuery
from services.violations.subscriber import create_default_subscriber

app = FastAPI(title="Violations Service", version="1.0.0")

_stats_cache: dict = {"ts": 0.0, "data": None}
_stats_lock = threading.Lock()
_subscriber_thread: Optional[threading.Thread] = None
_subscriber_stop = threading.Event()


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
    if not enable_subscriber:
        return

    subscriber = create_default_subscriber()

    def _runner() -> None:
        subscriber.run_forever(stop_event=_subscriber_stop)

    _subscriber_thread = threading.Thread(target=_runner, daemon=True, name="violations-subscriber")
    _subscriber_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    _subscriber_stop.set()
    if _subscriber_thread and _subscriber_thread.is_alive():
        _subscriber_thread.join(timeout=3)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


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
            return _stats_cache["data"]

    fresh = _bq().compute_stats()
    with _stats_lock:
        _stats_cache["data"] = fresh
        _stats_cache["ts"] = now
    return fresh


@app.get("/violations/{violation_id}")
def get_violation(violation_id: str) -> dict:
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
    updated = _bq().update_violation_status(
        violation_id=violation_id,
        status=body.status,
        note=body.note,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Violation not found.")
    return updated
