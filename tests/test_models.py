"""Tests for ugckit.models and ugckit.config."""

from __future__ import annotations

from pathlib import Path

from ugckit.config import load_config
from ugckit.models import (
    CompositionMode,
    Config,
    Position,
    ScreencastOverlay,
    Script,
    Segment,
    Timeline,
    TimelineEntry,
)


class TestConfig:
    def test_default_values(self):
        cfg = Config()
        assert cfg.output.fps == 30
        assert cfg.output.resolution == (1080, 1920)
        assert cfg.output.codec == "libx264"
        assert cfg.output.crf == 23
        assert cfg.audio.normalize is True
        assert cfg.audio.target_loudness == -14
        assert cfg.composition.overlay.scale == 0.4
        assert cfg.composition.overlay.position == Position.BOTTOM_RIGHT

    def test_load_default_yaml(self):
        cfg = load_config()
        assert cfg.output.fps == 30
        assert cfg.composition.overlay.margin == 50

    def test_load_nonexistent_returns_default(self, tmp_path):
        cfg = load_config(tmp_path / "nope.yaml")
        assert cfg.output.fps == 30

    def test_load_custom_yaml(self, tmp_path):
        yaml_path = tmp_path / "custom.yaml"
        yaml_path.write_text(
            """\
output:
  fps: 60
  crf: 18
audio:
  normalize: false
"""
        )
        cfg = load_config(yaml_path)
        assert cfg.output.fps == 60
        assert cfg.output.crf == 18
        assert cfg.audio.normalize is False

    def test_yaml_resolution_list(self, tmp_path):
        yaml_path = tmp_path / "res.yaml"
        yaml_path.write_text("output:\n  resolution: [720, 1280]\n")
        cfg = load_config(yaml_path)
        assert cfg.output.resolution == (720, 1280)

    def test_yaml_paths_section(self, tmp_path):
        yaml_path = tmp_path / "paths.yaml"
        yaml_path.write_text("paths:\n  screencasts: /tmp/sc\n  output: /tmp/out\n")
        cfg = load_config(yaml_path)
        assert cfg.screencasts_path == Path("/tmp/sc")
        assert cfg.output_path == Path("/tmp/out")


class TestModels:
    def test_segment(self):
        seg = Segment(id=1, text="hello", duration=5.0)
        assert seg.id == 1
        assert seg.screencasts == []

    def test_screencast_overlay(self):
        sc = ScreencastOverlay(file="demo.mp4", start=1.0, end=5.0)
        assert sc.mode == CompositionMode.OVERLAY

    def test_script(self):
        s = Script(script_id="A1", title="Test", segments=[])
        assert s.total_duration == 0.0
        assert s.character is None

    def test_timeline_entry(self, tmp_path):
        e = TimelineEntry(start=0, end=8, type="avatar", file=tmp_path / "a.mp4")
        assert e.parent_segment is None

    def test_timeline(self, tmp_path):
        tl = Timeline(script_id="X", total_duration=0, entries=[])
        assert tl.output_path is None


class TestPosition:
    def test_all_values(self):
        values = [p.value for p in Position]
        assert "top-left" in values
        assert "top-right" in values
        assert "bottom-left" in values
        assert "bottom-right" in values

    def test_from_string(self):
        assert Position("bottom-right") == Position.BOTTOM_RIGHT
