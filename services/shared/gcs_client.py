from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from google.cloud import storage

from services.shared.config import SETTINGS


def parse_gs_uri(gs_uri: str) -> Tuple[str, str]:
    if not gs_uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got: {gs_uri!r}")
    without = gs_uri[len("gs://") :]
    if "/" not in without:
        raise ValueError(f"Expected gs://bucket/path URI, got: {gs_uri!r}")
    bucket, blob = without.split("/", 1)
    if not bucket or not blob:
        raise ValueError(f"Expected gs://bucket/path URI, got: {gs_uri!r}")
    return bucket, blob


@dataclass
class GcsClient:
    client: storage.Client

    @classmethod
    def default(cls) -> "GcsClient":
        return cls(client=storage.Client(project=SETTINGS.gcp_project_id))

    def download_bytes(self, gs_uri: str) -> bytes:
        bucket_name, blob_name = parse_gs_uri(gs_uri)
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.download_as_bytes()

    def upload_bytes(self, gs_uri: str, data: bytes, *, content_type: Optional[str] = None) -> None:
        bucket_name, blob_name = parse_gs_uri(gs_uri)
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(data, content_type=content_type)
