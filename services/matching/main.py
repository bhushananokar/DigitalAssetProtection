from __future__ import annotations

import io
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from fastapi import FastAPI, File, Form, UploadFile
from google.cloud import bigquery, pubsub_v1
from PIL import Image

from services.fingerprint.embedder import MultimodalEmbedder
from services.fingerprint.keyframe import extract_keyframes
from services.matching.index_client import MatchingIndexClient
from services.shared.bq_client import BqClient
from services.shared.config import SETTINGS
from services.shared.schemas import (
    IndexUpsertRequest,
    IndexUpsertResponse,
    ManualMatchResponse,
    MatchItem,
    MatchingQueryRequest,
    MatchingQueryResponse,
)

app = FastAPI(title="Matching Service", version="1.0.0")


def _mean_pool(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        raise ValueError("Cannot mean-pool empty vectors")
    dim = len(vectors[0])
    out = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            out[i] += x
    n = float(len(vectors))
    return [x / n for x in out]


def _lookup_asset_metadata(fingerprint_ids: List[str]) -> Dict[str, Dict[str, str]]:
    if not fingerprint_ids:
        return {}
    bq = BqClient.default()
    sql = f"""
    SELECT fingerprint_id, ANY_VALUE(asset_id) AS asset_id, ANY_VALUE(asset_type) AS asset_type
    FROM `{SETTINGS.bq_fingerprints_table_fqn}`
    WHERE fingerprint_id IN UNNEST(@ids)
    GROUP BY fingerprint_id
    """
    rows = bq.query(
        sql,
        params=[bigquery.ArrayQueryParameter("ids", "STRING", fingerprint_ids)],
    )
    return {r["fingerprint_id"]: {"asset_id": r["asset_id"], "asset_type": r.get("asset_type")} for r in rows}


def _publish_match_event(match: MatchItem, source_metadata: Optional[dict] = None) -> None:
    publisher = pubsub_v1.PublisherClient()
    topic = publisher.topic_path(SETTINGS.gcp_project_id, SETTINGS.pubsub_match_topic)
    payload = {
        "matched_fingerprint_id": match.fingerprint_id,
        "source_metadata": source_metadata or {},
        "similarity_score": match.similarity_score,
        "discovered_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    publisher.publish(topic, data=str(payload).encode("utf-8"))


def _query_matches(req: MatchingQueryRequest) -> MatchingQueryResponse:
    index_client = MatchingIndexClient.create()
    t0 = time.perf_counter()
    neighbors = index_client.query(req.embedding, req.top_k)
    query_ms = int((time.perf_counter() - t0) * 1000)

    filtered = [n for n in neighbors if float(n["similarity"]) >= req.threshold]
    ids = [str(n["fingerprint_id"]).split("#")[0] for n in filtered]
    metadata = _lookup_asset_metadata(ids)

    matches: List[MatchItem] = []
    for n in filtered:
        root_fingerprint_id = str(n["fingerprint_id"]).split("#")[0]
        meta = metadata.get(root_fingerprint_id, {})
        matches.append(
            MatchItem(
                asset_id=meta.get("asset_id", ""),
                fingerprint_id=root_fingerprint_id,
                similarity_score=float(n["similarity"]),
                asset_type=meta.get("asset_type"),
            )
        )
    print(f"[matching.query] top_k={req.top_k} threshold={req.threshold} query_ms={query_ms} matches={len(matches)}")
    return MatchingQueryResponse(matches=matches)


def _download_source_url(source_url: str) -> bytes:
    max_bytes = SETTINGS.max_source_download_mb * 1024 * 1024
    with requests.get(source_url, stream=True, timeout=20) as r:
        r.raise_for_status()
        out = bytearray()
        for chunk in r.iter_content(chunk_size=1024 * 256):
            if not chunk:
                continue
            out.extend(chunk)
            if len(out) > max_bytes:
                raise ValueError(f"source exceeds max size of {SETTINGS.max_source_download_mb}MB")
        return bytes(out)


def _is_image_bytes(data: bytes) -> bool:
    try:
        Image.open(io.BytesIO(data)).verify()
        return True
    except Exception:
        return False


def _embedding_from_raw(data: bytes) -> List[float]:
    embedder = MultimodalEmbedder.create()
    if _is_image_bytes(data):
        return embedder.embed_image(data)
    frames = extract_keyframes(data, max_frames=10)
    vecs = [embedder.embed_video_frame(f) for f in frames]
    return _mean_pool(vecs)


def _confidence(similarity: float) -> str:
    if similarity >= 0.90:
        return "high"
    if similarity >= 0.80:
        return "medium"
    return "low"


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/matching/query")
def matching_query(req: MatchingQueryRequest):
    resp = _query_matches(req)
    if resp.matches:
        for m in resp.matches:
            _publish_match_event(m)
    return resp.model_dump()


@app.post("/fingerprint/match")
async def fingerprint_match(
    source_url: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
):
    if not source_url and not file:
        return {"matched": False, "matches": []}
    if source_url and file:
        return {"matched": False, "matches": []}

    raw = _download_source_url(source_url) if source_url else await file.read()  # type: ignore[arg-type]
    embedding = _embedding_from_raw(raw)
    query_resp = _query_matches(MatchingQueryRequest(embedding=embedding, top_k=5, threshold=0.70))

    manual_matches: List[MatchItem] = []
    for m in query_resp.matches:
        manual_matches.append(
            MatchItem(
                asset_id=m.asset_id,
                asset_name=m.asset_id,  # placeholder until assets join is added in backend table
                fingerprint_id=m.fingerprint_id,
                similarity_score=m.similarity_score,
                asset_type=m.asset_type,
                confidence=_confidence(m.similarity_score),  # type: ignore[arg-type]
            )
        )
    return ManualMatchResponse(matched=len(manual_matches) > 0, matches=manual_matches).model_dump()


@app.post("/matching/index/upsert")
def upsert_index(req: IndexUpsertRequest):
    client = MatchingIndexClient.create()
    client.upsert(req.fingerprint_id, req.embedding)
    return IndexUpsertResponse(success=True).model_dump()

