from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


AssetType = Literal["image", "video"]


class ErrorEnvelope(BaseModel):
    error: bool = True
    code: str
    message: str
    status: int


class FingerprintGenerateRequest(BaseModel):
    asset_id: str
    storage_uri: str
    asset_type: AssetType
    org_id: Optional[str] = None


class FingerprintGenerateResponse(BaseModel):
    fingerprint_id: str
    asset_id: str
    model_version: str
    generated_at: datetime
    status: Literal["ready", "failed"]


class MatchingQueryRequest(BaseModel):
    embedding: List[float]
    top_k: int = 5
    threshold: float = 0.70


class MatchItem(BaseModel):
    asset_id: str
    fingerprint_id: str
    similarity_score: float
    asset_type: Optional[str] = None
    asset_name: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


class MatchingQueryResponse(BaseModel):
    matches: List[MatchItem]


class IndexUpsertRequest(BaseModel):
    fingerprint_id: str
    asset_id: str
    embedding: List[float]


class IndexUpsertResponse(BaseModel):
    success: bool


class ManualMatchResponse(BaseModel):
    matched: bool
    matches: List[MatchItem]


class PubSubPushEnvelope(BaseModel):
    message: dict
    subscription: Optional[str] = None

    @property
    def data_b64(self) -> str:
        return self.message.get("data", "")
