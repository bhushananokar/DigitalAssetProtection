from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from services.shared.bq_client import BqClient
from services.shared.config import SETTINGS
from services.shared.schemas import FingerprintGenerateRequest, FingerprintGenerateResponse
from services.fingerprint.embedder import MultimodalEmbedder
from services.fingerprint.keyframe import extract_keyframes
from services.fingerprint.storage import download_asset_bytes
from services.matching.index_client import MatchingIndexClient


def _mean_pool(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        raise ValueError("Cannot mean-pool empty vectors")
    dim = len(vectors[0])
    pooled = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            pooled[i] += x
    n = float(len(vectors))
    return [x / n for x in pooled]


def _fingerprint_rows(
    *,
    fingerprint_id: str,
    asset_id: str,
    asset_type: str,
    storage_uri: str,
    org_id: Optional[str],
    model_version: str,
    generated_at: datetime,
    vectors: List[Tuple[Optional[int], bool, List[float]]],
    embedding_as_scalar: bool,
) -> List[Dict]:
    rows = []
    for keyframe_index, is_pooled, embedding in vectors:
        embedding_value = float(embedding[0]) if embedding_as_scalar else embedding
        rows.append(
            {
                "fingerprint_id": fingerprint_id,
                "asset_id": asset_id,
                "org_id": org_id or "unknown",
                "asset_type": asset_type,
                "storage_uri": storage_uri,
                "keyframe_index": keyframe_index,
                "is_pooled": is_pooled,
                "embedding": embedding_value,
                "model_version": model_version,
                "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
                "status": "ready",
            }
        )
    return rows


def _set_asset_status(asset_id: str, status: str) -> None:
    bq = BqClient.default()
    schema = bq.get_table_schema(
        f"{SETTINGS.gcp_project_id}.{SETTINGS.bq_assets_dataset}.{SETTINGS.bq_assets_table}"
    )
    status_col = "fingerprint_status"
    if status_col not in schema:
        # Backend-owned schema may not yet include fingerprint_status in some environments.
        print(
            "[fingerprint.generate] "
            f"asset status update skipped: column '{status_col}' not found on "
            f"{SETTINGS.gcp_project_id}.{SETTINGS.bq_assets_dataset}.{SETTINGS.bq_assets_table}"
        )
        return

    sql = f"""
    UPDATE `{SETTINGS.gcp_project_id}.{SETTINGS.bq_assets_dataset}.{SETTINGS.bq_assets_table}`
    SET {status_col} = @status
    WHERE asset_id = @asset_id
    """
    from google.cloud import bigquery

    bq.query(
        sql,
        params=[
            bigquery.ScalarQueryParameter("status", "STRING", status),
            bigquery.ScalarQueryParameter("asset_id", "STRING", asset_id),
        ],
    )


def generate_fingerprint(req: FingerprintGenerateRequest) -> FingerprintGenerateResponse:
    bq = BqClient.default()
    embedder = MultimodalEmbedder.create()
    index_client = MatchingIndexClient.create()

    generated_at = datetime.now(tz=timezone.utc)
    fingerprint_id = str(uuid.uuid4())

    t0 = time.perf_counter()
    asset_bytes = download_asset_bytes(req.storage_uri)
    download_ms = int((time.perf_counter() - t0) * 1000)

    embed_t0 = time.perf_counter()
    vectors_for_rows: List[Tuple[Optional[int], bool, List[float]]] = []
    vectors_for_index: List[List[float]] = []
    if req.asset_type == "image":
        vec = embedder.embed_image(asset_bytes)
        vectors_for_rows.append((None, False, vec))
        vectors_for_index.append(vec)
    elif req.asset_type == "video":
        keyframes = extract_keyframes(asset_bytes, max_frames=10)
        frame_vectors = [embedder.embed_video_frame(f) for f in keyframes]
        for i, vec in enumerate(frame_vectors):
            vectors_for_rows.append((i, False, vec))
            vectors_for_index.append(vec)
        pooled = _mean_pool(frame_vectors)
        vectors_for_rows.append((None, True, pooled))
        vectors_for_index.append(pooled)
    else:
        raise ValueError(f"Unsupported asset_type: {req.asset_type}")
    embed_ms = int((time.perf_counter() - embed_t0) * 1000)

    bq_t0 = time.perf_counter()
    schema = bq.get_table_schema(SETTINGS.bq_fingerprints_table_fqn)
    emb_field = schema.get("embedding")
    embedding_as_scalar = bool(emb_field and emb_field.mode != "REPEATED")
    rows = _fingerprint_rows(
        fingerprint_id=fingerprint_id,
        asset_id=req.asset_id,
        asset_type=req.asset_type,
        storage_uri=req.storage_uri,
        org_id=req.org_id,
        model_version=embedder.model_version,
        generated_at=generated_at,
        vectors=vectors_for_rows,
        embedding_as_scalar=embedding_as_scalar,
    )
    bq.insert_rows_json(SETTINGS.bq_fingerprints_table_fqn, rows)
    bq_ms = int((time.perf_counter() - bq_t0) * 1000)

    upsert_t0 = time.perf_counter()
    for i, vec in enumerate(vectors_for_index):
        # pooled vector keeps original fingerprint_id for easier lookup.
        datapoint_id = fingerprint_id if i == len(vectors_for_index) - 1 else f"{fingerprint_id}#kf{i}"
        index_client.upsert(datapoint_id, vec)
    upsert_ms = int((time.perf_counter() - upsert_t0) * 1000)

    _set_asset_status(req.asset_id, "ready")

    print(
        "[fingerprint.generate] "
        f"asset_id={req.asset_id} type={req.asset_type} fingerprint_id={fingerprint_id} "
        f"download_ms={download_ms} embed_ms={embed_ms} bq_insert_ms={bq_ms} index_upsert_ms={upsert_ms}"
    )

    return FingerprintGenerateResponse(
        fingerprint_id=fingerprint_id,
        asset_id=req.asset_id,
        model_version=embedder.model_version,
        generated_at=generated_at,
        status="ready",
    )

