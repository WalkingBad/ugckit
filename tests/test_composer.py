"""Tests for ugckit.composer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ugckit.composer import (
    FFmpegError,
    build_ffmpeg_filter_overlay,
    build_timeline,
    compose_video,
    compose_video_with_progress,
    format_ffmpeg_cmd,
    format_timeline,
    get_video_duration,
    has_audio_stream,
    position_to_overlay_coords,
    validate_timeline_files,
)
from ugckit.models import (
    Config,
    Position,
    Script,
    Segment,
    Timeline,
    TimelineEntry,
)

# ── Helpers ─────────────────────────────────────────────────────────────


def make_fake_video(path: Path, duration: float = 8.0) -> Path:
    """Create a minimal mp4 file for testing (1s black video)."""
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
        pytest.skip(f"ffmpeg not available: {result.stderr[:200]}")
    return path


def make_script(num_segments: int = 2) -> Script:
    """Create a test Script model."""
    segments = [
        Segment(id=i + 1, text=f"Segment {i+1} text", duration=8.0) for i in range(num_segments)
    ]
    return Script(
        script_id="T1",
        title="Test",
        total_duration=sum(s.duration for s in segments),
        segments=segments,
    )


def make_timeline(avatar_files: list[Path], output_path: Path) -> Timeline:
    """Create a test Timeline."""
    entries = []
    t = 0.0
    for i, f in enumerate(avatar_files):
        entries.append(
            TimelineEntry(start=t, end=t + 8.0, type="avatar", file=f, parent_segment=i + 1)
        )
        t += 8.0
    return Timeline(
        script_id="T1",
        total_duration=t,
        entries=entries,
        output_path=output_path,
    )


# ── Unit tests ──────────────────────────────────────────────────────────


class TestPositionToOverlayCoords:
    def test_bottom_right(self):
        x, y = position_to_overlay_coords(Position.BOTTOM_RIGHT, 50, "w", "h")
        assert x == "W-w-50"
        assert y == "H-h-50"

    def test_top_left(self):
        x, y = position_to_overlay_coords(Position.TOP_LEFT, 30)
        assert x == "30"
        assert y == "30"

    def test_top_right(self):
        x, y = position_to_overlay_coords(Position.TOP_RIGHT, 10, "w", "h")
        assert x == "W-w-10"
        assert y == "10"

    def test_bottom_left(self):
        x, y = position_to_overlay_coords(Position.BOTTOM_LEFT, 20, "w", "h")
        assert x == "20"
        assert y == "H-h-20"


class TestFormatTimeline:
    def test_basic(self, tmp_path):
        tl = make_timeline(
            [tmp_path / "a.mp4", tmp_path / "b.mp4"],
            tmp_path / "out.mp4",
        )
        text = format_timeline(tl)
        assert "T1" in text
        assert "a.mp4" in text
        assert "b.mp4" in text
        assert "out.mp4" in text

    def test_empty_entries(self, tmp_path):
        tl = Timeline(
            script_id="E1",
            total_duration=0.0,
            entries=[],
            output_path=tmp_path / "out.mp4",
        )
        text = format_timeline(tl)
        assert "E1" in text


class TestFormatFfmpegCmd:
    def test_basic(self):
        cmd = ["ffmpeg", "-i", "input.mp4", "-y", "output.mp4"]
        result = format_ffmpeg_cmd(cmd)
        assert "ffmpeg" in result
        assert "input.mp4" in result

    def test_spaces_quoted(self):
        cmd = ["ffmpeg", "-i", "my file.mp4"]
        result = format_ffmpeg_cmd(cmd)
        assert "my file.mp4" in result  # should be quoted


class TestValidateTimelineFiles:
    def test_all_exist(self, tmp_path):
        f1 = tmp_path / "a.mp4"
        f1.touch()
        tl = Timeline(
            script_id="V1",
            total_duration=8.0,
            entries=[TimelineEntry(start=0, end=8, type="avatar", file=f1)],
        )
        validate_timeline_files(tl)  # should not raise

    def test_missing_file(self, tmp_path):
        tl = Timeline(
            script_id="V2",
            total_duration=8.0,
            entries=[
                TimelineEntry(start=0, end=8, type="avatar", file=tmp_path / "nonexistent.mp4")
            ],
        )
        with pytest.raises(FFmpegError, match="Missing files"):
            validate_timeline_files(tl)


class TestBuildFfmpegFilterOverlay:
    def test_single_avatar(self, tmp_path):
        tl = make_timeline([tmp_path / "a.mp4"], tmp_path / "out.mp4")
        cfg = Config()
        result = build_ffmpeg_filter_overlay(tl, cfg, audio_presence=[True])
        assert "[av0]copy[base]" in result
        assert "[vout]" in result
        assert "[aout]" in result

    def test_two_avatars_concat(self, tmp_path):
        tl = make_timeline(
            [tmp_path / "a.mp4", tmp_path / "b.mp4"],
            tmp_path / "out.mp4",
        )
        cfg = Config()
        result = build_ffmpeg_filter_overlay(tl, cfg, audio_presence=[True, True])
        assert "concat=n=2:v=1:a=0[base]" in result

    def test_audio_presence_mismatch(self, tmp_path):
        tl = make_timeline([tmp_path / "a.mp4"], tmp_path / "out.mp4")
        cfg = Config()
        with pytest.raises(ValueError, match="audio_presence length"):
            build_ffmpeg_filter_overlay(tl, cfg, audio_presence=[True, True])


# ── Integration tests (require ffmpeg) ──────────────────────────────────


class TestGetVideoDuration:
    def test_real_file(self, tmp_path):
        video = make_fake_video(tmp_path / "test.mp4", duration=2.0)
        dur = get_video_duration(video)
        assert 1.5 < dur < 3.0  # allow tolerance

    def test_missing_file(self, tmp_path):
        with pytest.raises(FFmpegError, match="not found"):
            get_video_duration(tmp_path / "nope.mp4")


class TestHasAudioStream:
    def test_with_audio(self, tmp_path):
        video = make_fake_video(tmp_path / "with_audio.mp4")
        assert has_audio_stream(video) is True


class TestBuildTimeline:
    def test_basic(self, tmp_path):
        v1 = make_fake_video(tmp_path / "seg1.mp4", duration=3.0)
        v2 = make_fake_video(tmp_path / "seg2.mp4", duration=4.0)
        script = make_script(2)
        sc_dir = tmp_path / "screencasts"
        sc_dir.mkdir()

        tl = build_timeline(script, [v1, v2], sc_dir, tmp_path / "out.mp4")
        assert len(tl.entries) == 2
        assert tl.entries[0].type == "avatar"
        assert tl.entries[1].type == "avatar"
        assert tl.total_duration > 0

    def test_empty_clips_raises(self, tmp_path):
        script = make_script(1)
        sc_dir = tmp_path / "sc"
        sc_dir.mkdir()
        with pytest.raises(ValueError, match="cannot be empty"):
            build_timeline(script, [], sc_dir, tmp_path / "out.mp4")

    def test_fewer_clips_than_segments(self, tmp_path):
        v1 = make_fake_video(tmp_path / "only_one.mp4", duration=3.0)
        script = make_script(3)
        sc_dir = tmp_path / "sc"
        sc_dir.mkdir()

        tl = build_timeline(script, [v1], sc_dir, tmp_path / "out.mp4")
        assert len(tl.entries) == 1  # only 1 clip for 3 segments


class TestComposeVideoDryRun:
    def test_returns_cmd_list(self, tmp_path):
        v1 = make_fake_video(tmp_path / "a.mp4", duration=2.0)
        script = make_script(1)
        sc_dir = tmp_path / "sc"
        sc_dir.mkdir()

        tl = build_timeline(script, [v1], sc_dir, tmp_path / "out.mp4")
        cfg = Config()
        result = compose_video(tl, cfg, dry_run=True)
        assert isinstance(result, list)
        assert result[0] == "ffmpeg"
        assert "-filter_complex" in result

    def test_no_output_path_raises(self):
        tl = Timeline(script_id="X", total_duration=0, entries=[])
        with pytest.raises(ValueError, match="output_path"):
            compose_video(tl, Config(), dry_run=True)


class TestComposeVideoRender:
    def test_full_render(self, tmp_path):
        v1 = make_fake_video(tmp_path / "seg1.mp4", duration=2.0)
        v2 = make_fake_video(tmp_path / "seg2.mp4", duration=2.0)
        script = make_script(2)
        sc_dir = tmp_path / "sc"
        sc_dir.mkdir()
        output = tmp_path / "output" / "result.mp4"

        tl = build_timeline(script, [v1, v2], sc_dir, output)
        cfg = Config()
        result = compose_video(tl, cfg, dry_run=False)
        assert result == output
        assert output.exists()
        assert output.stat().st_size > 0


class TestComposeVideoWithProgress:
    def test_progress_callback(self, tmp_path):
        v1 = make_fake_video(tmp_path / "p1.mp4", duration=2.0)
        script = make_script(1)
        sc_dir = tmp_path / "sc"
        sc_dir.mkdir()
        output = tmp_path / "output" / "progress.mp4"

        tl = build_timeline(script, [v1], sc_dir, output)
        # Disable loudnorm to avoid NaN issues with short synthetic audio
        cfg = Config()
        cfg.audio.normalize = False

        progress_values = []
        compose_video_with_progress(tl, cfg, progress_callback=progress_values.append)

        assert output.exists()
        assert len(progress_values) > 0
        assert progress_values[-1] == 1.0  # should end at 1.0
