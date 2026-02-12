"""Tests for ugckit.pip_processor."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ugckit.models import PipConfig, Position
from ugckit.pip_processor import (
    PipProcessingError,
    _create_head_basic,
    _head_position_coords,
    _head_size,
    create_head_video,
)

# ── Helpers ─────────────────────────────────────────────────────────────


def make_fake_video(path: Path, duration: float = 3.0) -> Path:
    """Create a minimal mp4 file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=black:s=320x240:d={duration}",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=48000:cl=stereo",
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        pytest.skip("ffmpeg not available")
    return path


# ── Unit tests ──────────────────────────────────────────────────────────


class TestHeadSize:
    def test_default_scale(self):
        config = PipConfig()
        assert _head_size(config, 1080) == 270  # 0.25 * 1080

    def test_custom_scale(self):
        config = PipConfig(head_scale=0.5)
        assert _head_size(config, 1080) == 540


class TestHeadPositionCoords:
    def test_top_right(self):
        config = PipConfig(head_position=Position.TOP_RIGHT, head_margin=30)
        x, y = _head_position_coords(config, 1080, 1920)
        assert x == "1080-overlay_w-30"
        assert y == "30"

    def test_top_left(self):
        config = PipConfig(head_position=Position.TOP_LEFT, head_margin=20)
        x, y = _head_position_coords(config, 1080, 1920)
        assert x == "20"
        assert y == "20"

    def test_bottom_right(self):
        config = PipConfig(head_position=Position.BOTTOM_RIGHT, head_margin=10)
        x, y = _head_position_coords(config, 1080, 1920)
        assert x == "1080-overlay_w-10"
        assert y == "1920-overlay_h-10"

    def test_bottom_left(self):
        config = PipConfig(head_position=Position.BOTTOM_LEFT, head_margin=50)
        x, y = _head_position_coords(config, 1080, 1920)
        assert x == "50"
        assert y == "1920-overlay_h-50"


class TestCreateHeadVideo:
    def test_falls_back_to_basic(self, tmp_path):
        """create_head_video should fall back to basic when enhanced deps missing."""
        avatar = make_fake_video(tmp_path / "avatar.mp4", duration=1.0)
        config = PipConfig()

        # Mock _create_head_enhanced to raise ImportError
        with patch(
            "ugckit.pip_processor._create_head_enhanced",
            side_effect=ImportError("no mediapipe"),
        ):
            result = create_head_video(avatar, tmp_path / "head.webm", config)
            assert result.suffix == ".webm"
            assert result.exists()

    def test_missing_file_raises(self, tmp_path):
        config = PipConfig()
        with pytest.raises(PipProcessingError):
            _create_head_basic(
                tmp_path / "nonexistent.mp4",
                tmp_path / "head.webm",
                config,
                1080,
            )


class TestCreateHeadBasic:
    def test_produces_webm(self, tmp_path):
        avatar = make_fake_video(tmp_path / "avatar.mp4", duration=1.0)
        config = PipConfig()

        result = _create_head_basic(avatar, tmp_path / "head.webm", config, 1080)
        assert result.suffix == ".webm"
        assert result.exists()
        assert result.stat().st_size > 0


class TestCreateHeadEnhanced:
    def test_raises_without_deps(self, tmp_path):
        """Enhanced mode should raise ImportError when deps not available."""
        from ugckit.pip_processor import _create_head_enhanced

        avatar = make_fake_video(tmp_path / "avatar.mp4", duration=1.0)
        config = PipConfig()

        # This will raise ImportError since mediapipe/rembg likely not installed
        with pytest.raises((ImportError, PipProcessingError)):
            _create_head_enhanced(avatar, tmp_path / "head.webm", config, 1080)
