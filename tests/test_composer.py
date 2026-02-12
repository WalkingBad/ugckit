"""Tests for ugckit.composer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ugckit.composer import (
    FFmpegError,
    _detect_composition_mode,  # noqa: F401
    build_ffmpeg_filter_greenscreen,  # noqa: F401
    build_ffmpeg_filter_overlay,
    build_ffmpeg_filter_split,  # noqa: F401
    build_timeline,
    compose_video,
    compose_video_with_progress,
    format_ffmpeg_cmd,
    format_timeline,
    get_video_duration,
    has_audio_stream,
    position_to_overlay_coords,
    validate_timeline_files,
    wrap_with_post_processing,  # noqa: F401
)
from ugckit.models import (
    CompositionMode,
    Config,
    MusicConfig,  # noqa: F401
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


# ── PiP filter builder tests ──────────────────────────────────────────


class TestBuildFfmpegFilterPip:
    def _make_pip_timeline(self, tmp_path) -> Timeline:
        """Create a timeline with PiP screencast entries."""

        entries = [
            TimelineEntry(start=0, end=8, type="avatar", file=tmp_path / "a.mp4", parent_segment=1),
            TimelineEntry(
                start=2,
                end=6,
                type="screencast",
                file=tmp_path / "sc.mp4",
                parent_segment=1,
                composition_mode=CompositionMode.PIP,
            ),
        ]
        return Timeline(
            script_id="P1",
            total_duration=8.0,
            entries=entries,
            output_path=tmp_path / "out.mp4",
        )

    def test_pip_filter_has_fullscreen_overlay(self, tmp_path):
        from ugckit.composer import build_ffmpeg_filter_pip

        tl = self._make_pip_timeline(tmp_path)
        cfg = Config()
        result = build_ffmpeg_filter_pip(tl, cfg, audio_presence=[True])
        # PiP mode should scale screencast to fullscreen
        assert "1080:1920" in result  # fullscreen scale
        assert "[vout]" in result
        assert "[aout]" in result

    def test_pip_filter_with_head_videos(self, tmp_path):
        from ugckit.composer import build_ffmpeg_filter_pip

        tl = self._make_pip_timeline(tmp_path)
        cfg = Config()
        head_vids = [tmp_path / "head_0.webm"]
        result = build_ffmpeg_filter_pip(tl, cfg, audio_presence=[True], head_videos=head_vids)
        # Should include head overlay
        assert "overlay" in result.lower()

    def test_pip_audio_presence_mismatch(self, tmp_path):
        from ugckit.composer import build_ffmpeg_filter_pip

        tl = self._make_pip_timeline(tmp_path)
        cfg = Config()
        with pytest.raises(ValueError, match="audio_presence length"):
            build_ffmpeg_filter_pip(tl, cfg, audio_presence=[True, True])


class TestBuildTimelinePreservesMode:
    def test_screencast_mode_propagated(self, tmp_path):
        """build_timeline should copy screencast mode to TimelineEntry."""
        from ugckit.models import ScreencastOverlay

        v1 = make_fake_video(tmp_path / "seg1.mp4", duration=3.0)
        sc_dir = tmp_path / "screencasts"
        sc_dir.mkdir()
        (sc_dir / "app.mp4").touch()

        script = Script(
            script_id="T1",
            title="Test",
            total_duration=8.0,
            segments=[
                Segment(
                    id=1,
                    text="Test",
                    duration=8.0,
                    screencasts=[
                        ScreencastOverlay(
                            file="app.mp4",
                            start=1.0,
                            end=3.0,
                            mode=CompositionMode.PIP,
                        )
                    ],
                )
            ],
        )
        tl = build_timeline(script, [v1], sc_dir, tmp_path / "out.mp4")
        sc_entries = [e for e in tl.entries if e.type == "screencast"]
        assert len(sc_entries) == 1
        assert sc_entries[0].composition_mode == CompositionMode.PIP


# ── Split screen tests ─────────────────────────────────────────────


class TestBuildFfmpegFilterSplit:
    def _make_split_timeline(self, tmp_path) -> Timeline:
        entries = [
            TimelineEntry(start=0, end=8, type="avatar", file=tmp_path / "a.mp4", parent_segment=1),
            TimelineEntry(
                start=2,
                end=6,
                type="screencast",
                file=tmp_path / "sc.mp4",
                parent_segment=1,
                composition_mode=CompositionMode.SPLIT,
            ),
        ]
        return Timeline(
            script_id="S1",
            total_duration=8.0,
            entries=entries,
            output_path=tmp_path / "out.mp4",
        )

    def test_contains_hstack(self, tmp_path):
        tl = self._make_split_timeline(tmp_path)
        cfg = Config()
        result = build_ffmpeg_filter_split(tl, cfg, audio_presence=[True])
        assert "hstack" in result
        assert "split=2" in result  # stream must be duplicated
        assert "[vout]" in result
        assert "[aout]" in result

    def test_avatar_side_left(self, tmp_path):
        tl = self._make_split_timeline(tmp_path)
        cfg = Config()
        cfg.composition.split.avatar_side = "left"
        result = build_ffmpeg_filter_split(tl, cfg, audio_presence=[True])
        assert "hstack" in result

    def test_avatar_side_right(self, tmp_path):
        tl = self._make_split_timeline(tmp_path)
        cfg = Config()
        cfg.composition.split.avatar_side = "right"
        result = build_ffmpeg_filter_split(tl, cfg, audio_presence=[True])
        assert "hstack" in result

    def test_no_screencasts(self, tmp_path):
        tl = make_timeline([tmp_path / "a.mp4"], tmp_path / "out.mp4")
        cfg = Config()
        result = build_ffmpeg_filter_split(tl, cfg, audio_presence=[True])
        assert "[base]null[vout]" in result


# ── Green screen tests ─────────────────────────────────────────────


class TestBuildFfmpegFilterGreenscreen:
    def _make_gs_timeline(self, tmp_path) -> Timeline:
        entries = [
            TimelineEntry(start=0, end=8, type="avatar", file=tmp_path / "a.mp4", parent_segment=1),
            TimelineEntry(
                start=2,
                end=6,
                type="screencast",
                file=tmp_path / "sc.mp4",
                parent_segment=1,
                composition_mode=CompositionMode.GREENSCREEN,
            ),
        ]
        return Timeline(
            script_id="G1",
            total_duration=8.0,
            entries=entries,
            output_path=tmp_path / "out.mp4",
        )

    def test_has_overlay(self, tmp_path):
        tl = self._make_gs_timeline(tmp_path)
        cfg = Config()
        result = build_ffmpeg_filter_greenscreen(tl, cfg, audio_presence=[True])
        assert "overlay" in result.lower()
        assert "[vout]" in result
        assert "[aout]" in result

    def test_with_transparent_avatars(self, tmp_path):
        tl = self._make_gs_timeline(tmp_path)
        cfg = Config()
        ta = [tmp_path / "ta_0.webm"]
        result = build_ffmpeg_filter_greenscreen(
            tl, cfg, audio_presence=[True], transparent_avatars=ta
        )
        # Should reference the transparent avatar input
        assert "ta_" in result


# ── Post-processing wrapper tests ──────────────────────────────────


class TestWrapWithPostProcessing:
    def test_no_op_returns_same(self):
        original = "[0:v]null[vout];[0:a]anull[aout]"
        result = wrap_with_post_processing(original)
        assert result == original

    def test_subtitles_only(self, tmp_path):
        original = "[0:v]null[vout];[0:a]anull[aout]"
        sub_file = tmp_path / "subs.ass"
        sub_file.write_text("dummy")
        result = wrap_with_post_processing(original, subtitle_file=sub_file)
        assert "[vout_pre]" in result
        assert "ass=" in result
        assert "[aout]" in result  # audio unchanged

    def test_music_only(self):
        original = "[0:v]null[vout];[0:a]anull[aout]"
        music_cfg = MusicConfig(enabled=True, volume=0.2, fade_out_duration=1.5, loop=True)
        result = wrap_with_post_processing(
            original, music_input_index=1, music_config=music_cfg, total_duration=10.0
        )
        assert "[aout_pre]" in result
        assert "aloop" in result
        assert "amix" in result
        assert "[vout]" in result  # video unchanged

    def test_music_no_loop(self):
        original = "[0:v]null[vout];[0:a]anull[aout]"
        music_cfg = MusicConfig(enabled=True, volume=0.1, fade_out_duration=2.0, loop=False)
        result = wrap_with_post_processing(
            original, music_input_index=2, music_config=music_cfg, total_duration=8.0
        )
        assert "aloop" not in result
        assert "atrim" in result
        assert "amix" in result

    def test_both_subtitles_and_music(self, tmp_path):
        original = "[0:v]null[vout];[0:a]anull[aout]"
        sub_file = tmp_path / "subs.ass"
        sub_file.write_text("dummy")
        music_cfg = MusicConfig(enabled=True, volume=0.15)
        result = wrap_with_post_processing(
            original,
            subtitle_file=sub_file,
            music_input_index=1,
            music_config=music_cfg,
            total_duration=10.0,
        )
        assert "ass=" in result
        assert "amix" in result


# ── Mode detection tests ───────────────────────────────────────────


class TestDetectCompositionMode:
    def test_overlay_default(self, tmp_path):
        tl = make_timeline([tmp_path / "a.mp4"], tmp_path / "out.mp4")
        assert _detect_composition_mode(tl) == CompositionMode.OVERLAY

    def test_pip_detected(self, tmp_path):
        entries = [
            TimelineEntry(start=0, end=8, type="avatar", file=tmp_path / "a.mp4"),
            TimelineEntry(
                start=2,
                end=6,
                type="screencast",
                file=tmp_path / "sc.mp4",
                composition_mode=CompositionMode.PIP,
            ),
        ]
        tl = Timeline(script_id="P", total_duration=8, entries=entries)
        assert _detect_composition_mode(tl) == CompositionMode.PIP

    def test_split_detected(self, tmp_path):
        entries = [
            TimelineEntry(start=0, end=8, type="avatar", file=tmp_path / "a.mp4"),
            TimelineEntry(
                start=2,
                end=6,
                type="screencast",
                file=tmp_path / "sc.mp4",
                composition_mode=CompositionMode.SPLIT,
            ),
        ]
        tl = Timeline(script_id="S", total_duration=8, entries=entries)
        assert _detect_composition_mode(tl) == CompositionMode.SPLIT

    def test_greenscreen_detected(self, tmp_path):
        entries = [
            TimelineEntry(start=0, end=8, type="avatar", file=tmp_path / "a.mp4"),
            TimelineEntry(
                start=2,
                end=6,
                type="screencast",
                file=tmp_path / "sc.mp4",
                composition_mode=CompositionMode.GREENSCREEN,
            ),
        ]
        tl = Timeline(script_id="G", total_duration=8, entries=entries)
        assert _detect_composition_mode(tl) == CompositionMode.GREENSCREEN

    def test_greenscreen_takes_priority(self, tmp_path):
        """When mixed modes, greenscreen > pip > split."""
        entries = [
            TimelineEntry(start=0, end=8, type="avatar", file=tmp_path / "a.mp4"),
            TimelineEntry(
                start=1,
                end=3,
                type="screencast",
                file=tmp_path / "s1.mp4",
                composition_mode=CompositionMode.PIP,
            ),
            TimelineEntry(
                start=4,
                end=6,
                type="screencast",
                file=tmp_path / "s2.mp4",
                composition_mode=CompositionMode.GREENSCREEN,
            ),
        ]
        tl = Timeline(script_id="M", total_duration=8, entries=entries)
        assert _detect_composition_mode(tl) == CompositionMode.GREENSCREEN


# ── Finalize filter tests ────────────────────────────────────────────


class TestFinalizeFilter:
    def test_normalize(self):
        from ugckit.composer import _finalize_filter

        filters = ["[0:v]null[base]"]
        cfg = Config()
        result = _finalize_filter(filters, "base", cfg)
        assert "[base]null[vout]" in result
        assert "loudnorm" in result
        assert "[aout]" in result

    def test_no_normalize(self):
        from ugckit.composer import _finalize_filter

        filters = ["[0:v]null[base]"]
        cfg = Config()
        cfg.audio.normalize = False
        result = _finalize_filter(filters, "base", cfg)
        assert "[base]null[vout]" in result
        assert "[audio]anull[aout]" in result
        assert "loudnorm" not in result


# ── Filter builder registry tests ────────────────────────────────────


class TestFilterBuilderRegistry:
    def test_covers_all_modes(self):
        from ugckit.composer import _FILTER_BUILDERS

        for mode in CompositionMode:
            assert mode in _FILTER_BUILDERS, f"Missing builder for {mode}"
