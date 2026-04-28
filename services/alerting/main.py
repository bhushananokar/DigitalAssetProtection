from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from google.cloud import bigquery, storage

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("dap.alerting")


def _load_setup_env_if_present() -> None:
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent
    env_path = repo_root / "setup.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value

def _getenv(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


_load_setup_env_if_present()


@dataclass
class AlertingContext:
    project_id: str
    dataset: str
    violations_table: str
    assets_table: str
    evidence_bucket: str
    webhook_url: Optional[str]
    bq: bigquery.Client
    gcs: storage.Client

    @classmethod
    def from_env(cls) -> "AlertingContext":
        project_id = _require("GCP_PROJECT_ID")
        dataset = _getenv("BQ_ASSETS_DATASET", _getenv("BQ_DATASET", "digital_asset_protection"))
        return cls(
            project_id=project_id,
            dataset=dataset,
            violations_table=_getenv("BQ_VIOLATIONS_TABLE", "violations"),
            assets_table=_getenv("BQ_ASSETS_TABLE", "assets"),
            evidence_bucket=_getenv("GCS_EVIDENCE_BUCKET", _require("GCS_RAW_BUCKET")),
            webhook_url=os.getenv("ALERT_WEBHOOK_URL"),
            bq=bigquery.Client(project=project_id),
            gcs=storage.Client(project=project_id),
        )

    @property
    def violations_fqn(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.violations_table}"

    @property
    def assets_fqn(self) -> str:
        return f"{self.project_id}.{self.dataset}.{self.assets_table}"

    def violation_columns(self) -> set[str]:
        return {f.name for f in self.bq.get_table(self.violations_fqn).schema}

    def asset_columns(self) -> set[str]:
        return {f.name for f in self.bq.get_table(self.assets_fqn).schema}


def _parse_pubsub_message(event: Dict[str, Any]) -> Dict[str, Any]:
    if "data" not in event:
        return {}
    raw_data = base64.b64decode(event["data"]).decode("utf-8")
    try:
        parsed = json.loads(raw_data)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return {}
    return {}


def _fetch_violation(ctx: AlertingContext, violation_id: str) -> Dict[str, Any]:
    sql = f"""
    SELECT *
    FROM `{ctx.violations_fqn}`
    WHERE violation_id = @violation_id
    LIMIT 1
    """
    rows = ctx.bq.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("violation_id", "STRING", violation_id)]
        ),
    ).result()
    items = [dict(row.items()) for row in rows]
    if not items:
        raise RuntimeError(f"Violation not found: {violation_id}")
    return items[0]


def _fetch_asset_name(ctx: AlertingContext, matched_asset_id: str) -> str:
    columns = ctx.asset_columns()
    preferred = "asset_name" if "asset_name" in columns else "event_name" if "event_name" in columns else None
    if preferred is None:
        return ""
    sql = f"""
    SELECT {preferred} AS asset_name
    FROM `{ctx.assets_fqn}`
    WHERE asset_id = @asset_id
    LIMIT 1
    """
    rows = ctx.bq.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("asset_id", "STRING", matched_asset_id)]
        ),
    ).result()
    items = [dict(row.items()) for row in rows]
    if not items:
        return ""
    return str(items[0].get("asset_name") or "")


def _extract_og_image_url(source_url: str) -> Optional[str]:
    try:
        response = requests.get(source_url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        tag = soup.find("meta", attrs={"property": "og:image"}) or soup.find(
            "meta", attrs={"name": "og:image"}
        )
        if not tag:
            return None
        content = tag.get("content")
        if not content:
            return None
        return urljoin(source_url, content)
    except Exception:
        return None


def _store_screenshot_if_available(
    ctx: AlertingContext, violation_id: str, source_url: str
) -> Optional[str]:
    image_url = _extract_og_image_url(source_url)
    if not image_url:
        return None

    try:
        response = requests.get(image_url, timeout=20)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg")
        extension = "jpg"
        if "png" in content_type:
            extension = "png"
        elif "webp" in content_type:
            extension = "webp"
        elif "gif" in content_type:
            extension = "gif"
        blob_name = f"evidence/{violation_id}/screenshot.{extension}"
        bucket = ctx.gcs.bucket(ctx.evidence_bucket)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(response.content, content_type=content_type)
        return f"gs://{ctx.evidence_bucket}/{blob_name}"
    except Exception:
        return None


def _build_evidence_bundle(
    *,
    violation: Dict[str, Any],
    asset_name: str,
    screenshot_url: Optional[str],
) -> Dict[str, Any]:
    matched_asset_id = str(violation.get("matched_asset_id") or violation.get("asset_id") or "")
    source_url = str(violation.get("source_url") or "")
    discovered_at = str(violation.get("discovered_at") or datetime.now(timezone.utc).isoformat())
    hash_input = f"{source_url}{matched_asset_id}{discovered_at}"
    content_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

    return {
        "source_url": source_url,
        "similarity_score": float(violation.get("similarity_score") or 0.0),
        "matched_asset_id": matched_asset_id,
        "asset_name": asset_name,
        "severity": str(violation.get("severity") or ""),
        "platform": str(violation.get("platform") or ""),
        "discovered_at": discovered_at,
        "content_hash": content_hash,
        "screenshot_url": screenshot_url or "",
    }


def _store_bundle(ctx: AlertingContext, violation_id: str, bundle: Dict[str, Any]) -> str:
    blob_name = f"evidence/{violation_id}/bundle.json"
    payload = json.dumps(bundle, indent=2, default=str).encode("utf-8")
    bucket = ctx.gcs.bucket(ctx.evidence_bucket)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(payload, content_type="application/json")
    return f"gs://{ctx.evidence_bucket}/{blob_name}"


def _update_evidence_uri(ctx: AlertingContext, violation_id: str, evidence_uri: str) -> None:
    if "evidence_uri" not in ctx.violation_columns():
        return
    sql = f"""
    UPDATE `{ctx.violations_fqn}`
    SET evidence_uri = @evidence_uri
    WHERE violation_id = @violation_id
    """
    ctx.bq.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("evidence_uri", "STRING", evidence_uri),
                bigquery.ScalarQueryParameter("violation_id", "STRING", violation_id),
            ]
        ),
    ).result()


def _send_notification(
    *,
    webhook_url: Optional[str],
    violation_id: str,
    asset_name: str,
    severity: str,
    source_url: str,
    similarity_score: float,
    platform: str,
    evidence_uri: Optional[str],
) -> None:
    payload = {
        "violation_id": violation_id,
        "asset_name": asset_name,
        "severity": severity,
        "source_url": source_url,
        "similarity_score": similarity_score,
        "platform": platform,
        "evidence_uri": evidence_uri or "",
    }
    if webhook_url:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("alert_webhook_sent violation_id=%s status_code=%d", violation_id, response.status_code)
        return
    logger.info("alert_logged_webhook_disabled payload=%s", json.dumps(payload))


def handle_high_severity_violation(event: Dict[str, Any], context: Any = None) -> None:
    parsed = _parse_pubsub_message(event)
    violation_id = str(parsed.get("violation_id") or "")
    if not violation_id:
        logger.warning("alert_event_ignored reason=missing_violation_id payload=%s", parsed)
        return

    logger.info("alert_event_received violation_id=%s", violation_id)
    ctx = AlertingContext.from_env()
    violation = _fetch_violation(ctx, violation_id)
    matched_asset_id = str(violation.get("matched_asset_id") or violation.get("asset_id") or "")
    asset_name = _fetch_asset_name(ctx, matched_asset_id) if matched_asset_id else ""

    evidence_uri: Optional[str] = None
    try:
        screenshot_url = _store_screenshot_if_available(ctx, violation_id, str(violation.get("source_url") or ""))
        bundle = _build_evidence_bundle(violation=violation, asset_name=asset_name, screenshot_url=screenshot_url)
        evidence_uri = _store_bundle(ctx, violation_id, bundle)
        _update_evidence_uri(ctx, violation_id, evidence_uri)
        logger.info("evidence_bundle_stored violation_id=%s evidence_uri=%s", violation_id, evidence_uri)
    except Exception as exc:
        logger.exception("evidence_bundle_failed violation_id=%s error=%s", violation_id, exc)

    try:
        _send_notification(
            webhook_url=ctx.webhook_url,
            violation_id=violation_id,
            asset_name=asset_name,
            severity=str(violation.get("severity") or ""),
            source_url=str(violation.get("source_url") or ""),
            similarity_score=float(violation.get("similarity_score") or 0.0),
            platform=str(violation.get("platform") or ""),
            evidence_uri=evidence_uri,
        )
    except Exception as exc:
        logger.exception("alert_notification_failed violation_id=%s error=%s", violation_id, exc)
    else:
        logger.info("alert_pipeline_completed violation_id=%s severity=%s", violation_id, violation.get("severity"))
