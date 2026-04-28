from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from google.cloud import bigquery


@dataclass
class ViolationsBigQuery:
    project_id: str
    dataset: str
    violations_table: str
    assets_table: str
    client: Optional[bigquery.Client] = None
    _violations_columns: Optional[set[str]] = None
    _assets_columns: Optional[set[str]] = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = bigquery.Client(project=self.project_id)

    @property
    def violations_fqn(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.violations_table}"

    @property
    def assets_fqn(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.assets_table}"

    def _load_violations_columns(self) -> set[str]:
        if self._violations_columns is None:
            table = self.client.get_table(self.violations_fqn)
            self._violations_columns = {field.name for field in table.schema}
        return self._violations_columns

    def _load_assets_columns(self) -> set[str]:
        if self._assets_columns is None:
            table = self.client.get_table(self.assets_fqn)
            self._assets_columns = {field.name for field in table.schema}
        return self._assets_columns

    def _filter_violation_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        columns = self._load_violations_columns()
        return {k: v for k, v in record.items() if k in columns}

    def insert_violation(self, record: Dict[str, Any]) -> None:
        row = self._filter_violation_record(record)
        if not row:
            raise RuntimeError("No matching columns found for violations table insert.")
        errors = self.client.insert_rows_json(self.violations_fqn, [row])
        if errors:
            raise RuntimeError(f"BigQuery violation insert failed: {errors!r}")

    def get_asset_org_id(self, asset_id: str) -> Optional[str]:
        if "org_id" not in self._load_assets_columns():
            return None
        sql = f"""
        SELECT org_id
        FROM `{self.assets_fqn}`
        WHERE asset_id = @asset_id
        LIMIT 1
        """
        rows = self.client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("asset_id", "STRING", asset_id)]
            ),
        ).result()
        found = [dict(r.items()) for r in rows]
        return found[0]["org_id"] if found else None

    def list_violations(
        self,
        *,
        org_id: Optional[str],
        severity: Optional[str],
        status: Optional[str],
        platform: Optional[str],
        asset_id: Optional[str],
        from_date: Optional[date],
        to_date: Optional[date],
        anomaly_flagged: Optional[bool],
        page: int,
        limit: int,
    ) -> Dict[str, Any]:
        columns = self._load_violations_columns()
        conditions: List[str] = []
        params: List[bigquery.ScalarQueryParameter] = []

        def add_filter(column: str, name: str, value: Any, typ: str) -> None:
            if value is None or column not in columns:
                return
            conditions.append(f"{column} = @{name}")
            params.append(bigquery.ScalarQueryParameter(name, typ, value))

        add_filter("org_id", "org_id", org_id, "STRING")
        add_filter("severity", "severity", severity, "STRING")
        add_filter("status", "status", status, "STRING")
        add_filter("platform", "platform", platform, "STRING")
        if asset_id:
            if "asset_id" in columns:
                add_filter("asset_id", "asset_id", asset_id, "STRING")
            elif "matched_asset_id" in columns:
                add_filter("matched_asset_id", "asset_id", asset_id, "STRING")
        add_filter("anomaly_flagged", "anomaly_flagged", anomaly_flagged, "BOOL")

        date_column = "discovered_at" if "discovered_at" in columns else "created_at"
        if from_date and date_column in columns:
            conditions.append(f"DATE({date_column}) >= @from_date")
            params.append(bigquery.ScalarQueryParameter("from_date", "DATE", str(from_date)))
        if to_date and date_column in columns:
            conditions.append(f"DATE({date_column}) <= @to_date")
            params.append(bigquery.ScalarQueryParameter("to_date", "DATE", str(to_date)))

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order_column = "created_at" if "created_at" in columns else "updated_at"
        if order_column not in columns:
            order_column = "violation_id"

        offset = (page - 1) * limit
        paged_params = params + [
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
            bigquery.ScalarQueryParameter("offset", "INT64", offset),
        ]

        list_sql = f"""
        SELECT *
        FROM `{self.violations_fqn}`
        {where}
        ORDER BY {order_column} DESC
        LIMIT @limit OFFSET @offset
        """
        count_sql = f"""
        SELECT COUNT(1) AS total
        FROM `{self.violations_fqn}`
        {where}
        """
        items = self.client.query(
            list_sql, job_config=bigquery.QueryJobConfig(query_parameters=paged_params)
        ).result()
        count = self.client.query(
            count_sql, job_config=bigquery.QueryJobConfig(query_parameters=params)
        ).result()
        rows = [dict(r.items()) for r in items]
        total = int(next(count)["total"])
        return {"items": rows, "page": page, "limit": limit, "total": total}

    def get_violation(self, violation_id: str) -> Optional[Dict[str, Any]]:
        sql = f"""
        SELECT *
        FROM `{self.violations_fqn}`
        WHERE violation_id = @violation_id
        LIMIT 1
        """
        rows = self.client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("violation_id", "STRING", violation_id)]
            ),
        ).result()
        items = [dict(r.items()) for r in rows]
        return items[0] if items else None

    def update_violation_status(self, violation_id: str, status: str, note: Optional[str]) -> Optional[Dict[str, Any]]:
        columns = self._load_violations_columns()
        set_clauses = ["status = @status"] if "status" in columns else []
        params: List[bigquery.ScalarQueryParameter] = [
            bigquery.ScalarQueryParameter("violation_id", "STRING", violation_id),
            bigquery.ScalarQueryParameter("status", "STRING", status),
        ]
        if "updated_at" in columns:
            set_clauses.append("updated_at = @updated_at")
            params.append(bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", datetime.now(timezone.utc)))
        if "note" in columns:
            set_clauses.append("note = @note")
            params.append(bigquery.ScalarQueryParameter("note", "STRING", note or ""))
        if not set_clauses:
            raise RuntimeError("Violations table missing required updatable fields.")

        sql = f"""
        UPDATE `{self.violations_fqn}`
        SET {", ".join(set_clauses)}
        WHERE violation_id = @violation_id
        """
        self.client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        return self.get_violation(violation_id)

    def compute_stats(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        start_30 = now - timedelta(days=30)
        params = [bigquery.ScalarQueryParameter("start_30", "TIMESTAMP", start_30)]
        columns = self._load_violations_columns()
        if "discovered_at" in columns and "created_at" in columns:
            time_expr = "COALESCE(discovered_at, created_at)"
        elif "discovered_at" in columns:
            time_expr = "discovered_at"
        elif "created_at" in columns:
            time_expr = "created_at"
        else:
            time_expr = "CURRENT_TIMESTAMP()"

        overview_sql = f"""
        SELECT
          COUNT(1) AS total_violations,
          COUNTIF(status = 'open') AS open_violations,
          COUNTIF(severity = 'critical') AS critical_violations
        FROM `{self.violations_fqn}`
        """
        severity_sql = f"""
        SELECT severity, COUNT(1) AS count
        FROM `{self.violations_fqn}`
        GROUP BY severity
        ORDER BY count DESC
        """
        platform_sql = f"""
        SELECT platform, COUNT(1) AS count
        FROM `{self.violations_fqn}`
        GROUP BY platform
        ORDER BY count DESC
        """
        daily_sql = f"""
        SELECT DATE({time_expr}) AS day, COUNT(1) AS count
        FROM `{self.violations_fqn}`
        WHERE {time_expr} >= @start_30
        GROUP BY day
        ORDER BY day ASC
        """
        top_asset_col = "asset_id" if "asset_id" in columns else "matched_asset_id"
        top_assets_sql = f"""
        SELECT {top_asset_col} AS asset_id, COUNT(1) AS count
        FROM `{self.violations_fqn}`
        GROUP BY {top_asset_col}
        ORDER BY count DESC
        LIMIT 5
        """

        overview = [dict(r.items()) for r in self.client.query(overview_sql).result()]
        by_severity = [dict(r.items()) for r in self.client.query(severity_sql).result()]
        by_platform = [dict(r.items()) for r in self.client.query(platform_sql).result()]
        per_day = [
            {"day": str(r["day"]), "count": int(r["count"])}
            for r in self.client.query(
                daily_sql, job_config=bigquery.QueryJobConfig(query_parameters=params)
            ).result()
        ]
        top_assets = [dict(r.items()) for r in self.client.query(top_assets_sql).result()]

        baseline = overview[0] if overview else {}
        return {
            "total_violations": int(baseline.get("total_violations", 0)),
            "open_violations": int(baseline.get("open_violations", 0)),
            "critical_violations": int(baseline.get("critical_violations", 0)),
            "count_by_severity": by_severity,
            "count_by_platform": by_platform,
            "violations_per_day_30d": per_day,
            "top_assets": top_assets,
        }
