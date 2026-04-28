from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
import requests
from google.api_core.exceptions import DeadlineExceeded
from google.cloud import bigquery, pubsub_v1, storage
from PIL import Image


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


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def _create_sample_image() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        path = Path(tmp.name)
    image = Image.new("RGB", (320, 180), color=(12, 34, 200))
    image.save(path, format="JPEG")
    payload = path.read_bytes()
    path.unlink(missing_ok=True)
    return payload


def _create_sample_video() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        path = Path(tmp.name)
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5.0,
        (320, 180),
    )
    for idx in range(12):
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[:, :, 2] = min(255, idx * 20)
        frame[:, :, 1] = 80
        writer.write(frame)
    writer.release()
    payload = path.read_bytes()
    path.unlink(missing_ok=True)
    return payload


def _upload_asset(
    *,
    base_url: str,
    filename: str,
    payload: bytes,
    asset_type: str,
    org_id: str,
    event_name: str,
) -> Dict[str, str]:
    response = requests.post(
        f"{base_url.rstrip('/')}/assets/upload",
        files={"file": (filename, payload)},
        data={
            "org_id": org_id,
            "asset_type": asset_type,
            "event_name": event_name,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def _assert_gcs_object_exists(bucket: str, blob_name: str, project_id: str) -> None:
    client = storage.Client(project=project_id)
    exists = client.bucket(bucket).blob(blob_name).exists()
    assert exists, f"Expected GCS object missing: gs://{bucket}/{blob_name}"


def _fetch_asset_row(project_id: str, dataset: str, table: str, asset_id: str) -> Dict[str, object]:
    client = bigquery.Client(project=project_id)
    table_fqn = f"{project_id}.{dataset}.{table}"
    rows = client.query(
        f"SELECT * FROM `{table_fqn}` WHERE asset_id = @asset_id LIMIT 1",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("asset_id", "STRING", asset_id)]
        ),
    ).result()
    items = [dict(row.items()) for row in rows]
    assert items, f"No asset record found for asset_id={asset_id}"
    return items[0]


def _fingerprint_status(row: Dict[str, object]) -> Optional[str]:
    direct = row.get("fingerprint_status")
    if isinstance(direct, str):
        return direct
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("fingerprint_status")
        if isinstance(value, str):
            return value
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                value = parsed.get("fingerprint_status")
                if isinstance(value, str):
                    return value
        except Exception:
            return None
    return None


def _assert_pubsub_message(
    *,
    subscriber: pubsub_v1.SubscriberClient,
    subscription_path: str,
    expected_asset_id: str,
    wait_seconds: int = 20,
) -> None:
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        try:
            pulled = subscriber.pull(
                request={"subscription": subscription_path, "max_messages": 10},
                timeout=5,
            )
        except DeadlineExceeded:
            time.sleep(1)
            continue
        if not pulled.received_messages:
            time.sleep(1)
            continue
        ack_ids = []
        for item in pulled.received_messages:
            ack_ids.append(item.ack_id)
            payload = json.loads(item.message.data.decode("utf-8"))
            if payload.get("asset_id") == expected_asset_id:
                subscriber.acknowledge(
                    request={"subscription": subscription_path, "ack_ids": ack_ids}
                )
                return
        subscriber.acknowledge(request={"subscription": subscription_path, "ack_ids": ack_ids})
    raise AssertionError(f"No Pub/Sub message found for asset_id={expected_asset_id}")


def _create_temp_subscription(project_id: str, topic_name: str) -> Tuple[pubsub_v1.SubscriberClient, str]:
    subscriber = pubsub_v1.SubscriberClient()
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_name)
    subscription_id = f"ingest-test-{int(time.time())}"
    subscription_path = subscriber.subscription_path(project_id, subscription_id)
    subscriber.create_subscription(name=subscription_path, topic=topic_path)
    return subscriber, subscription_path


def _keyframes_prefix_exists(project_id: str, bucket: str, asset_id: str) -> bool:
    client = storage.Client(project=project_id)
    blobs = client.list_blobs(bucket, prefix=f"assets/{asset_id}/keyframes/")
    return any(True for _ in blobs)


def run() -> None:
    _load_setup_env_if_present()
    base_url = os.getenv("INGEST_BASE_URL", "http://localhost:8080")
    project_id = _require_env("GCP_PROJECT_ID")
    raw_bucket = _require_env("GCS_RAW_BUCKET")
    keyframes_bucket = os.getenv("GCS_KEYFRAMES_BUCKET", raw_bucket)
    dataset = os.getenv("BQ_ASSETS_DATASET", _require_env("BQ_DATASET"))
    assets_table = os.getenv("BQ_ASSETS_TABLE", "assets")
    topic = os.getenv("PUBSUB_ASSET_TOPIC", "asset-uploaded")
    org_id = os.getenv("TEST_ORG_ID", "test-org")
    event_name = os.getenv("TEST_EVENT_NAME", "ingest-e2e")

    subscriber, subscription_path = _create_temp_subscription(project_id, topic)
    try:
        image_resp = _upload_asset(
            base_url=base_url,
            filename="sample.jpg",
            payload=_create_sample_image(),
            asset_type="image",
            org_id=org_id,
            event_name=event_name,
        )
        image_asset_id = image_resp["asset_id"]
        _assert_gcs_object_exists(raw_bucket, f"assets/{image_asset_id}/original.jpg", project_id)
        image_row = _fetch_asset_row(project_id, dataset, assets_table, image_asset_id)
        assert _fingerprint_status(image_row) == "pending"
        _assert_pubsub_message(
            subscriber=subscriber,
            subscription_path=subscription_path,
            expected_asset_id=image_asset_id,
        )

        video_resp = _upload_asset(
            base_url=base_url,
            filename="sample.mp4",
            payload=_create_sample_video(),
            asset_type="video",
            org_id=org_id,
            event_name=event_name,
        )
        video_asset_id = video_resp["asset_id"]
        _assert_gcs_object_exists(raw_bucket, f"assets/{video_asset_id}/original.mp4", project_id)
        assert _keyframes_prefix_exists(project_id, keyframes_bucket, video_asset_id), "Expected keyframes missing."
        video_row = _fetch_asset_row(project_id, dataset, assets_table, video_asset_id)
        assert _fingerprint_status(video_row) == "pending"
        _assert_pubsub_message(
            subscriber=subscriber,
            subscription_path=subscription_path,
            expected_asset_id=video_asset_id,
        )
    finally:
        subscriber.delete_subscription(request={"subscription": subscription_path})

    print("Ingest upload test passed for image + video.")


if __name__ == "__main__":
    run()
