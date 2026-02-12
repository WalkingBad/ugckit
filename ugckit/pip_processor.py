"""PiP head extraction for UGCKit (Phase 2).

Creates head-only video from avatar clips for picture-in-picture mode.
Two-tier approach: basic (FFmpeg-only) and enhanced (MediaPipe + rembg).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from ugckit.models import PipConfig, Position


def create_head_video(
    avatar_path: Path,
    output_path: Path,
    config: PipConfig,
    output_width: int = 1080,
) -> Path:
    """Create head-only video from avatar clip.

    Tries enhanced mode (MediaPipe + rembg) first, falls back to basic circular crop.

    Args:
        avatar_path: Path to avatar video file.
        output_path: Path for output head video (WebM with alpha).
        config: PiP configuration.
        output_width: Output video width for scaling head size.

    Returns:
        Path to head video file.

    Raises:
        PipProcessingError: If head extraction fails.
    """
    try:
        return _create_head_enhanced(avatar_path, output_path, config, output_width)
    except (ImportError, PipProcessingError):
        return _create_head_basic(avatar_path, output_path, config, output_width)


class PipProcessingError(Exception):
    """Error during PiP head extraction."""

    pass


def _head_size(config: PipConfig, output_width: int) -> int:
    """Calculate head video size in pixels."""
    return int(output_width * config.head_scale)


def _head_position_coords(
    config: PipConfig,
    output_width: int,
    output_height: int,
) -> tuple[str, str]:
    """Calculate FFmpeg overlay coordinates for head position.

    Returns x, y expressions for FFmpeg overlay filter.
    """
    margin = config.head_margin
    pos = config.head_position

    if pos == Position.TOP_LEFT:
        return (str(margin), str(margin))
    elif pos == Position.TOP_RIGHT:
        return (f"{output_width}-overlay_w-{margin}", str(margin))
    elif pos == Position.BOTTOM_LEFT:
        return (str(margin), f"{output_height}-overlay_h-{margin}")
    else:  # BOTTOM_RIGHT
        return (f"{output_width}-overlay_w-{margin}", f"{output_height}-overlay_h-{margin}")


def _create_head_basic(
    avatar_path: Path,
    output_path: Path,
    config: PipConfig,
    output_width: int,
) -> Path:
    """FFmpeg-only: crop center square, apply circular mask via geq filter.

    Creates a WebM VP9 video with alpha channel containing a circular head cutout.
    """
    head_size = _head_size(config, output_width)

    # Crop center square from avatar, scale to head_size, apply circular alpha mask
    # geq filter creates circular transparency: alpha = 255 inside circle, 0 outside
    filter_complex = (
        f"[0:v]crop=min(iw\\,ih):min(iw\\,ih),"
        f"scale={head_size}:{head_size},"
        f"format=yuva420p,"
        f"geq="
        f"lum='lum(X,Y)':"
        f"cb='cb(X,Y)':"
        f"cr='cr(X,Y)':"
        f"a='if(lte(pow(X-{head_size}/2,2)+pow(Y-{head_size}/2,2),pow({head_size}/2-2,2)),255,0)'"
        f"[head]"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(avatar_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[head]",
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
        "-an",
        str(output_path.with_suffix(".webm")),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise PipProcessingError(f"Head extraction timed out for {avatar_path}")

    if result.returncode != 0:
        raise PipProcessingError(f"Head extraction failed: {result.stderr[:500]}")

    return output_path.with_suffix(".webm")


def _create_head_enhanced(
    avatar_path: Path,
    output_path: Path,
    config: PipConfig,
    output_width: int,
) -> Path:
    """MediaPipe face detection + rembg: detect face, crop, remove bg, circular mask.

    Requires: mediapipe, rembg, numpy, cv2 (opencv-python).

    Pipeline:
    1. mediapipe face detection -> face bounding box per frame
    2. Smooth bounding box across frames (moving average)
    3. Crop each frame to face region + margin
    4. rembg.remove() on each cropped frame -> RGBA
    5. Apply circular mask
    6. Encode to WebM VP9 with alpha via ffmpeg -f rawvideo
    """
    try:
        import cv2
        import mediapipe as mp
        import numpy as np
        from rembg import remove
    except ImportError as e:
        raise ImportError(
            f"Enhanced PiP mode requires: pip install mediapipe rembg opencv-python. Missing: {e}"
        )

    head_size = _head_size(config, output_width)

    cap = cv2.VideoCapture(str(avatar_path))
    if not cap.isOpened():
        raise PipProcessingError(f"Cannot open video: {avatar_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Phase 1: detect face bounding boxes
    face_detector = mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.5
    )

    bboxes = []
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_detector.process(rgb)

        if results.detections:
            det = results.detections[0]
            bb = det.location_data.relative_bounding_box
            bboxes.append((bb.xmin, bb.ymin, bb.width, bb.height))
        else:
            # Use previous bbox or center crop fallback
            if bboxes:
                bboxes.append(bboxes[-1])
            else:
                # Center crop fallback
                size = min(frame_width, frame_height)
                bboxes.append(
                    (
                        (frame_width - size) / (2 * frame_width),
                        (frame_height - size) / (2 * frame_height),
                        size / frame_width,
                        size / frame_height,
                    )
                )

    cap.release()
    face_detector.close()

    if not frames:
        raise PipProcessingError("No frames read from video")

    # Phase 2: smooth bounding boxes (5-frame moving average)
    window = 5
    smoothed = []
    for i in range(len(bboxes)):
        start = max(0, i - window // 2)
        end = min(len(bboxes), i + window // 2 + 1)
        chunk = bboxes[start:end]
        avg = tuple(sum(c) / len(chunk) for c in zip(*chunk))
        smoothed.append(avg)

    # Phase 3: process frames
    # Create circular mask
    mask = np.zeros((head_size, head_size), dtype=np.uint8)
    center = head_size // 2
    cv2.circle(mask, (center, center), center - 2, 255, -1)

    # Write raw RGBA frames to temp file, then encode with ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as raw_file:
        raw_path = Path(raw_file.name)

        for frame, (bx, by, bw, bh) in zip(frames, smoothed):
            # Expand bbox by 30% margin
            margin_factor = 0.3
            cx = bx + bw / 2
            cy = by + bh / 2
            size = max(bw, bh) * (1 + margin_factor)

            x1 = int(max(0, (cx - size / 2) * frame_width))
            y1 = int(max(0, (cy - size / 2) * frame_height))
            x2 = int(min(frame_width, (cx + size / 2) * frame_width))
            y2 = int(min(frame_height, (cy + size / 2) * frame_height))

            cropped = frame[y1:y2, x1:x2]
            if cropped.size == 0:
                cropped = frame  # fallback to full frame

            # Remove background
            cropped_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
            rgba = remove(cropped_rgb)

            # Resize to head_size
            rgba = cv2.resize(rgba, (head_size, head_size))

            # Apply circular mask to alpha channel
            rgba[:, :, 3] = cv2.bitwise_and(rgba[:, :, 3], mask)

            raw_file.write(rgba.tobytes())

    # Encode to WebM VP9 with alpha
    out_webm = output_path.with_suffix(".webm")
    out_webm.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{head_size}x{head_size}",
        "-r",
        str(fps),
        "-i",
        str(raw_path),
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
        "-an",
        str(out_webm),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise PipProcessingError("Enhanced head encoding timed out")
    finally:
        raw_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise PipProcessingError(f"Enhanced head encoding failed: {result.stderr[:500]}")

    return out_webm


def create_transparent_avatar(
    avatar_path: Path,
    output_path: Path,
    scale: float = 0.8,
    output_width: int = 1080,
) -> Path:
    """Remove avatar background and produce a WebM VP9 video with alpha.

    Uses rembg to remove background from each frame (no face detection
    or circular mask — preserves full body).

    Args:
        avatar_path: Path to avatar video file.
        output_path: Output path (will use .webm extension).
        scale: Scale factor relative to output_width.
        output_width: Reference output width.

    Returns:
        Path to transparent avatar WebM file.

    Raises:
        PipProcessingError: If processing fails.
        ImportError: If rembg/opencv not installed.
    """
    try:
        import cv2
        import numpy as np
        from rembg import remove
    except ImportError as e:
        raise ImportError(
            f"Green screen mode requires: pip install rembg opencv-python. Missing: {e}"
        )

    cap = cv2.VideoCapture(str(avatar_path))
    if not cap.isOpened():
        raise PipProcessingError(f"Cannot open video: {avatar_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    target_w = int(output_width * scale)

    frames_rgba = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgba = remove(rgb)
        rgba = cv2.resize(rgba, (target_w, int(target_w * rgba.shape[0] / rgba.shape[1])))
        frames_rgba.append(rgba)

    cap.release()

    if not frames_rgba:
        raise PipProcessingError("No frames read from video")

    frame_h, frame_w = frames_rgba[0].shape[:2]

    with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as raw_file:
        raw_path = Path(raw_file.name)
        for frame in frames_rgba:
            raw_file.write(frame.tobytes())

    out_webm = output_path.with_suffix(".webm")
    out_webm.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{frame_w}x{frame_h}",
        "-r",
        str(fps),
        "-i",
        str(raw_path),
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
        "-an",
        str(out_webm),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise PipProcessingError("Transparent avatar encoding timed out")
    finally:
        raw_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise PipProcessingError(f"Transparent avatar encoding failed: {result.stderr[:500]}")

    return out_webm
