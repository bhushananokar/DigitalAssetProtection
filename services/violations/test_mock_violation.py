from __future__ import annotations

import json
import os
import time
from pathlib import Path
from uuid import uuid4

from google.cloud import bigquery, pubsub_v1

from services.violations.subscriber import create_default_subscriber


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
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


def main() -> None:
    _load_setup_env_if_present()
    project_id = _require("GCP_PROJECT_ID")
    topic_name = os.getenv("PUBSUB_MATCH_TOPIC", "match-found")
    dataset = os.getenv("BQ_ASSETS_DATASET", _require("BQ_DATASET"))
    violations_table = os.getenv("BQ_VIOLATIONS_TABLE", "violations")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, topic_name)

    unique = str(uuid4())
    payload = {
        "source_url": f"https://example.com/mock/{unique}",
        "matched_asset_id": f"asset-{unique}",
        "similarity_score": 0.91,
        "platform": "youtube",
        "discovered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    publisher.publish(topic_path, data=json.dumps(payload).encode("utf-8")).result(timeout=20)
    print(f"Published mock match event to {topic_name}: {payload}")

    # Process directly through subscriber logic so this test does not depend on
    # a separate long-running worker being active during development.
    created = create_default_subscriber().process_payload(payload)
    assert created is not None, "Mock message should produce a violation row."

    client = bigquery.Client(project=project_id)
    table_fqn = f"{project_id}.{dataset}.{violations_table}"
    table = client.get_table(table_fqn)
    column_names = {field.name for field in table.schema}
    order_col = "created_at" if "created_at" in column_names else "discovered_at"
    query = f"""
    SELECT violation_id, severity, status, source_url, similarity_score
    FROM `{table_fqn}`
    WHERE source_url = @source_url
    ORDER BY {order_col} DESC
    LIMIT 1
    """
    rows = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("source_url", "STRING", payload["source_url"])]
        ),
    ).result()
    items = [dict(r.items()) for r in rows]
    assert items, "Expected violation row to be present in BigQuery."
    latest = items[0]
    assert latest["severity"] == "high", f"Expected high severity, got {latest['severity']}"
    assert latest["status"] == "open", f"Expected open status, got {latest['status']}"
    print(f"Violation created and verified: {latest}")


if __name__ == "__main__":
    main()
