from __future__ import annotations

import ast
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any, Dict, Optional
from uuid import uuid4

from google.cloud import pubsub_v1

from services.violations.bigquery import ViolationsBigQuery
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("dap.violations.subscriber")


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


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _getenv(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


_load_setup_env_if_present()


def score_severity(similarity: float) -> Optional[str]:
    if similarity >= 0.95:
        return "critical"
    if similarity >= 0.85:
        return "high"
    if similarity >= 0.70:
        return "medium"
    if similarity >= 0.60:
        return "low"
    return None


def _parse_message_bytes(raw: bytes) -> Dict[str, Any]:
    text = raw.decode("utf-8").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _extract_match_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    source_metadata = payload.get("source_metadata") or {}
    asset_id = (
        payload.get("matched_asset_id")
        or payload.get("asset_id")
        or payload.get("matched_fingerprint_id")
        or source_metadata.get("asset_id")
    )
    return {
        "source_url": payload.get("source_url") or source_metadata.get("source_url", ""),
        "matched_asset_id": asset_id or "",
        "similarity_score": float(payload.get("similarity_score") or 0.0),
        "platform": payload.get("platform") or source_metadata.get("platform") or "unknown",
        "discovered_at": payload.get("discovered_at"),
    }


@dataclass
class ViolationSubscriber:
    project_id: str
    dataset: str
    violations_table: str
    assets_table: str
    match_subscription: str
    high_severity_topic: str

    def __post_init__(self) -> None:
        self.bq = ViolationsBigQuery(
            project_id=self.project_id,
            dataset=self.dataset,
            violations_table=self.violations_table,
            assets_table=self.assets_table,
        )
        self.publisher = pubsub_v1.PublisherClient()
        self.subscriber = pubsub_v1.SubscriberClient()
        self.topic_path = self.publisher.topic_path(self.project_id, self.high_severity_topic)
        self.subscription_path = self.subscriber.subscription_path(self.project_id, self.match_subscription)
        logger.info(
            "subscriber_initialized project_id=%s subscription=%s high_topic=%s",
            self.project_id,
            self.subscription_path,
            self.topic_path,
        )

    def process_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        msg = _extract_match_payload(payload)
        similarity = float(msg["similarity_score"])
        severity = score_severity(similarity)
        if severity is None:
            logger.info("message_discarded similarity=%s reason=below_threshold", similarity)
            return None

        discovered_at = msg["discovered_at"] or datetime.now(timezone.utc).isoformat()
        created_at = datetime.now(timezone.utc).isoformat()
        violation_id = str(uuid4())
        asset_id = str(msg["matched_asset_id"])
        org_id = payload.get("org_id") or self.bq.get_asset_org_id(asset_id) if asset_id else None
        row = {
            "violation_id": violation_id,
            "org_id": org_id,
            "asset_id": asset_id,
            "matched_asset_id": asset_id,
            "source_url": msg["source_url"],
            "platform": msg["platform"],
            "similarity_score": similarity,
            "severity": severity,
            "status": "open",
            "anomaly_flagged": False,
            "evidence_uri": "",
            "discovered_at": discovered_at,
            "created_at": created_at,
            "updated_at": created_at,
        }
        self.bq.insert_violation(row)
        logger.info(
            "violation_inserted violation_id=%s asset_id=%s severity=%s similarity=%s",
            violation_id,
            asset_id,
            severity,
            similarity,
        )

        if severity in ("high", "critical"):
            outgoing = {
                "violation_id": violation_id,
                "asset_id": asset_id,
                "severity": severity,
                "similarity_score": similarity,
                "source_url": msg["source_url"],
                "platform": msg["platform"],
                "discovered_at": discovered_at,
            }
            self.publisher.publish(self.topic_path, data=json.dumps(outgoing).encode("utf-8"))
            logger.info("high_severity_republished violation_id=%s severity=%s", violation_id, severity)
        return row

    def process_message(self, pubsub_message: pubsub_v1.subscriber.message.Message) -> None:
        payload = _parse_message_bytes(pubsub_message.data)
        try:
            self.process_payload(payload)
            pubsub_message.ack()
            logger.info("message_acknowledged message_id=%s", pubsub_message.message_id)
        except Exception as exc:
            logger.exception("message_processing_failed message_id=%s error=%s", pubsub_message.message_id, exc)
            pubsub_message.nack()

    def run_forever(self, stop_event: Optional[Event] = None) -> None:
        callback = self.process_message
        future = self.subscriber.subscribe(self.subscription_path, callback=callback)
        logger.info("subscriber_listening subscription=%s", self.subscription_path)
        try:
            while True:
                if stop_event and stop_event.is_set():
                    break
                time.sleep(1)
        finally:
            future.cancel()
            self.subscriber.close()


def create_default_subscriber() -> ViolationSubscriber:
    project_id = _require("GCP_PROJECT_ID")
    dataset = _getenv("BQ_ASSETS_DATASET", _getenv("BQ_DATASET", "digital_asset_protection"))
    violations_table = _getenv("BQ_VIOLATIONS_TABLE", "violations")
    assets_table = _getenv("BQ_ASSETS_TABLE", "assets")
    match_subscription = _getenv("PUBSUB_MATCH_SUB", "violations-match-sub")
    high_severity_topic = _getenv("PUBSUB_HIGH_SEVERITY_TOPIC", "high-severity-violation")
    return ViolationSubscriber(
        project_id=project_id,
        dataset=dataset,
        violations_table=violations_table,
        assets_table=assets_table,
        match_subscription=match_subscription,
        high_severity_topic=high_severity_topic,
    )


def main() -> None:
    create_default_subscriber().run_forever()


if __name__ == "__main__":
    main()
