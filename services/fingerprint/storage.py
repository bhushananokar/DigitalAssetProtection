from __future__ import annotations

from services.shared.gcs_client import GcsClient


def download_asset_bytes(storage_uri: str) -> bytes:
    return GcsClient.default().download_bytes(storage_uri)

