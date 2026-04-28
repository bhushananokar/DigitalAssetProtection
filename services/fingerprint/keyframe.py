from __future__ import annotations

import os
import tempfile
from typing import List

import cv2  # type: ignore
import numpy as np


def extract_keyframes(video_bytes: bytes, max_frames: int = 10) -> List[bytes]:
    """
    Extract up to `max_frames` keyframes sampled uniformly across the video.

    Returns a list of JPEG-encoded bytes.
    """

    if max_frames <= 0:
        return []

    # On Windows, NamedTemporaryFile keeps an open handle that can prevent
    # OpenCV from opening the file. Write to a closed temp path instead.
    with tempfile.TemporaryDirectory() as td:
        cap = None
        for ext in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
            path = os.path.join(td, f"video{ext}")
            with open(path, "wb") as f:
                f.write(video_bytes)
            candidate = cv2.VideoCapture(path)
            if candidate.isOpened():
                cap = candidate
                break
            candidate.release()

        if cap is None:
            raise RuntimeError("OpenCV failed to open video bytes")

        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if frame_count <= 0:
                # Fallback: attempt sequential read to count, then resample.
                frames = []
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    frames.append(frame)
                if not frames:
                    return []
                frame_count = len(frames)
                indices = np.linspace(0, frame_count - 1, num=min(max_frames, frame_count), dtype=int)
                out: List[bytes] = []
                for idx in indices:
                    jpg = _encode_jpeg(frames[int(idx)])
                    out.append(jpg)
                return out

            sample_n = min(max_frames, frame_count)
            indices = np.linspace(0, frame_count - 1, num=sample_n, dtype=int)
            indices = np.unique(indices)

            out: List[bytes] = []
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                out.append(_encode_jpeg(frame))
            return out
        finally:
            cap.release()


def _encode_jpeg(frame_bgr) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError("Failed to JPEG-encode keyframe")
    return bytes(buf.tobytes())

