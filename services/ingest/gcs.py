from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from google.cloud import storage


@dataclass
class GcsHelper:
    project_id: str
    client: Optional[storage.Client] = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = storage.Client(project=self.project_id)

    def upload_bytes(
        self,
        *,
        bucket: str,
        blob_name: str,
        payload: bytes,
        content_type: Optional[str] = None,
    ) -> str:
        blob = self.client.bucket(bucket).blob(blob_name)
        blob.upload_from_string(payload, content_type=content_type)
        return f"gs://{bucket}/{blob_name}"

    def blob_exists(self, *, bucket: str, blob_name: str) -> bool:
        return self.client.bucket(bucket).blob(blob_name).exists()

    def delete_blob(self, *, bucket: str, blob_name: str) -> None:
        self.client.bucket(bucket).blob(blob_name).delete(if_generation_match=None)

    def delete_prefix(self, *, bucket: str, prefix: str) -> int:
        deleted = 0
        blobs: Iterable[storage.Blob] = self.client.list_blobs(bucket, prefix=prefix)
        for blob in blobs:
            blob.delete(if_generation_match=None)
            deleted += 1
        return deleted

    def list_prefix(self, *, bucket: str, prefix: str) -> List[str]:
        blobs = self.client.list_blobs(bucket, prefix=prefix)
        return [f"gs://{bucket}/{blob.name}" for blob in blobs]
