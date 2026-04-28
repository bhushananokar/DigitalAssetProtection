from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from google.cloud import bigquery

from services.anomaly.detector import create_default_detector


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


def _table_columns(client: bigquery.Client, table_fqn: str) -> set[str]:
    return {f.name for f in client.get_table(table_fqn).schema}


def _seed_rows(client: bigquery.Client, table_fqn: str) -> Dict[str, str]:
    cols = _table_columns(client, table_fqn)
    asset_col = "asset_id" if "asset_id" in cols else "matched_asset_id"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    marker = f"anomaly-test-{uuid4().hex[:8]}"
    asset_spike = f"{marker}-spike"
    asset_coord = f"{marker}-coord"
    asset_cluster = f"{marker}-cluster"

    rows: list[Dict[str, Any]] = []

    # Spike: >10 in last 60 minutes.
    for i in range(11):
        row = {
            "violation_id": str(uuid4()),
            asset_col: asset_spike,
            "source_url": f"https://spike.example/{i}",
            "platform": "youtube",
            "similarity_score": 0.92,
            "severity": "high",
            "status": "open",
            "anomaly_flagged": False,
            "discovered_at": now,
        }
        if "evidence_uri" in cols:
            row["evidence_uri"] = ""
        rows.append({k: v for k, v in row.items() if k in cols})

    # Coordinated: >5 distinct source_url in last 10 minutes.
    for i in range(6):
        row = {
            "violation_id": str(uuid4()),
            asset_col: asset_coord,
            "source_url": f"https://coord.example/{i}",
            "platform": "youtube",
            "similarity_score": 0.88,
            "severity": "medium",
            "status": "open",
            "anomaly_flagged": False,
            "discovered_at": now,
        }
        if "evidence_uri" in cols:
            row["evidence_uri"] = ""
        rows.append({k: v for k, v in row.items() if k in cols})

    # Platform cluster: >=3 distinct platforms in last 30 minutes.
    for platform in ("youtube", "x", "instagram"):
        row = {
            "violation_id": str(uuid4()),
            asset_col: asset_cluster,
            "source_url": f"https://cluster.example/{platform}",
            "platform": platform,
            "similarity_score": 0.96,
            "severity": "critical",
            "status": "open",
            "anomaly_flagged": False,
            "discovered_at": now,
        }
        if "evidence_uri" in cols:
            row["evidence_uri"] = ""
        rows.append({k: v for k, v in row.items() if k in cols})

    load_job = client.load_table_from_json(rows, table_fqn)
    load_job.result()

    return {
        "marker": marker,
        "spike": asset_spike,
        "coord": asset_coord,
        "cluster": asset_cluster,
    }


def _assert_flagged(client: bigquery.Client, table_fqn: str, asset_id: str, expected_type: str) -> None:
    cols = _table_columns(client, table_fqn)
    asset_col = "asset_id" if "asset_id" in cols else "matched_asset_id"
    where_parts = [f"{asset_col} = @asset_id"]
    if "anomaly_flagged" in cols:
        where_parts.append("anomaly_flagged = TRUE")
    if "anomaly_type" in cols:
        where_parts.append("anomaly_type = @anomaly_type")
    sql = f"""
    SELECT COUNT(1) AS flagged
    FROM `{table_fqn}`
    WHERE {" AND ".join(where_parts)}
    """
    rows = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("asset_id", "STRING", asset_id),
                bigquery.ScalarQueryParameter("anomaly_type", "STRING", expected_type),
            ]
        ),
    ).result()
    count = int(next(rows)["flagged"])
    assert count > 0, f"Expected flagged rows for {asset_id} with type={expected_type}, got 0"


def main() -> None:
    _load_setup_env_if_present()
    project_id = _require("GCP_PROJECT_ID")
    dataset = os.getenv("BQ_ASSETS_DATASET", _require("BQ_DATASET"))
    base_table = os.getenv("BQ_VIOLATIONS_TABLE", "violations")
    base_table_fqn = f"{project_id}.{dataset}.{base_table}"
    bq = bigquery.Client(project=project_id)
    temp_table = f"{base_table}_anomaly_test_{uuid4().hex[:8]}"
    temp_table_fqn = f"{project_id}.{dataset}.{temp_table}"

    # Isolate this test from streaming-buffer churn in the shared live table.
    create_sql = f"""
    CREATE TABLE `{temp_table_fqn}` AS
    SELECT * FROM `{base_table_fqn}` WHERE 1=0
    """
    bq.query(create_sql).result()

    previous_table = os.getenv("BQ_VIOLATIONS_TABLE")
    os.environ["BQ_VIOLATIONS_TABLE"] = temp_table
    try:
        seeded = _seed_rows(bq, temp_table_fqn)
        result = create_default_detector().run()
        print(f"Detector run result: {result}")

        _assert_flagged(bq, temp_table_fqn, seeded["spike"], "spike")
        _assert_flagged(bq, temp_table_fqn, seeded["coord"], "coordinated")
        _assert_flagged(bq, temp_table_fqn, seeded["cluster"], "platform_cluster")
        print(f"Anomaly detector test passed for marker={seeded['marker']}")
    finally:
        if previous_table is None:
            os.environ.pop("BQ_VIOLATIONS_TABLE", None)
        else:
            os.environ["BQ_VIOLATIONS_TABLE"] = previous_table
        bq.delete_table(temp_table_fqn, not_found_ok=True)


if __name__ == "__main__":
    main()
