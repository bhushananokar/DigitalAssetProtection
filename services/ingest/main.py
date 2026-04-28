from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile

from services.ingest.bigquery import IngestBigQuery
from services.ingest.gcs import GcsHelper
from services.ingest.pubsub import PubSubHelper
from services.ingest.video import VideoKeyframeExtractor

AssetType = Literal["image", "video"]

ALLOWED_EXTENSIONS = {"mp4", "mov", "jpg", "jpeg", "png", "svg"}
VIDEO_EXTENSIONS = {"mp4", "mov"}

app = FastAPI(title="Ingest Service", version="1.0.0")


def _getenv(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _helpers() -> tuple[GcsHelper, IngestBigQuery, PubSubHelper, VideoKeyframeExtractor]:
    project_id = _require("GCP_PROJECT_ID")
    dataset = _getenv("BQ_ASSETS_DATASET", _getenv("BQ_DATASET", "digital_asset_protection"))
    assets_table = _getenv("BQ_ASSETS_TABLE", "assets")
    violations_table = _getenv("BQ_VIOLATIONS_TABLE", "violations")
    return (
        GcsHelper(project_id=project_id),
        IngestBigQuery(
            project_id=project_id,
            dataset=dataset,
            assets_table=assets_table,
            violations_table=violations_table,
        ),
        PubSubHelper(project_id=project_id),
        VideoKeyframeExtractor(project_id=project_id),
    )


def _normalize_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower().replace(".", "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )
    return ext


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/assets/upload")
async def upload_asset(
    file: UploadFile = File(...),
    org_id: str = Form(...),
    asset_type: AssetType = Form(...),
    event_name: str = Form(...),
) -> dict:
    raw_bucket = _require("GCS_RAW_BUCKET")
    keyframes_bucket = _getenv("GCS_KEYFRAMES_BUCKET", raw_bucket)
    topic = _getenv("PUBSUB_ASSET_TOPIC", "asset-uploaded")

    extension = _normalize_extension(file.filename or "")
    if asset_type == "video" and extension not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="asset_type=video requires mp4/mov file.")
    if asset_type == "image" and extension in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="asset_type=image requires image file.")

    asset_id = str(uuid4())
    blob_name = f"assets/{asset_id}/original.{extension}"
    gcs, bq, pubsub, video = _helpers()

    payload = await file.read()
    storage_uri = gcs.upload_bytes(
        bucket=raw_bucket,
        blob_name=blob_name,
        payload=payload,
        content_type=file.content_type,
    )

    keyframe_uris: list[str] = []
    if asset_type == "video":
        frames = video.extract_keyframes_to_jpegs(payload, max_frames=12)
        for idx, frame_bytes in enumerate(frames, start=1):
            frame_blob = f"assets/{asset_id}/keyframes/frame_{idx}.jpg"
            keyframe_uri = gcs.upload_bytes(
                bucket=keyframes_bucket,
                blob_name=frame_blob,
                payload=frame_bytes,
                content_type="image/jpeg",
            )
            keyframe_uris.append(keyframe_uri)

    now = _now_iso()
    bq.insert_asset(
        {
            "asset_id": asset_id,
            "org_id": org_id,
            "asset_type": asset_type,
            "event_name": event_name,
            "storage_uri": storage_uri,
            "keyframe_uris": keyframe_uris,
            "fingerprint_status": "pending",
            "deleted": False,
            "created_at": now,
            "updated_at": now,
        }
    )

    pubsub.publish_json(
        topic,
        {
            "asset_id": asset_id,
            "storage_uri": storage_uri,
            "asset_type": asset_type,
            "keyframe_uris": keyframe_uris,
        },
    )
    return {"asset_id": asset_id, "status": "processing"}


@app.get("/assets")
def list_assets(
    org_id: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    asset_type: Optional[AssetType] = Query(default=None),
) -> dict:
    _, bq, _, _ = _helpers()
    return bq.list_assets(org_id=org_id, page=page, limit=limit, asset_type=asset_type)


@app.get("/assets/{asset_id}")
def get_asset(asset_id: str) -> dict:
    _, bq, _, _ = _helpers()
    row = bq.get_asset(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return row


@app.delete("/assets/{asset_id}")
def delete_asset(asset_id: str, hard_delete: bool = Query(default=False)) -> dict:
    raw_bucket = _require("GCS_RAW_BUCKET")
    keyframes_bucket = _getenv("GCS_KEYFRAMES_BUCKET", raw_bucket)
    gcs, bq, _, _ = _helpers()

    row = bq.get_asset(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Asset not found.")

    bq.mark_deleted(asset_id, hard_delete=hard_delete)
    deleted_objects = 0
    if hard_delete:
        deleted_objects += gcs.delete_prefix(bucket=raw_bucket, prefix=f"assets/{asset_id}/")
        if keyframes_bucket != raw_bucket:
            deleted_objects += gcs.delete_prefix(bucket=keyframes_bucket, prefix=f"assets/{asset_id}/")

    return {
        "asset_id": asset_id,
        "deleted": True,
        "hard_delete": hard_delete,
        "gcs_objects_deleted": deleted_objects,
    }
