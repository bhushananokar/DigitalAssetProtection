from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from google.cloud import aiplatform


def _load_setup_env_if_present() -> None:
    """
    Local-dev convenience:
    load missing env vars from repo-level `setup.env`.
    Cloud Run runtime env vars still take precedence.
    """

    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent
    env_path = repo_root / "setup.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and k not in os.environ:
            os.environ[k] = v


def _getenv(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.getenv(name)
    if val is None or val == "":
        return default
    return val


def _require(name: str) -> str:
    val = _getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def _as_int(name: str, default: Optional[int] = None, *, required: bool = False) -> int:
    raw = _getenv(name)
    if raw is None:
        if required or default is None:
            raise RuntimeError(f"Missing required env var: {name}")
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise RuntimeError(f"Env var {name} must be int, got: {raw!r}") from e


def _as_float(name: str, default: Optional[float] = None, *, required: bool = False) -> float:
    raw = _getenv(name)
    if raw is None:
        if required or default is None:
            raise RuntimeError(f"Missing required env var: {name}")
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise RuntimeError(f"Env var {name} must be float, got: {raw!r}") from e


@dataclass(frozen=True)
class Settings:
    # Core project
    gcp_project_id: str
    gcp_region: str

    # Storage
    gcs_raw_bucket: str
    gcs_index_bucket: str

    # BigQuery
    bq_dataset: str
    bq_fingerprints_table: str
    bq_assets_dataset: str
    bq_assets_table: str

    # Pub/Sub
    pubsub_asset_topic: str
    pubsub_asset_sub: str
    pubsub_match_topic: str

    # Vertex AI embedding + Matching Engine
    vertex_embedding_model: str
    embedding_dim: int
    me_index_id: str
    me_index_endpoint_id: str
    me_deployed_index_id: str
    max_source_download_mb: int = 50

    # Operational
    max_concurrent_embeddings: int = 5

    @property
    def bq_fingerprints_table_fqn(self) -> str:
        return f"{self.gcp_project_id}.{self.bq_dataset}.{self.bq_fingerprints_table}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Required by contract: do not hardcode IDs/buckets/index IDs.
    settings = Settings(
        gcp_project_id=_require("GCP_PROJECT_ID"),
        gcp_region=_require("GCP_REGION"),
        gcs_raw_bucket=_require("GCS_RAW_BUCKET"),
        gcs_index_bucket=_require("GCS_INDEX_BUCKET"),
        bq_dataset=_require("BQ_DATASET"),
        bq_fingerprints_table=_require("BQ_FINGERPRINTS_TABLE"),
        bq_assets_dataset=_getenv("BQ_ASSETS_DATASET", _require("BQ_DATASET")) or _require("BQ_DATASET"),
        bq_assets_table=_getenv("BQ_ASSETS_TABLE", "assets") or "assets",
        pubsub_asset_topic=_require("PUBSUB_ASSET_TOPIC"),
        pubsub_asset_sub=_require("PUBSUB_ASSET_SUB"),
        pubsub_match_topic=_require("PUBSUB_MATCH_TOPIC"),
        vertex_embedding_model=_getenv("VERTEX_EMBEDDING_MODEL", "multimodalembedding@001") or "multimodalembedding@001",
        embedding_dim=_as_int("EMBEDDING_DIM", 1408),
        me_index_id=_require("ME_INDEX_ID"),
        me_index_endpoint_id=_require("ME_INDEX_ENDPOINT_ID"),
        me_deployed_index_id=_require("ME_DEPLOYED_INDEX_ID"),
        max_concurrent_embeddings=_as_int("MAX_CONCURRENT_EMBEDDINGS", 5),
        max_source_download_mb=_as_int("MAX_SOURCE_DOWNLOAD_MB", 50),
    )

    # Ensure Google SDKs can resolve project in local/dev flows too.
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.gcp_project_id)
    os.environ.setdefault("GCLOUD_PROJECT", settings.gcp_project_id)

    # Must happen exactly once at module load / init time.
    aiplatform.init(project=settings.gcp_project_id, location=settings.gcp_region)
    # Some Vertex model helpers live under the `vertexai` package (installed via google-cloud-aiplatform).
    # Initialize it too when available; safe no-op if unused.
    try:
        import vertexai  # type: ignore

        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_region)
    except Exception:
        pass
    return settings


# Ensure env validation happens early and aiplatform is initialized once.
_load_setup_env_if_present()
SETTINGS = get_settings()
