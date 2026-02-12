"""Tests for ugckit.parser."""

from __future__ import annotations

import pytest

from ugckit.parser import (
    CLIP_PATTERN,
    SAYS_PATTERN,
    SCREENCAST_PATTERN,
    estimate_duration,
    find_script_by_id,
    parse_markdown_file,
    parse_screencast_tags,
    parse_script_section,
    parse_scripts_directory,
)

# ── Regex patterns ──────────────────────────────────────────────────────


class TestClipPattern:
    """CLIP_PATTERN should capture clip number and optional duration."""

    @pytest.mark.parametrize(
        "text, expected_num, expected_dur",
        [
            ("**Clip 1 (8s):**", "1", "8"),
            ("**Clip 2 (VEO 8s):**", "2", "8"),
            ("**Clip 3 (Kling 12s):**", "3", "12"),
            ("**Clip 4 ():**", "4", None),
            ("**Clip 5 (close-up):**", "5", None),
            ("**Clip 6 (VEO):**", "6", None),
            ("**Clip 10 (slow-mo 6s):**", "10", "6"),
        ],
    )
    def test_match(self, text, expected_num, expected_dur):
        m = CLIP_PATTERN.search(text)
        assert m is not None, f"No match for: {text}"
        assert m.group(1) == expected_num
        assert m.group(2) == expected_dur

    def test_no_match_on_plain_text(self):
        assert CLIP_PATTERN.search("Just some text") is None

    def test_no_match_on_partial(self):
        assert CLIP_PATTERN.search("**Clip 1:**") is None  # no parens


class TestSaysPattern:
    def test_basic(self):
        m = SAYS_PATTERN.search('Says: "Hello world"')
        assert m and m.group(1) == "Hello world"

    def test_with_apostrophe(self):
        m = SAYS_PATTERN.search('Says: "It\'s a great day"')
        assert m and m.group(1) == "It's a great day"

    def test_multiline(self):
        m = SAYS_PATTERN.search('Says: "Line one\nline two"')
        assert m and "Line one" in m.group(1)


class TestScreencastPattern:
    def test_basic(self):
        m = SCREENCAST_PATTERN.search("[screencast: demo @ 1.5-5.0]")
        assert m
        assert m.group(1) == "demo"
        assert m.group(2) == "1.5"
        assert m.group(3) == "5.0"
        assert m.group(4) is None

    def test_with_mode(self):
        m = SCREENCAST_PATTERN.search("[screencast: screen.mp4 @ 2-6 mode:pip]")
        assert m
        assert m.group(1) == "screen.mp4"
        assert m.group(4) == "pip"


# ── Functions ───────────────────────────────────────────────────────────


class TestEstimateDuration:
    def test_basic(self):
        # 6 words / 3.0 wps = 2.0s
        assert estimate_duration("one two three four five six") == 2.0

    def test_empty(self):
        assert estimate_duration("") == 0.0

    def test_single_word(self):
        assert abs(estimate_duration("hello") - 1 / 3.0) < 0.01


class TestParseScreencastTags:
    def test_basic(self):
        result = parse_screencast_tags("[screencast: demo @ 1.5-5.0]")
        assert len(result) == 1
        assert result[0].file == "demo.mp4"
        assert result[0].start == 1.5
        assert result[0].end == 5.0

    def test_invalid_range_skipped(self):
        result = parse_screencast_tags("[screencast: demo @ 5.0-1.0]")
        assert len(result) == 0

    def test_multiple(self):
        text = "[screencast: a @ 1-3]\nSome text\n[screencast: b @ 4-8 mode:pip]"
        result = parse_screencast_tags(text)
        assert len(result) == 2

    def test_extension_preserved(self):
        result = parse_screencast_tags("[screencast: video.mp4 @ 0-5]")
        assert result[0].file == "video.mp4"


class TestParseScriptSection:
    def test_durations_from_header(self):
        content = """
**Clip 1 (8s):**
Says: "Test text"

**Clip 2 (12s):**
Says: "More text"
"""
        script = parse_script_section(content, "X1", "Test")
        assert len(script.segments) == 2
        assert script.segments[0].duration == 8.0
        assert script.segments[1].duration == 12.0

    def test_fallback_to_word_count(self):
        content = """
**Clip 1 ():**
Says: "Six words in this test sentence"
"""
        script = parse_script_section(content, "X2", "Test")
        assert len(script.segments) == 1
        assert script.segments[0].duration == 6 / 3.0  # 2.0s

    def test_character_extraction(self):
        content = """
**Character:** TestPerson

**Clip 1 (5s):**
Says: "Hello"
"""
        script = parse_script_section(content, "X3", "Test")
        assert script.character == "TestPerson"

    def test_skip_clip_without_says(self):
        content = """
**Clip 1 (8s):**
Says: "First"

**Clip 2 (8s):**
Just a description, no Says line

**Clip 3 (8s):**
Says: "Third"
"""
        script = parse_script_section(content, "X4", "Test")
        assert len(script.segments) == 2
        assert script.segments[0].id == 1
        assert script.segments[1].id == 3

    def test_total_duration(self):
        content = """
**Clip 1 (8s):**
Says: "First"

**Clip 2 (12s):**
Says: "Second"
"""
        script = parse_script_section(content, "X5", "Test")
        assert script.total_duration == 20.0

    def test_screencast_in_segment(self):
        content = """
**Clip 1 (8s):**
[screencast: app @ 2.0-6.0]
Says: "Check this"
"""
        script = parse_script_section(content, "X6", "Test")
        assert len(script.segments[0].screencasts) == 1
        assert script.segments[0].screencasts[0].file == "app.mp4"


class TestParseMarkdownFile:
    def test_single_script(self, sample_script_md):
        scripts = parse_markdown_file(sample_script_md)
        assert len(scripts) == 1
        assert scripts[0].script_id == "T1"
        assert scripts[0].title == "Test Script One"
        assert len(scripts[0].segments) == 3

    def test_multi_script(self, multi_script_md):
        scripts = parse_markdown_file(multi_script_md)
        assert len(scripts) == 2
        assert scripts[0].script_id == "A1"
        assert scripts[1].script_id == "A2"

    def test_durations_from_headers(self, sample_script_md):
        scripts = parse_markdown_file(sample_script_md)
        s = scripts[0]
        assert s.segments[0].duration == 8.0
        assert s.segments[1].duration == 12.0
        # Clip 3 has no duration in header -> word count fallback
        assert s.segments[2].duration < 8.0


class TestFindScriptById:
    def test_exact_match(self, sample_script_md):
        scripts = parse_markdown_file(sample_script_md)
        found = find_script_by_id(scripts, "T1")
        assert found is not None
        assert found.script_id == "T1"

    def test_case_insensitive(self, sample_script_md):
        scripts = parse_markdown_file(sample_script_md)
        assert find_script_by_id(scripts, "t1") is not None

    def test_not_found(self, sample_script_md):
        scripts = parse_markdown_file(sample_script_md)
        assert find_script_by_id(scripts, "ZZ99") is None


class TestParseScriptsDirectory:
    def test_finds_scripts(self, scripts_dir):
        scripts = parse_scripts_directory(scripts_dir)
        assert len(scripts) >= 1

    def test_empty_dir(self, tmp_dir):
        empty = tmp_dir / "empty"
        empty.mkdir()
        assert parse_scripts_directory(empty) == []


# ── Keyword screencast syntax (Phase 3) ─────────────────────────────────


class TestKeywordScreencastParsing:
    def test_keyword_syntax(self):
        text = '[screencast: app @ word:"check this out"-word:"and done" mode:pip]'
        result = parse_screencast_tags(text)
        assert len(result) == 1
        assert result[0].file == "app.mp4"
        assert result[0].start_keyword == "check this out"
        assert result[0].end_keyword == "and done"
        assert result[0].start == 0.0  # placeholder
        assert result[0].end == 0.0  # placeholder

    def test_keyword_overlay_mode(self):
        text = '[screencast: demo @ word:"look here"-word:"got it" mode:overlay]'
        result = parse_screencast_tags(text)
        assert len(result) == 1
        assert result[0].mode.value == "overlay"
        assert result[0].start_keyword == "look here"

    def test_keyword_no_mode(self):
        text = '[screencast: demo @ word:"start"-word:"end"]'
        result = parse_screencast_tags(text)
        assert len(result) == 1
        assert result[0].mode.value == "overlay"  # default

    def test_mixed_numeric_and_keyword(self):
        text = "[screencast: a @ 1.5-5.0]\n" '[screencast: b @ word:"check"-word:"done" mode:pip]'
        result = parse_screencast_tags(text)
        assert len(result) == 2
        # First is numeric
        assert result[0].start == 0.0  # keyword comes first in results
        assert result[0].start_keyword == "check"
        # Second is numeric
        assert result[1].start == 1.5
        assert result[1].start_keyword is None

    def test_keyword_with_extension(self):
        text = '[screencast: app.mp4 @ word:"a"-word:"b"]'
        result = parse_screencast_tags(text)
        assert len(result) == 1
        assert result[0].file == "app.mp4"
