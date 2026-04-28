from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import cv2
from google.cloud import videointelligence


@dataclass
class VideoKeyframeExtractor:
    project_id: str
    client: Optional[videointelligence.VideoIntelligenceServiceClient] = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = videointelligence.VideoIntelligenceServiceClient()

    def _shot_timestamps(self, video_bytes: bytes) -> List[float]:
        try:
            features = [videointelligence.Feature.SHOT_CHANGE_DETECTION]
            operation = self.client.annotate_video(
                request={"features": features, "input_content": video_bytes}
            )
            result = operation.result(timeout=180)
            if not result.annotation_results:
                return []

            annotations = result.annotation_results[0]
            timestamps: List[float] = []
            for shot in annotations.shot_annotations:
                seconds = shot.start_time_offset.seconds + shot.start_time_offset.nanos / 1e9
                timestamps.append(max(seconds, 0.0))
            return timestamps
        except Exception:
            # Allow ingest to proceed even if Video Intelligence is unavailable.
            return []

    def _capture_jpegs(self, video_bytes: bytes, timestamps: List[float], max_frames: int) -> List[bytes]:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = Path(tmp.name)

        capture = cv2.VideoCapture(str(tmp_path))
        if not capture.isOpened():
            capture.release()
            tmp_path.unlink(missing_ok=True)
            return []

        fps = capture.get(cv2.CAP_PROP_FPS)
        fps = fps if fps > 0 else 25.0

        frame_bytes: List[bytes] = []
        for timestamp in timestamps[:max_frames]:
            frame_index = int(timestamp * fps)
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            frame_bytes.append(encoded.tobytes())

        # Fallback for short videos where shot detection returns little/no offsets.
        if not frame_bytes:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = capture.read()
            if ok and frame is not None:
                ok, encoded = cv2.imencode(".jpg", frame)
                if ok:
                    frame_bytes.append(encoded.tobytes())

        capture.release()
        tmp_path.unlink(missing_ok=True)
        return frame_bytes

    def extract_keyframes_to_jpegs(self, video_bytes: bytes, *, max_frames: int = 12) -> List[bytes]:
        timestamps = self._shot_timestamps(video_bytes)
        return self._capture_jpegs(video_bytes, timestamps, max_frames=max_frames)
