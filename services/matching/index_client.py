from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from google.cloud import aiplatform
from google.cloud.aiplatform_v1.types import index as index_types

from services.shared.config import SETTINGS


def _index_resource_name() -> str:
    return f"projects/{SETTINGS.gcp_project_id}/locations/{SETTINGS.gcp_region}/indexes/{SETTINGS.me_index_id}"


def _index_endpoint_resource_name() -> str:
    return (
        f"projects/{SETTINGS.gcp_project_id}/locations/{SETTINGS.gcp_region}"
        f"/indexEndpoints/{SETTINGS.me_index_endpoint_id}"
    )


@dataclass
class MatchingIndexClient:
    _index: aiplatform.MatchingEngineIndex
    _endpoint: aiplatform.MatchingEngineIndexEndpoint

    @classmethod
    def create(cls) -> "MatchingIndexClient":
        index = aiplatform.MatchingEngineIndex(index_name=_index_resource_name())
        endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=_index_endpoint_resource_name())
        return cls(_index=index, _endpoint=endpoint)

    def upsert(self, fingerprint_id: str, embedding: List[float]) -> None:
        datapoint = index_types.IndexDatapoint(datapoint_id=fingerprint_id, feature_vector=embedding)
        self._index.upsert_datapoints(datapoints=[datapoint])

    def query(self, embedding: List[float], top_k: int) -> List[Dict[str, float | str]]:
        neighbors_per_query = self._endpoint.find_neighbors(
            deployed_index_id=SETTINGS.me_deployed_index_id,
            queries=[embedding],
            num_neighbors=top_k,
        )
        if not neighbors_per_query:
            return []
        out: List[Dict[str, float | str]] = []
        for n in neighbors_per_query[0]:
            distance = float(n.distance if n.distance is not None else 1.0)
            out.append(
                {
                    "fingerprint_id": str(n.id),
                    "distance": distance,
                    "similarity": 1.0 - distance,
                }
            )
        return out

