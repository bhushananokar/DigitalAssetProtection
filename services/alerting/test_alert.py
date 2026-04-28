from __future__ import annotations

import base64
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from google.api_core.exceptions import AlreadyExists
from google.cloud import bigquery, pubsub_v1, storage

from services.alerting.main import handle_high_severity_violation


def _load_setup_env_if_present() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    env_path = root / "setup.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


class _WebhookHandler(BaseHTTPRequestHandler):
    payloads: list[Dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        _WebhookHandler.payloads.append(parsed)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def _start_webhook_server(port: int) -> tuple[HTTPServer, threading.Thread]:
    server = HTTPServer(("127.0.0.1", port), _WebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _table_columns(client: bigquery.Client, table_fqn: str) -> set[str]:
    return {f.name for f in client.get_table(table_fqn).schema}


def _insert_asset_if_needed(
    client: bigquery.Client,
    assets_fqn: str,
    asset_id: str,
    org_id: str,
    asset_name: str,
) -> None:
    columns = _table_columns(client, assets_fqn)
    row: Dict[str, Any] = {}
    if "asset_id" in columns:
        row["asset_id"] = asset_id
    if "org_id" in columns:
        row["org_id"] = org_id
    if "asset_name" in columns:
        row["asset_name"] = asset_name
    if "event_name" in columns and "asset_name" not in columns:
        row["event_name"] = asset_name
    if "asset_type" in columns:
        row["asset_type"] = "video"
    if "storage_uri" in columns:
        row["storage_uri"] = f"gs://dummy/{asset_id}.mp4"
    if "fingerprint_status" in columns:
        row["fingerprint_status"] = "ready"
    if "deleted" in columns:
        row["deleted"] = False
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if "created_at" in columns:
        row["created_at"] = now
    if "updated_at" in columns:
        row["updated_at"] = now
    if not row:
        return
    client.insert_rows_json(assets_fqn, [row])


def _insert_violation(
    client: bigquery.Client,
    violations_fqn: str,
    *,
    violation_id: str,
    matched_asset_id: str,
    source_url: str,
) -> None:
    columns = _table_columns(client, violations_fqn)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row: Dict[str, Any] = {
        "violation_id": violation_id,
        "source_url": source_url,
        "similarity_score": 0.97,
        "severity": "critical",
        "platform": "youtube",
        "status": "open",
        "anomaly_flagged": False,
        "discovered_at": now,
    }
    if "matched_asset_id" in columns:
        row["matched_asset_id"] = matched_asset_id
    if "asset_id" in columns:
        row["asset_id"] = matched_asset_id
    if "evidence_uri" in columns:
        row["evidence_uri"] = ""
    if "org_id" in columns:
        row["org_id"] = "test-org"
    if "created_at" in columns:
        row["created_at"] = now
    if "updated_at" in columns:
        row["updated_at"] = now
    filtered = {k: v for k, v in row.items() if k in columns}
    errors = client.insert_rows_json(violations_fqn, [filtered])
    if errors:
        raise RuntimeError(f"Failed to insert violation test row: {errors!r}")


def _read_bundle(
    gcs: storage.Client, bucket_name: str, violation_id: str
) -> Optional[Dict[str, Any]]:
    blob = gcs.bucket(bucket_name).blob(f"evidence/{violation_id}/bundle.json")
    if not blob.exists():
        return None
    payload = blob.download_as_bytes().decode("utf-8")
    return json.loads(payload)


def main() -> None:
    _load_setup_env_if_present()
    project_id = _require("GCP_PROJECT_ID")
    dataset = os.getenv("BQ_ASSETS_DATASET", _require("BQ_DATASET"))
    assets_table = os.getenv("BQ_ASSETS_TABLE", "assets")
    violations_table = os.getenv("BQ_VIOLATIONS_TABLE", "violations")
    high_topic = os.getenv("PUBSUB_HIGH_SEVERITY_TOPIC", "high-severity-violation")
    evidence_bucket = os.getenv("GCS_EVIDENCE_BUCKET", _require("GCS_RAW_BUCKET"))

    bq = bigquery.Client(project=project_id)
    gcs = storage.Client(project=project_id)
    pub = pubsub_v1.PublisherClient()

    violation_id = str(uuid4())
    matched_asset_id = f"asset-{uuid4()}"
    source_url = "https://example.com"

    assets_fqn = f"{project_id}.{dataset}.{assets_table}"
    violations_fqn = f"{project_id}.{dataset}.{violations_table}"
    _insert_asset_if_needed(bq, assets_fqn, matched_asset_id, "test-org", "Test Match Asset")
    _insert_violation(
        bq,
        violations_fqn,
        violation_id=violation_id,
        matched_asset_id=matched_asset_id,
        source_url=source_url,
    )

    webhook_port = 8765
    server, thread = _start_webhook_server(webhook_port)
    os.environ["ALERT_WEBHOOK_URL"] = f"http://127.0.0.1:{webhook_port}"
    try:
        message = {"violation_id": violation_id}
        topic_path = pub.topic_path(project_id, high_topic)
        try:
            pub.create_topic(request={"name": topic_path})
        except AlreadyExists:
            pass
        pub.publish(topic_path, data=json.dumps(message).encode("utf-8")).result(timeout=20)
        print(f"Published fake high-severity event to {high_topic}: {message}")

        event = {"data": base64.b64encode(json.dumps(message).encode("utf-8")).decode("utf-8")}
        handle_high_severity_violation(event, None)
        time.sleep(1)

        bundle = _read_bundle(gcs, evidence_bucket, violation_id)
        assert bundle is not None, "Evidence bundle not found in GCS."
        assert bundle.get("matched_asset_id") == matched_asset_id
        assert _WebhookHandler.payloads, "Webhook did not receive alert POST."
        print(f"Evidence bundle stored: gs://{evidence_bucket}/evidence/{violation_id}/bundle.json")
        print(f"Webhook payload received: {_WebhookHandler.payloads[-1]}")
    finally:
        server.shutdown()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
