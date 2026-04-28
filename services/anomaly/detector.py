from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from google.cloud import bigquery, pubsub_v1


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


@dataclass
class AnomalyDetector:
    project_id: str
    dataset: str
    violations_table: str
    high_severity_topic: str
    bq: Optional[bigquery.Client] = None
    pubsub: Optional[pubsub_v1.PublisherClient] = None
    _columns: Optional[Set[str]] = None

    def __post_init__(self) -> None:
        if self.bq is None:
            self.bq = bigquery.Client(project=self.project_id)
        if self.pubsub is None:
            self.pubsub = pubsub_v1.PublisherClient()

    @property
    def violations_fqn(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.violations_table}"

    @property
    def topic_path(self) -> str:
        return self.pubsub.topic_path(self.project_id, self.high_severity_topic)

    def _load_columns(self) -> Set[str]:
        if self._columns is None:
            self._columns = {field.name for field in self.bq.get_table(self.violations_fqn).schema}
        return self._columns

    def _asset_column(self) -> str:
        columns = self._load_columns()
        if "asset_id" in columns:
            return "asset_id"
        if "matched_asset_id" in columns:
            return "matched_asset_id"
        raise RuntimeError("Violations table must include either asset_id or matched_asset_id")

    def _time_column(self) -> str:
        columns = self._load_columns()
        if "discovered_at" in columns:
            return "discovered_at"
        if "created_at" in columns:
            return "created_at"
        raise RuntimeError("Violations table must include discovered_at or created_at")

    def _query_asset_ids(self, sql: str) -> List[str]:
        rows = self.bq.query(sql).result()
        return [str(row["asset_ref"]) for row in rows if row.get("asset_ref")]

    def _set_anomaly_for_assets(self, anomaly_type: str, asset_ids: List[str]) -> List[Dict[str, Any]]:
        if not asset_ids:
            return []
        columns = self._load_columns()
        asset_col = self._asset_column()
        time_col = self._time_column()
        params = [
            bigquery.ArrayQueryParameter("asset_ids", "STRING", asset_ids),
            bigquery.ScalarQueryParameter("anomaly_type", "STRING", anomaly_type),
            bigquery.ScalarQueryParameter("now", "TIMESTAMP", datetime.now(timezone.utc)),
        ]
        set_parts = []
        if "anomaly_flagged" in columns:
            set_parts.append("anomaly_flagged = TRUE")
        if "anomaly_type" in columns:
            set_parts.append("anomaly_type = @anomaly_type")
        if "updated_at" in columns:
            set_parts.append("updated_at = @now")
        if not set_parts:
            raise RuntimeError("Violations table missing anomaly columns.")

        update_sql = f"""
        UPDATE `{self.violations_fqn}`
        SET {", ".join(set_parts)}
        WHERE {asset_col} IN UNNEST(@asset_ids)
          AND {time_col} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 MINUTE)
        """
        self.bq.query(update_sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()

        # Read back flagged rows in this run window for optional re-publish.
        where_parts = [
            f"{asset_col} IN UNNEST(@asset_ids)",
            f"{time_col} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 MINUTE)",
        ]
        if "anomaly_flagged" in columns:
            where_parts.append("anomaly_flagged = TRUE")
        if "anomaly_type" in columns:
            where_parts.append("anomaly_type = @anomaly_type")
        select_sql = f"""
        SELECT violation_id, {asset_col} AS asset_ref, severity, source_url, platform, similarity_score, {time_col} AS discovered_at
        FROM `{self.violations_fqn}`
        WHERE {" AND ".join(where_parts)}
        """
        result_rows = self.bq.query(
            select_sql, job_config=bigquery.QueryJobConfig(query_parameters=params[:2])
        ).result()
        return [dict(row.items()) for row in result_rows]

    def _republish_high_severity(self, flagged_rows: List[Dict[str, Any]], anomaly_type: str) -> None:
        for row in flagged_rows:
            severity = str(row.get("severity") or "").lower()
            if severity not in ("high", "critical"):
                continue
            payload = {
                "violation_id": row.get("violation_id"),
                "matched_asset_id": row.get("asset_ref"),
                "severity": severity,
                "source_url": row.get("source_url"),
                "platform": row.get("platform"),
                "similarity_score": row.get("similarity_score"),
                "discovered_at": str(row.get("discovered_at") or ""),
                "anomaly_flagged": True,
                "anomaly_type": anomaly_type,
            }
            self.pubsub.publish(self.topic_path, data=json.dumps(payload, default=str).encode("utf-8"))

    def run(self) -> Dict[str, Any]:
        asset_col = self._asset_column()
        time_col = self._time_column()
        run_id = os.urandom(8).hex()
        started_at = datetime.now(timezone.utc).isoformat()

        spike_sql = f"""
        SELECT {asset_col} AS asset_ref
        FROM `{self.violations_fqn}`
        WHERE {time_col} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 MINUTE)
        GROUP BY asset_ref
        HAVING COUNT(1) > 10
        """
        coordinated_sql = f"""
        SELECT {asset_col} AS asset_ref
        FROM `{self.violations_fqn}`
        WHERE {time_col} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 10 MINUTE)
        GROUP BY asset_ref
        HAVING COUNT(DISTINCT source_url) > 5
        """
        platform_cluster_sql = f"""
        SELECT {asset_col} AS asset_ref
        FROM `{self.violations_fqn}`
        WHERE {time_col} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 MINUTE)
        GROUP BY asset_ref
        HAVING COUNT(DISTINCT platform) >= 3
        """

        spike_assets = self._query_asset_ids(spike_sql)
        coordinated_assets = self._query_asset_ids(coordinated_sql)
        platform_cluster_assets = self._query_asset_ids(platform_cluster_sql)

        all_flagged_violation_ids: Set[str] = set()
        breakdown: Dict[str, int] = {}

        for anomaly_type, asset_ids in (
            ("spike", spike_assets),
            ("coordinated", coordinated_assets),
            ("platform_cluster", platform_cluster_assets),
        ):
            rows = self._set_anomaly_for_assets(anomaly_type, asset_ids)
            self._republish_high_severity(rows, anomaly_type)
            breakdown[anomaly_type] = len(rows)
            for row in rows:
                vid = row.get("violation_id")
                if vid:
                    all_flagged_violation_ids.add(str(vid))

        return {
            "run_id": run_id,
            "started_at": started_at,
            "violations_flagged": len(all_flagged_violation_ids),
            "breakdown": breakdown,
        }


def create_default_detector() -> AnomalyDetector:
    project_id = _require("GCP_PROJECT_ID")
    dataset = _getenv("BQ_ASSETS_DATASET", _getenv("BQ_DATASET", "digital_asset_protection"))
    return AnomalyDetector(
        project_id=project_id,
        dataset=dataset,
        violations_table=_getenv("BQ_VIOLATIONS_TABLE", "violations"),
        high_severity_topic=_getenv("PUBSUB_HIGH_SEVERITY_TOPIC", "high-severity-violation"),
    )
