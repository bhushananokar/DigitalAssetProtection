from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, List, Protocol, runtime_checkable

from services.shared.config import SETTINGS


@runtime_checkable
class _EmbeddingModel(Protocol):
    @classmethod
    def from_pretrained(cls, model_name: str) -> Any: ...

    def get_embeddings(self, **kwargs: Any) -> Any: ...


def _load_multimodal_model(model_name: str) -> _EmbeddingModel:
    """
    Load the Vertex multimodal embedding model via the `vertexai` SDK.

    Note: Although `google-cloud-aiplatform` provides `aiplatform.init(...)`,
    the multimodal embedding model class is exposed under `vertexai.vision_models`
    in current SDK versions.
    """

    try:
        from vertexai.vision_models import MultiModalEmbeddingModel  # type: ignore

        return MultiModalEmbeddingModel.from_pretrained(model_name)
    except Exception:
        raise RuntimeError(
            "Failed to load Vertex MultiModalEmbeddingModel. "
            "Make sure `google-cloud-aiplatform` is installed and Application Default Credentials are set "
            "(e.g. run `gcloud auth application-default login` locally, or use a service account on Cloud Run)."
        )


def _to_vertex_image(image_bytes: bytes) -> Any:
    from vertexai.vision_models import Image  # type: ignore

    return Image(image_bytes=image_bytes)


def _extract_image_embedding(resp: Any) -> List[float]:
    # Different SDK versions expose slightly different response shapes.
    if hasattr(resp, "image_embedding"):
        return list(resp.image_embedding)
    if hasattr(resp, "embeddings") and resp.embeddings:
        emb0 = resp.embeddings[0]
        if hasattr(emb0, "image_embedding"):
            return list(emb0.image_embedding)
        if hasattr(emb0, "values"):
            return list(emb0.values)
    if hasattr(resp, "values"):
        return list(resp.values)
    raise RuntimeError(f"Unrecognized embedding response type: {type(resp)!r}")


@dataclass
class MultimodalEmbedder:
    """
    Thin wrapper around Vertex multimodal embedding model.

    Notes:
    - Model returns a 1408-dim embedding for images.
    - For video: caller must extract frames and call embed_image on each.
    """

    _model: _EmbeddingModel

    @classmethod
    def create(cls) -> "MultimodalEmbedder":
        # Ensure aiplatform.init(...) has already happened in shared.config import.
        model = _load_multimodal_model(SETTINGS.vertex_embedding_model)
        return cls(_model=model)

    @property
    def model_version(self) -> str:
        return SETTINGS.vertex_embedding_model

    def embed_image(self, image_bytes: bytes) -> List[float]:
        t0 = time.perf_counter()
        image = _to_vertex_image(image_bytes)
        resp = self._model.get_embeddings(image=image)
        vec = _extract_image_embedding(resp)
        if len(vec) != SETTINGS.embedding_dim:
            raise RuntimeError(f"Unexpected embedding dim {len(vec)} (expected {SETTINGS.embedding_dim})")
        _ = time.perf_counter() - t0
        return vec

    def embed_video_frame(self, frame_bytes: bytes) -> List[float]:
        # Video frames are embedded as images.
        return self.embed_image(frame_bytes)

