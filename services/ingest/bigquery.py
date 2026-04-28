from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from google.cloud import bigquery


@dataclass
class IngestBigQuery:
    project_id: str
    dataset: str
    assets_table: str
    violations_table: str
    client: Optional[bigquery.Client] = None
    _asset_columns: Optional[set[str]] = None
    _violation_columns: Optional[set[str]] = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = bigquery.Client(project=self.project_id)

    @property
    def assets_table_fqn(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.assets_table}"

    @property
    def violations_table_fqn(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.violations_table}"

    def _load_asset_columns(self) -> set[str]:
        if self._asset_columns is None:
            table = self.client.get_table(self.assets_table_fqn)
            self._asset_columns = {field.name for field in table.schema}
        return self._asset_columns

    def _filter_asset_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        columns = self._load_asset_columns()
        return {k: v for k, v in record.items() if k in columns}

    def _load_violation_columns(self) -> set[str]:
        if self._violation_columns is None:
            table = self.client.get_table(self.violations_table_fqn)
            self._violation_columns = {field.name for field in table.schema}
        return self._violation_columns

    def _violation_asset_column(self) -> Optional[str]:
        columns = self._load_violation_columns()
        if "asset_id" in columns:
            return "asset_id"
        if "matched_asset_id" in columns:
            return "matched_asset_id"
        return None

    @staticmethod
    def _metadata_as_dict(row: Dict[str, Any]) -> Dict[str, Any]:
        metadata = row.get("metadata")
        if metadata is None:
            return {}
        if isinstance(metadata, dict):
            return metadata
        if isinstance(metadata, str):
            try:
                import json

                parsed = json.loads(metadata)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    def _normalize_asset_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        metadata = self._metadata_as_dict(normalized)
        if "fingerprint_status" not in normalized and "fingerprint_status" in metadata:
            normalized["fingerprint_status"] = metadata.get("fingerprint_status")
        if "keyframe_uris" not in normalized and "keyframe_uris" in metadata:
            normalized["keyframe_uris"] = metadata.get("keyframe_uris")
        if "deleted" not in normalized and "deleted" in metadata:
            normalized["deleted"] = metadata.get("deleted")
        return normalized

    def insert_asset(self, record: Dict[str, Any]) -> None:
        filtered = self._filter_asset_record(record)
        if not filtered:
            raise RuntimeError("No valid asset fields matched BigQuery schema.")
        errors = self.client.insert_rows_json(self.assets_table_fqn, [filtered])
        if errors:
            raise RuntimeError(f"Failed to insert asset row: {errors!r}")

    def list_assets(
        self,
        *,
        org_id: Optional[str],
        asset_type: Optional[str],
        page: int,
        limit: int,
    ) -> Dict[str, Any]:
        conditions: List[str] = []
        params: List[bigquery.ScalarQueryParameter] = []
        columns = self._load_asset_columns()

        if "deleted" in columns:
            conditions.append("deleted = FALSE")
        if org_id:
            conditions.append("org_id = @org_id")
            params.append(bigquery.ScalarQueryParameter("org_id", "STRING", org_id))
        if asset_type:
            conditions.append("asset_type = @asset_type")
            params.append(bigquery.ScalarQueryParameter("asset_type", "STRING", asset_type))

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * limit
        params.extend(
            [
                bigquery.ScalarQueryParameter("limit", "INT64", limit),
                bigquery.ScalarQueryParameter("offset", "INT64", offset),
            ]
        )
        order_by = "created_at DESC" if "created_at" in columns else "asset_id DESC"
        sql = f"""
        SELECT *
        FROM `{self.assets_table_fqn}`
        {where_clause}
        ORDER BY {order_by}
        LIMIT @limit OFFSET @offset
        """
        count_sql = f"""
        SELECT COUNT(1) AS total
        FROM `{self.assets_table_fqn}`
        {where_clause}
        """
        job = self.client.query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        )
        rows = [self._normalize_asset_row(dict(row.items())) for row in job.result()]

        count_params = [p for p in params if p.name not in ("limit", "offset")]
        count_job = self.client.query(
            count_sql,
            job_config=bigquery.QueryJobConfig(query_parameters=count_params),
        )
        total = int(next(count_job.result())["total"])
        return {
            "items": rows,
            "page": page,
            "limit": limit,
            "total": total,
        }

    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        violation_asset_col = self._violation_asset_column()
        if violation_asset_col:
            sql = f"""
            SELECT a.*, COALESCE(v.violation_count, 0) AS violation_count
            FROM `{self.assets_table_fqn}` a
            LEFT JOIN (
                SELECT {violation_asset_col} AS asset_id, COUNT(1) AS violation_count
                FROM `{self.violations_table_fqn}`
                GROUP BY {violation_asset_col}
            ) v USING (asset_id)
            WHERE a.asset_id = @asset_id
            LIMIT 1
            """
        else:
            sql = f"""
            SELECT a.*, 0 AS violation_count
            FROM `{self.assets_table_fqn}` a
            WHERE a.asset_id = @asset_id
            LIMIT 1
            """
        job = self.client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("asset_id", "STRING", asset_id)]
            ),
        )
        rows = [self._normalize_asset_row(dict(row.items())) for row in job.result()]
        return rows[0] if rows else None

    def mark_deleted(self, asset_id: str, hard_delete: bool) -> None:
        now = datetime.now(timezone.utc)
        columns = self._load_asset_columns()
        set_clauses = []
        params: List[bigquery.ScalarQueryParameter] = [
            bigquery.ScalarQueryParameter("asset_id", "STRING", asset_id),
            bigquery.ScalarQueryParameter("now", "TIMESTAMP", now),
            bigquery.ScalarQueryParameter("hard_delete", "BOOL", hard_delete),
        ]

        if "deleted" in columns:
            set_clauses.append("deleted = TRUE")
        if "deleted_at" in columns:
            set_clauses.append("deleted_at = @now")
        if "updated_at" in columns:
            set_clauses.append("updated_at = @now")
        if "hard_deleted" in columns:
            set_clauses.append("hard_deleted = @hard_delete")

        if not set_clauses:
            # Best-effort no-op when schema does not model soft-delete.
            return

        sql = f"""
        UPDATE `{self.assets_table_fqn}`
        SET {", ".join(set_clauses)}
        WHERE asset_id = @asset_id
        """
        self.client.query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=params),
        ).result()
