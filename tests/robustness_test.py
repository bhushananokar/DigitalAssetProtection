from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2  # type: ignore


FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[1]

# Allow running as `python tests/robustness_test.py` without installing as a package.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def _load_setup_env(path: Path) -> None:
    """
    Convenience for local runs: load missing env vars from `setup.env`.
    In Cloud Run these will already be provided as environment variables.
    """

    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and k not in os.environ:
            os.environ[k] = v


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    av = np.asarray(a, dtype=np.float32)
    bv = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(av) * np.linalg.norm(bv))
    if denom == 0.0:
        return 0.0
    return float(np.dot(av, bv) / denom)


def _mean_pool(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        raise ValueError("cannot mean-pool empty vectors")
    arr = np.asarray(vectors, dtype=np.float32)
    return arr.mean(axis=0).astype(np.float32).tolist()


def _load_fixture_bytes() -> Tuple[bytes, bytes]:
    """
    Returns (image_bytes, video_bytes) from tests/fixtures.
    Fails loudly when fixtures are missing so robustness numbers are meaningful.
    """

    img = _first_existing(FIXTURES_DIR, ["*.jpg", "*.jpeg", "*.png", "*.webp"])
    vid = _first_existing(FIXTURES_DIR, ["*.mp4", "*.mov", "*.mkv", "*.avi"])

    if not img or not vid:
        raise RuntimeError(
            "Missing robustness fixtures. Add at least one image and one video under tests/fixtures "
            "(e.g. tests/fixtures/sample_image.jpg and tests/fixtures/sample_video.mp4)."
        )
    return img.read_bytes(), vid.read_bytes()


def _first_existing(dir_path: Path, globs: List[str]) -> Optional[Path]:
    for g in globs:
        matches = sorted(dir_path.glob(g))
        if matches:
            return matches[0]
    return None


def _generate_synthetic_image_bytes() -> bytes:
    im = Image.new("RGB", (640, 360), (20, 30, 60))
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 600, 320], outline=(255, 255, 255), width=4)
    d.text((70, 150), "SPORTS TEST", fill=(200, 220, 255))
    bio = io.BytesIO()
    im.save(bio, format="JPEG", quality=92)
    return bio.getvalue()


def _generate_synthetic_video_bytes() -> bytes:
    """
    Creates a short video without relying on ffmpeg, so the script can at least
    reach the explicit ffmpeg-based recompress step and fail loudly there if
    ffmpeg is missing.
    """

    import cv2  # type: ignore

    w, h = 640, 360
    fps = 15
    frames = 30

    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "synthetic.avi"
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
        if not writer.isOpened():
            raise RuntimeError("OpenCV failed to create synthetic video writer")

        try:
            for i in range(frames):
                im = Image.new("RGB", (w, h), (20, 30, 60))
                d = ImageDraw.Draw(im)
                x = 40 + i * 10
                d.rectangle([x, 120, x + 120, 240], fill=(255, 200, 50))
                d.text((30, 20), f"FRAME {i}", fill=(240, 240, 240))
                frame_bgr = np.asarray(im)[:, :, ::-1]  # RGB -> BGR
                writer.write(frame_bgr)
        finally:
            writer.release()

        return out_path.read_bytes()


def _pil_to_jpeg_bytes(im: Image.Image, *, quality: int = 92) -> bytes:
    bio = io.BytesIO()
    im.save(bio, format="JPEG", quality=quality)
    return bio.getvalue()


def _center_crop_80(im: Image.Image) -> Image.Image:
    w, h = im.size
    nw, nh = int(w * 0.8), int(h * 0.8)
    left = (w - nw) // 2
    top = (h - nh) // 2
    return im.crop((left, top, left + nw, top + nh))


def _overlay_text(im: Image.Image, text: str = "LEAKED") -> Image.Image:
    base = im.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = base.size

    try:
        font = ImageFont.truetype("arial.ttf", size=max(24, w // 12))
    except Exception:
        font = ImageFont.load_default()

    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = right - left, bottom - top
    x = (w - text_w) // 2
    y = (h - text_h) // 2
    draw.text((x, y), text, font=font, fill=(255, 0, 0, 128))
    composed = Image.alpha_composite(base, overlay)
    return composed.convert("RGB")


def _flip_horizontal(im: Image.Image) -> Image.Image:
    return im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def _image_transformations(original: bytes) -> Dict[str, bytes]:
    im = Image.open(io.BytesIO(original)).convert("RGB")
    return {
        "Crop 80%": _pil_to_jpeg_bytes(_center_crop_80(im), quality=92),
        "Recompress JPEG q30": _pil_to_jpeg_bytes(im, quality=30),
        "Text overlay": _pil_to_jpeg_bytes(_overlay_text(im), quality=92),
        "Horizontal flip": _pil_to_jpeg_bytes(_flip_horizontal(im), quality=92),
    }


def _video_recompress_low_bitrate(video_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "in.mp4"
        out_path = Path(td) / "out.mp4"
        in_path.write_bytes(video_bytes)
        _run_ffmpeg(
            [
                "-y",
                "-i",
                str(in_path),
                "-c:v",
                "libx264",
                "-b:v",
                "300k",
                "-maxrate",
                "300k",
                "-bufsize",
                "600k",
                "-an",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
        )
        return out_path.read_bytes()


def _video_filter(video_bytes: bytes, vf: str) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "in.mp4"
        out_path = Path(td) / "out.mp4"
        in_path.write_bytes(video_bytes)
        _run_ffmpeg(
            [
                "-y",
                "-i",
                str(in_path),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
        )
        return out_path.read_bytes()


def _video_transformations(original: bytes) -> Dict[str, bytes]:
    # Crop 80% (center), overlay, flip, plus recompress.
    crop_vf = "crop=iw*0.8:ih*0.8:(iw-iw*0.8)/2:(ih-ih*0.8)/2"
    flip_vf = "hflip"
    return {
        "Crop 80%": _video_filter(original, crop_vf),
        "Recompress low bitrate": _video_recompress_low_bitrate(original),
        # Use OpenCV/Pillow frame overlay to avoid FFmpeg drawtext/fontconfig
        # issues on some Windows environments.
        "Text overlay": _video_overlay_text(original),
        "Horizontal flip": _video_filter(original, flip_vf),
    }


def _video_overlay_text(video_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "in.avi"
        out_path = Path(td) / "out.avi"
        in_path.write_bytes(video_bytes)

        cap = cv2.VideoCapture(str(in_path))
        if not cap.isOpened():
            raise RuntimeError("OpenCV failed to open video for text overlay")

        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 15.0)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 360)
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            writer = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))
            if not writer.isOpened():
                raise RuntimeError("OpenCV failed to create output video for text overlay")

            try:
                while True:
                    ok, frame_bgr = cap.read()
                    if not ok or frame_bgr is None:
                        break
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    im = Image.fromarray(frame_rgb)
                    over = _overlay_text(im, text="LEAKED")
                    over_bgr = cv2.cvtColor(np.asarray(over), cv2.COLOR_RGB2BGR)
                    writer.write(over_bgr)
            finally:
                writer.release()
        finally:
            cap.release()

        return out_path.read_bytes()


def _video_pooled_embedding(embedder: MultimodalEmbedder, video_bytes: bytes) -> List[float]:
    from services.fingerprint.keyframe import extract_keyframes

    keyframes = extract_keyframes(video_bytes, max_frames=10)
    if not keyframes:
        raise RuntimeError("No keyframes extracted; cannot embed video")
    vectors = [embedder.embed_video_frame(jpg) for jpg in keyframes]
    return _mean_pool(vectors)


def _screenshot_frame_as_image_bytes(video_bytes: bytes) -> bytes:
    # Use keyframes sampler and take the middle one as "screenshot".
    from services.fingerprint.keyframe import extract_keyframes

    keyframes = extract_keyframes(video_bytes, max_frames=5)
    if not keyframes:
        raise RuntimeError("No keyframes extracted for screenshot test")
    return keyframes[len(keyframes) // 2]


def _run_ffmpeg(args: List[str]) -> None:
    ffmpeg_bin = _resolve_ffmpeg_binary()
    cmd = [ffmpeg_bin, *args]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as e:
        raise RuntimeError("ffmpeg not found on PATH (required for robustness test)") from e
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg failed: {stderr}") from e


def _resolve_ffmpeg_binary() -> str:
    # 1) Explicit override for CI/local troubleshooting.
    explicit = os.getenv("FFMPEG_BIN")
    if explicit:
        return explicit

    # 2) Standard PATH resolution.
    resolved = shutil.which("ffmpeg")
    if resolved:
        return resolved

    # 3) Common WinGet shim path fallback.
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        candidate = Path(local_appdata) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "ffmpeg not found on PATH (required for robustness test). "
        "Install ffmpeg and ensure PATH is refreshed, or set FFMPEG_BIN."
    )


@dataclass
class _Row:
    transformation: str
    similarity: float
    passed: bool


def run_robustness() -> int:
    _load_setup_env(REPO_ROOT / "setup.env")
    image_bytes, video_bytes = _load_fixture_bytes()
    from services.fingerprint.embedder import MultimodalEmbedder

    embedder = MultimodalEmbedder.create()

    # IMAGE robustness
    original_img_vec = embedder.embed_image(image_bytes)
    img_rows: List[_Row] = []
    for name, transformed_bytes in _image_transformations(image_bytes).items():
        vec = embedder.embed_image(transformed_bytes)
        sim = _cosine_similarity(original_img_vec, vec)
        img_rows.append(_Row(name, sim, sim >= 0.80))

    # VIDEO robustness (pooled embedding)
    original_vid_vec = _video_pooled_embedding(embedder, video_bytes)
    vid_rows: List[_Row] = []
    for name, transformed_bytes in _video_transformations(video_bytes).items():
        vec = _video_pooled_embedding(embedder, transformed_bytes)
        sim = _cosine_similarity(original_vid_vec, vec)
        vid_rows.append(_Row(name, sim, sim >= 0.80))

    # Frame screenshot vs pooled video embedding
    screenshot_bytes = _screenshot_frame_as_image_bytes(video_bytes)
    screenshot_vec = embedder.embed_image(screenshot_bytes)
    sim = _cosine_similarity(original_vid_vec, screenshot_vec)
    vid_rows.append(_Row("Frame screenshot", sim, sim >= 0.80))

    print("\nIMAGE robustness\n")
    _print_rows(img_rows)
    print("\nVIDEO robustness (pooled)\n")
    _print_rows(vid_rows)

    failures = [r for r in img_rows + vid_rows if (not r.passed and r.transformation != "Horizontal flip")]
    # Horizontal flip is allowed to fail but must be visible in the table.
    return 1 if failures else 0


def _print_rows(rows: List[_Row]) -> None:
    print("Transformation         | Similarity | Pass")
    print("-----------------------+------------+-----")
    for r in rows:
        mark = "✓" if r.passed else "✗"
        print(f"{r.transformation:<23} | {r.similarity:>0.2f}       | {mark}")


if __name__ == "__main__":
    code = run_robustness()
    sys.exit(code)

