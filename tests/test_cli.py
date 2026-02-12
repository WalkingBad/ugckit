"""Tests for ugckit.cli."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ugckit.cli import main

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


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def setup_workspace(tmp_path):
    """Create scripts dir and avatar dir for CLI tests."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "T1.md").write_text(
        """\
### Script T1: "Test Script"

**Clip 1 (8s):**
Says: "First segment of the test script."

**Clip 2 (8s):**
Says: "Second segment of the test script."
"""
    )

    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir()

    return scripts_dir, avatar_dir


# ── list-scripts ────────────────────────────────────────────────────────


class TestListScripts:
    def test_basic(self, runner, setup_workspace):
        scripts_dir, _ = setup_workspace
        result = runner.invoke(main, ["list-scripts", "-d", str(scripts_dir)])
        assert result.exit_code == 0
        assert "T1" in result.output
        assert "1 scripts" in result.output

    def test_empty_dir(self, runner, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        result = runner.invoke(main, ["list-scripts", "-d", str(d)])
        assert result.exit_code == 0
        assert "No scripts found" in result.output

    def test_shows_header_duration(self, runner, setup_workspace):
        scripts_dir, _ = setup_workspace
        result = runner.invoke(main, ["list-scripts", "-d", str(scripts_dir)])
        assert "~16s" in result.output  # 2 clips * 8s


# ── show-script ─────────────────────────────────────────────────────────


class TestShowScript:
    def test_basic(self, runner, setup_workspace):
        scripts_dir, _ = setup_workspace
        result = runner.invoke(main, ["show-script", "-s", "T1", "--scripts-dir", str(scripts_dir)])
        assert result.exit_code == 0
        assert "T1" in result.output
        assert "8.0s" in result.output

    def test_not_found(self, runner, setup_workspace):
        scripts_dir, _ = setup_workspace
        result = runner.invoke(
            main, ["show-script", "-s", "ZZ99", "--scripts-dir", str(scripts_dir)]
        )
        assert result.exit_code != 0


# ── compose ─────────────────────────────────────────────────────────────


class TestCompose:
    def test_no_avatars_error(self, runner, setup_workspace):
        scripts_dir, _ = setup_workspace
        result = runner.invoke(main, ["compose", "-s", "T1", "-d", str(scripts_dir)])
        assert result.exit_code != 0
        assert "provide --avatars or --avatar-dir" in result.output

    def test_empty_avatar_dir(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        result = runner.invoke(
            main, ["compose", "-s", "T1", "--avatar-dir", str(avatar_dir), "-d", str(scripts_dir)]
        )
        assert result.exit_code != 0
        assert "no .mp4 files" in result.output

    def test_dry_run_with_avatar_dir(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)
        make_fake_video(avatar_dir / "seg2.mp4", duration=2.0)

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Timeline for T1" in result.output
        assert "Dry run" in result.output
        assert "ffmpeg" in result.output

    def test_dry_run_with_avatars(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        v1 = make_fake_video(avatar_dir / "a.mp4", duration=2.0)
        v2 = make_fake_video(avatar_dir / "b.mp4", duration=2.0)

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "-a",
                str(v1),
                "-a",
                str(v2),
                "-d",
                str(scripts_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "ffmpeg" in result.output

    def test_full_render(self, runner, setup_workspace, tmp_path):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)
        make_fake_video(avatar_dir / "seg2.mp4", duration=2.0)
        output = tmp_path / "output" / "result.mp4"

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "-o",
                str(output),
            ],
        )
        assert result.exit_code == 0
        assert "Done!" in result.output
        assert output.exists()

    def test_pip_mode_dry_run(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)
        make_fake_video(avatar_dir / "seg2.mp4", duration=2.0)

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "--mode",
                "pip",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Timeline for T1" in result.output
        assert "ffmpeg" in result.output

    def test_head_scale_option(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "--head-scale",
                "0.3",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

    def test_sync_flag_without_whisper(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)
        make_fake_video(avatar_dir / "seg2.mp4", duration=2.0)

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "--sync",
                "--dry-run",
            ],
        )
        # Should warn about missing whisper but still succeed
        assert result.exit_code == 0
        assert "Smart Sync" in result.output


# ── batch ───────────────────────────────────────────────────────────────


class TestBatch:
    def test_no_matching_avatars(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        # Add a second script so single-script fallback doesn't apply
        (scripts_dir / "T2.md").write_text(
            '### Script T2: "Second"\n\n**Clip 1 (8s):**\nSays: "Hello"\n'
        )
        make_fake_video(avatar_dir / "unrelated.mp4", duration=2.0)

        result = runner.invoke(
            main,
            ["batch", "-d", str(scripts_dir), "--avatar-dir", str(avatar_dir), "--dry-run"],
        )
        assert result.exit_code == 0
        assert "SKIP" in result.output

    def test_prefix_matching(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "T1_seg1.mp4", duration=2.0)
        make_fake_video(avatar_dir / "T1_seg2.mp4", duration=2.0)

        result = runner.invoke(
            main,
            ["batch", "-d", str(scripts_dir), "--avatar-dir", str(avatar_dir), "--dry-run"],
        )
        assert result.exit_code == 0
        assert "T1" in result.output
        assert "2 clips" in result.output
        assert "Batch complete: 1 ok" in result.output

    def test_empty_scripts_dir(self, runner, tmp_path):
        s = tmp_path / "s"
        s.mkdir()
        a = tmp_path / "a"
        a.mkdir()
        make_fake_video(a / "x.mp4", duration=1.0)

        result = runner.invoke(main, ["batch", "-d", str(s), "--avatar-dir", str(a)])
        assert result.exit_code != 0

    def test_empty_avatar_dir(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        result = runner.invoke(
            main, ["batch", "-d", str(scripts_dir), "--avatar-dir", str(avatar_dir)]
        )
        assert result.exit_code != 0
        assert "No .mp4 files" in result.output


# ── New mode/option tests ──────────────────────────────────────────


class TestComposeNewModes:
    def test_split_mode_dry_run(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)
        make_fake_video(avatar_dir / "seg2.mp4", duration=2.0)

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "--mode",
                "split",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "ffmpeg" in result.output

    def test_greenscreen_mode_dry_run(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)
        make_fake_video(avatar_dir / "seg2.mp4", duration=2.0)

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "--mode",
                "greenscreen",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "ffmpeg" in result.output

    def test_music_option_dry_run(self, runner, setup_workspace, tmp_path):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)
        make_fake_video(avatar_dir / "seg2.mp4", duration=2.0)

        # Create a fake music file
        music_file = tmp_path / "bg.mp3"
        music_file.touch()

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "--music",
                str(music_file),
                "--music-volume",
                "0.2",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "ffmpeg" in result.output

    def test_subtitles_flag_dry_run(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)
        make_fake_video(avatar_dir / "seg2.mp4", duration=2.0)

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "--subtitles",
                "--dry-run",
            ],
        )
        # May warn about whisper not installed but should still succeed
        assert result.exit_code == 0

    def test_avatar_side_option(self, runner, setup_workspace):
        scripts_dir, avatar_dir = setup_workspace
        make_fake_video(avatar_dir / "seg1.mp4", duration=2.0)

        result = runner.invoke(
            main,
            [
                "compose",
                "-s",
                "T1",
                "--avatar-dir",
                str(avatar_dir),
                "-d",
                str(scripts_dir),
                "--mode",
                "split",
                "--avatar-side",
                "right",
                "--split-ratio",
                "0.4",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
