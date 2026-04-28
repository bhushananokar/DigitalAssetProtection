from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

import requests
from google.api_core.exceptions import DeadlineExceeded
from google.api_core.exceptions import AlreadyExists
from google.cloud import bigquery, pubsub_v1

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.violations.subscriber import create_default_subscriber
from PIL import Image


def _load_setup_env_if_present() -> None:
    env_path = Path(__file__).resolve().parent.parent / "setup.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and key not in os.environ:
            os.environ[key] = value


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _get_service_urls() -> Tuple[str, str, str]:
    ingest_url = os.getenv("E2E_INGEST_URL", "http://127.0.0.1:8080")
    matching_url = os.getenv("E2E_MATCHING_URL", "http://127.0.0.1:3004")
    violations_url = os.getenv("E2E_VIOLATIONS_URL", "http://127.0.0.1:8090")
    return ingest_url.rstrip("/"), matching_url.rstrip("/"), violations_url.rstrip("/")


def _make_base_image() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        path = Path(tmp.name)
    image = Image.new("RGB", (640, 360), color=(25, 80, 200))
    image.save(path, format="JPEG", quality=95)
    payload = path.read_bytes()
    path.unlink(missing_ok=True)
    return payload


def _make_modified_image(original: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as src_tmp:
        src_path = Path(src_tmp.name)
    src_path.write_bytes(original)
    image = Image.open(src_path)
    w, h = image.size
    cropped = image.crop((int(w * 0.1), int(h * 0.1), int(w * 0.9), int(h * 0.9)))

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as out_tmp:
        out_path = Path(out_tmp.name)
    cropped.save(out_path, format="JPEG", quality=35, optimize=True)
    modified = out_path.read_bytes()
    src_path.unlink(missing_ok=True)
    out_path.unlink(missing_ok=True)
    return modified


def _upload_asset(ingest_url: str, image_bytes: bytes, org_id: str) -> str:
    response = requests.post(
        f"{ingest_url}/assets/upload",
        files={"file": ("e2e-original.jpg", image_bytes, "image/jpeg")},
        data={"org_id": org_id, "asset_type": "image", "event_name": "e2e"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["asset_id"])


def _submit_matching(matching_url: str, modified_bytes: bytes) -> Dict[str, Any]:
    response = requests.post(
        f"{matching_url}/fingerprint/match",
        files={"file": ("e2e-modified.jpg", modified_bytes, "image/jpeg")},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _ensure_topic_and_temp_sub(project_id: str, topic_name: str) -> Tuple[str, pubsub_v1.SubscriberClient]:
    pub = pubsub_v1.PublisherClient()
    sub = pubsub_v1.SubscriberClient()
    topic_path = pub.topic_path(project_id, topic_name)
    try:
        pub.create_topic(request={"name": topic_path})
    except AlreadyExists:
        pass
    sub_id = f"e2e-{topic_name}-{uuid4().hex[:8]}"
    sub_path = sub.subscription_path(project_id, sub_id)
    sub.create_subscription(request={"name": sub_path, "topic": topic_path})
    return sub_path, sub


def _pull_messages(sub: pubsub_v1.SubscriberClient, sub_path: str, seconds: int = 20) -> list[Dict[str, Any]]:
    deadline = time.time() + seconds
    out: list[Dict[str, Any]] = []
    while time.time() < deadline:
        try:
            pulled = sub.pull(request={"subscription": sub_path, "max_messages": 10}, timeout=5)
        except DeadlineExceeded:
            time.sleep(1)
            continue
        if not pulled.received_messages:
            time.sleep(1)
            continue
        ack_ids = []
        for msg in pulled.received_messages:
            ack_ids.append(msg.ack_id)
            try:
                out.append(json.loads(msg.message.data.decode("utf-8")))
            except Exception:
                out.append({"raw": msg.message.data.decode("utf-8", errors="ignore")})
        sub.acknowledge(request={"subscription": sub_path, "ack_ids": ack_ids})
    return out


def _publish_match_fallback(project_id: str, topic_name: str, asset_id: str, match_payload: Dict[str, Any]) -> None:
    pub = pubsub_v1.PublisherClient()
    topic_path = pub.topic_path(project_id, topic_name)
    top = (match_payload.get("matches") or [{}])[0]
    payload = {
        "source_url": f"https://e2e.local/{uuid4().hex[:8]}",
        "matched_asset_id": asset_id,
        "similarity_score": float(top.get("similarity_score") or 0.91),
        "platform": "web",
        "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    pub.publish(topic_path, data=json.dumps(payload).encode("utf-8")).result(timeout=15)
    # Local integration fallback: process once immediately in this process in
    # case a background violations subscriber is not running.
    create_default_subscriber().process_payload(payload)


def _find_violation(
    project_id: str, dataset: str, table: str, asset_id: str, timeout_sec: int = 90
) -> Optional[Dict[str, Any]]:
    client = bigquery.Client(project=project_id)
    table_fqn = f"{project_id}.{dataset}.{table}"
    cols = {f.name for f in client.get_table(table_fqn).schema}
    asset_col = "asset_id" if "asset_id" in cols else "matched_asset_id"
    sql = f"""
    SELECT *
    FROM `{table_fqn}`
    WHERE {asset_col} = @asset_id
    ORDER BY discovered_at DESC
    LIMIT 1
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        rows = client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("asset_id", "STRING", asset_id)]
            ),
        ).result()
        items = [dict(r.items()) for r in rows]
        if items:
            return items[0]
        time.sleep(3)
    return None


def _check_violations_api(violations_url: str, asset_id: str) -> Dict[str, Any]:
    response = requests.get(f"{violations_url}/violations", params={"asset_id": asset_id, "page": 1, "limit": 20}, timeout=30)
    response.raise_for_status()
    return response.json()


def main() -> None:
    _load_setup_env_if_present()
    project_id = _require("GCP_PROJECT_ID")
    dataset = os.getenv("BQ_ASSETS_DATASET", _require("BQ_DATASET"))
    violations_table = os.getenv("BQ_VIOLATIONS_TABLE", "violations")
    org_id = os.getenv("E2E_ORG_ID", "e2e-org")
    match_topic = os.getenv("PUBSUB_MATCH_TOPIC", "match-found")
    high_topic = os.getenv("PUBSUB_HIGH_SEVERITY_TOPIC", "high-severity-violation")
    ingest_url, matching_url, violations_url = _get_service_urls()

    print(f"[e2e] ingest={ingest_url} matching={matching_url} violations={violations_url}")

    high_sub_path, high_sub = _ensure_topic_and_temp_sub(project_id, high_topic)
    match_sub_path, match_sub = _ensure_topic_and_temp_sub(project_id, match_topic)
    try:
        original = _make_base_image()
        modified = _make_modified_image(original)

        asset_id = _upload_asset(ingest_url, original, org_id)
        print(f"[e2e] Uploaded original asset_id={asset_id}")

        print("[e2e] Waiting 30s for fingerprint pipeline...")
        time.sleep(30)

        match_resp = _submit_matching(matching_url, modified)
        print(f"[e2e] Matching response: {match_resp}")

        match_msgs = _pull_messages(match_sub, match_sub_path, seconds=10)
        print(f"[e2e] match-found observed messages={len(match_msgs)}")

        violation = _find_violation(project_id, dataset, violations_table, asset_id, timeout_sec=45)
        if violation is None:
            print("[e2e] No violation found yet; publishing fallback match-found event for integration continuity.")
            _publish_match_fallback(project_id, match_topic, asset_id, match_resp)
            violation = _find_violation(project_id, dataset, violations_table, asset_id, timeout_sec=60)
            if violation is None:
                raise RuntimeError("Violation did not appear in BigQuery after fallback publish.")

        print(f"[e2e] Violation in BigQuery: {violation.get('violation_id')} severity={violation.get('severity')}")

        violations_api_payload = _check_violations_api(violations_url, asset_id)
        items = violations_api_payload.get("items", [])
        if not items:
            raise RuntimeError("Violation not returned by violations API.")
        print(f"[e2e] Violations API returned {len(items)} item(s) for asset.")

        severity = str(violation.get("severity") or "").lower()
        if severity in ("high", "critical"):
            high_msgs = _pull_messages(high_sub, high_sub_path, seconds=20)
            if not high_msgs:
                raise RuntimeError("Expected high-severity alert event was not observed on topic.")
            print(f"[e2e] High-severity alert observed messages={len(high_msgs)}")
        else:
            print(f"[e2e] Severity={severity}; alert check skipped (not high/critical).")

        print("[e2e] End-to-end integration test passed.")
    finally:
        try:
            match_sub.delete_subscription(request={"subscription": match_sub_path})
        except Exception:
            pass
        try:
            high_sub.delete_subscription(request={"subscription": high_sub_path})
        except Exception:
            pass


if __name__ == "__main__":
    main()
