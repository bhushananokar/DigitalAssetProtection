# Fingerprint + Matching ML Core Implementation Plan
 
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
 
**Goal:** Implement shared config/clients, Vertex multimodal embedding + keyframe extraction utilities, and a robustness gate test to validate embedding invariance before any API endpoints are built.
 
**Architecture:** A `shared/config.py` module loads environment variables from `setup.env` via process env (Cloud Run) and provides validated configuration. Thin clients wrap GCS and BigQuery. Fingerprint utilities use Vertex AI multimodal embeddings for images and OpenCV-based keyframe extraction for videos. A robustness test script exercises transformations and checks cosine similarity thresholds.
 
**Tech Stack:** Python 3.11, FastAPI (later), google-cloud-aiplatform, google-cloud-storage, google-cloud-bigquery, opencv-python, Pillow, pytest.
 
---
 
### Task 1: Create repository skeleton
 
**Files:**
- Create: `services/fingerprint/*`, `services/matching/*`, `shared/*`, `tests/*`
 
- [ ] Create the directory structure and placeholder `__init__.py` where needed.
 
### Task 2: Shared config + env loading
 
**Files:**
- Create: `shared/config.py`
 
- [ ] **Step 1: Write failing tests for env validation**
 
```python
import os
import importlib
import pytest
 
def test_config_requires_project_id(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    with pytest.raises(Exception):
        importlib.reload(__import__("shared.config", fromlist=["*"]))
```
 
- [ ] **Step 2: Implement `shared/config.py`**
 
Provide:
 - `Settings` dataclass/pydantic with required fields and defaults
 - `get_settings()` returning a singleton instance
 - call `aiplatform.init(project=..., location=...)` once at import time
 
- [ ] **Step 3: Run tests**
 
Run: `pytest -q`
Expected: PASS
 
### Task 3: Shared GCS + BigQuery clients
 
**Files:**
- Create: `shared/gcs_client.py`
- Create: `shared/bq_client.py`
 
- [ ] Implement:
 - `GcsClient.download_bytes(gs://bucket/path) -> bytes`
 - `GcsClient.upload_bytes(gs://bucket/path, data, content_type)`
 - `BqClient.insert_rows_json(table_fqn, rows)`
 - `BqClient.query(sql, params)`
 
### Task 4: Embedder + keyframes
 
**Files:**
- Create: `services/fingerprint/embedder.py`
- Create: `services/fingerprint/keyframe.py`
 
- [ ] Implement `MultimodalEmbedder` (image->1408 floats) using `multimodalembedding@001`.
- [ ] Implement `extract_keyframes(video_bytes, max_frames=10)` sampling uniformly and returning JPEG bytes.
 
### Task 5: Robustness gate test script
 
**Files:**
- Create/Modify: `tests/robustness_test.py`
- Use: `tests/fixtures/*`
 
- [ ] Implement transformations (crop 80%, recompress, overlay text, flip, frame screenshot).
- [ ] Compute cosine similarity and assert ≥ 0.80 (except allow horizontal flip to fail but must be reported).
- [ ] Print results table exactly in the requested format.
 
### Task 6: Only if robustness passes: proceed to API services
 
Stop here if robustness fails; report which transforms failed and their scores.
