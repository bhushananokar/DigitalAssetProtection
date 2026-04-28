from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from google.cloud import pubsub_v1


@dataclass
class PubSubHelper:
    project_id: str
    publisher: Optional[pubsub_v1.PublisherClient] = None

    def __post_init__(self) -> None:
        if self.publisher is None:
            self.publisher = pubsub_v1.PublisherClient()

    def publish_json(self, topic_name: str, payload: Dict[str, Any]) -> str:
        topic_path = self.publisher.topic_path(self.project_id, topic_name)
        future = self.publisher.publish(
            topic_path,
            data=json.dumps(payload, default=str).encode("utf-8"),
        )
        return future.result(timeout=30)
