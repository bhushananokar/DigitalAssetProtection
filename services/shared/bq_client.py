from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from google.cloud import bigquery

from services.shared.config import SETTINGS


@dataclass
class BqClient:
    client: bigquery.Client

    @classmethod
    def default(cls) -> "BqClient":
        return cls(client=bigquery.Client(project=SETTINGS.gcp_project_id))

    def insert_rows_json(self, table_fqn: str, rows: List[Dict[str, Any]]) -> None:
        errors = self.client.insert_rows_json(table_fqn, rows)
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors!r}")

    def query(
        self,
        sql: str,
        params: Optional[Iterable[bigquery.ScalarQueryParameter]] = None,
    ) -> List[Dict[str, Any]]:
        job_config = bigquery.QueryJobConfig()
        if params is not None:
            job_config.query_parameters = list(params)
        it = self.client.query(sql, job_config=job_config).result()
        return [dict(row.items()) for row in it]

    def get_table_schema(self, table_fqn: str) -> Dict[str, bigquery.SchemaField]:
        table = self.client.get_table(table_fqn)
        return {f.name: f for f in table.schema}
