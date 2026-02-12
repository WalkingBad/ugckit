"""Tests for ugckit.subtitles."""

from __future__ import annotations

from ugckit.models import Config, Timeline
from ugckit.subtitles import (
    SubtitleLine,
    WordTimestamp,
    _format_ass_time,
    _group_words_into_lines,
    _write_ass_file,
)


class TestGroupWordsIntoLines:
    def test_basic_grouping(self):
        words = [
            WordTimestamp("hello", 0.0, 0.5),
            WordTimestamp("world", 0.5, 1.0),
            WordTimestamp("this", 1.0, 1.5),
            WordTimestamp("is", 1.5, 1.8),
            WordTimestamp("a", 1.8, 2.0),
            WordTimestamp("test", 2.0, 2.5),
        ]
        lines = _group_words_into_lines(words, max_words=3)
        assert len(lines) == 2
        assert lines[0].text == "hello world this"
        assert lines[1].text == "is a test"

    def test_single_word_per_line(self):
        words = [
            WordTimestamp("one", 0.0, 0.5),
            WordTimestamp("two", 0.5, 1.0),
        ]
        lines = _group_words_into_lines(words, max_words=1)
        assert len(lines) == 2
        assert lines[0].text == "one"
        assert lines[1].text == "two"

    def test_empty_words(self):
        lines = _group_words_into_lines([], max_words=5)
        assert lines == []

    def test_fewer_words_than_max(self):
        words = [WordTimestamp("hi", 0.0, 0.5)]
        lines = _group_words_into_lines(words, max_words=5)
        assert len(lines) == 1
        assert lines[0].text == "hi"

    def test_timing_preserved(self):
        words = [
            WordTimestamp("a", 1.0, 1.5),
            WordTimestamp("b", 2.0, 2.5),
            WordTimestamp("c", 3.0, 3.5),
        ]
        lines = _group_words_into_lines(words, max_words=2)
        assert lines[0].start == 1.0
        assert lines[0].end == 2.5
        assert lines[1].start == 3.0
        assert lines[1].end == 3.5


class TestFormatAssTime:
    def test_zero(self):
        assert _format_ass_time(0.0) == "0:00:00.00"

    def test_seconds(self):
        assert _format_ass_time(5.25) == "0:00:05.25"

    def test_minutes(self):
        assert _format_ass_time(65.5) == "0:01:05.50"

    def test_hours(self):
        assert _format_ass_time(3661.0) == "1:01:01.00"


class TestWriteAssFile:
    def test_creates_file(self, tmp_path):
        lines = [
            SubtitleLine(
                words=[
                    WordTimestamp("hello", 0.0, 0.5),
                    WordTimestamp("world", 0.5, 1.0),
                ],
                start=0.0,
                end=1.0,
                text="hello world",
            )
        ]
        cfg = Config()
        output = tmp_path / "test.ass"
        result = _write_ass_file(lines, cfg.subtitles, output, (1080, 1920))
        assert result.exists()
        content = result.read_text()
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content
        assert "Dialogue:" in content

    def test_karaoke_tags(self, tmp_path):
        lines = [
            SubtitleLine(
                words=[
                    WordTimestamp("hi", 0.0, 0.5),
                    WordTimestamp("there", 0.5, 1.2),
                ],
                start=0.0,
                end=1.2,
                text="hi there",
            )
        ]
        cfg = Config()
        output = tmp_path / "karaoke.ass"
        result = _write_ass_file(lines, cfg.subtitles, output, (1080, 1920))
        content = result.read_text()
        # Should contain \kf tags
        assert "\\kf" in content

    def test_empty_lines(self, tmp_path):
        cfg = Config()
        output = tmp_path / "empty.ass"
        result = _write_ass_file([], cfg.subtitles, output, (1080, 1920))
        assert result.exists()
        content = result.read_text()
        assert "Dialogue:" not in content


class TestGenerateSubtitleFile:
    def test_disabled_returns_none(self):
        from ugckit.subtitles import generate_subtitle_file

        cfg = Config()
        cfg.subtitles.enabled = False
        tl = Timeline(script_id="T", total_duration=0, entries=[])
        result = generate_subtitle_file(tl, [], cfg)
        assert result is None
