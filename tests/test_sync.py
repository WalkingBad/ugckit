"""Tests for ugckit.sync."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from ugckit.models import CompositionMode, ScreencastOverlay, Script, Segment
from ugckit.sync import (
    SyncError,
    WordTimestamp,
    match_keyword_timing,
    sync_screencast_timing,
)

# ── Unit tests ──────────────────────────────────────────────────────────


class TestWordTimestamp:
    def test_creation(self):
        wt = WordTimestamp(word="hello", start=1.0, end=1.5)
        assert wt.word == "hello"
        assert wt.start == 1.0
        assert wt.end == 1.5


class TestMatchKeywordTiming:
    def test_single_word_match(self):
        transcript = [
            WordTimestamp(word="hey", start=0.0, end=0.3),
            WordTimestamp(word="check", start=0.5, end=0.8),
            WordTimestamp(word="this", start=0.9, end=1.1),
            WordTimestamp(word="out", start=1.2, end=1.4),
        ]
        result = match_keyword_timing(transcript, "check")
        assert result == 0.5

    def test_multi_word_match(self):
        transcript = [
            WordTimestamp(word="hey", start=0.0, end=0.3),
            WordTimestamp(word="check", start=0.5, end=0.8),
            WordTimestamp(word="this", start=0.9, end=1.1),
            WordTimestamp(word="out", start=1.2, end=1.4),
        ]
        result = match_keyword_timing(transcript, "check this out")
        assert result == 0.5

    def test_no_match(self):
        transcript = [
            WordTimestamp(word="hello", start=0.0, end=0.5),
            WordTimestamp(word="world", start=0.6, end=1.0),
        ]
        result = match_keyword_timing(transcript, "goodbye")
        assert result is None

    def test_empty_transcript(self):
        result = match_keyword_timing([], "hello")
        assert result is None

    def test_empty_keyword(self):
        transcript = [WordTimestamp(word="hello", start=0.0, end=0.5)]
        result = match_keyword_timing(transcript, "")
        assert result is None

    def test_case_insensitive(self):
        transcript = [
            WordTimestamp(word="Check", start=0.5, end=0.8),
            WordTimestamp(word="This", start=0.9, end=1.1),
        ]
        result = match_keyword_timing(transcript, "check this")
        assert result == 0.5

    def test_punctuation_handling(self):
        transcript = [
            WordTimestamp(word="hello,", start=0.0, end=0.3),
            WordTimestamp(word="world!", start=0.4, end=0.8),
        ]
        result = match_keyword_timing(transcript, "hello")
        assert result == 0.0

    def test_fuzzy_substring_match(self):
        transcript = [
            WordTimestamp(word="checking", start=0.5, end=0.8),
        ]
        result = match_keyword_timing(transcript, "check")
        assert result == 0.5


class TestSyncScreencastTiming:
    def _make_script_with_keywords(self) -> Script:
        return Script(
            script_id="T1",
            title="Test",
            total_duration=16.0,
            segments=[
                Segment(
                    id=1,
                    text="First segment",
                    duration=8.0,
                    screencasts=[
                        ScreencastOverlay(
                            file="app.mp4",
                            start=0.0,
                            end=0.0,
                            mode=CompositionMode.OVERLAY,
                            start_keyword="check this out",
                            end_keyword="and that's it",
                        )
                    ],
                ),
                Segment(id=2, text="Second segment", duration=8.0, screencasts=[]),
            ],
        )

    def _make_script_without_keywords(self) -> Script:
        return Script(
            script_id="T1",
            title="Test",
            total_duration=8.0,
            segments=[
                Segment(
                    id=1,
                    text="First segment",
                    duration=8.0,
                    screencasts=[
                        ScreencastOverlay(
                            file="app.mp4",
                            start=1.5,
                            end=5.0,
                        )
                    ],
                ),
            ],
        )

    @patch("ugckit.sync.transcribe_audio")
    def test_resolves_keyword_timing(self, mock_transcribe, tmp_path):
        mock_transcribe.return_value = [
            WordTimestamp(word="hey", start=0.0, end=0.3),
            WordTimestamp(word="check", start=2.0, end=2.3),
            WordTimestamp(word="this", start=2.4, end=2.6),
            WordTimestamp(word="out", start=2.7, end=2.9),
            WordTimestamp(word="cool", start=3.0, end=3.3),
            WordTimestamp(word="and", start=5.0, end=5.2),
            WordTimestamp(word="that's", start=5.3, end=5.6),
            WordTimestamp(word="it", start=5.7, end=5.9),
        ]

        script = self._make_script_with_keywords()
        clip = tmp_path / "avatar.mp4"
        clip.touch()

        result = sync_screencast_timing(script, [clip, clip])

        sc = result.segments[0].screencasts[0]
        assert sc.start == 2.0  # "check this out" starts at 2.0
        assert sc.end == 5.0  # "and that's it" starts at 5.0

    @patch("ugckit.sync.transcribe_audio")
    def test_no_keywords_unchanged(self, mock_transcribe, tmp_path):
        script = self._make_script_without_keywords()
        clip = tmp_path / "avatar.mp4"
        clip.touch()

        result = sync_screencast_timing(script, [clip])

        # Should not call transcribe at all
        mock_transcribe.assert_not_called()

        sc = result.segments[0].screencasts[0]
        assert sc.start == 1.5
        assert sc.end == 5.0

    @patch("ugckit.sync.transcribe_audio")
    def test_missing_keyword_keeps_original(self, mock_transcribe, tmp_path):
        mock_transcribe.return_value = [
            WordTimestamp(word="unrelated", start=0.0, end=0.5),
            WordTimestamp(word="words", start=0.6, end=1.0),
        ]

        script = self._make_script_with_keywords()
        clip = tmp_path / "avatar.mp4"
        clip.touch()

        result = sync_screencast_timing(script, [clip, clip])

        sc = result.segments[0].screencasts[0]
        # start_keyword not found, uses original 0.0
        assert sc.start == 0.0

    @patch("ugckit.sync.transcribe_audio", side_effect=SyncError("no whisper"))
    def test_sync_error_returns_original(self, mock_transcribe, tmp_path):
        script = self._make_script_with_keywords()
        clip = tmp_path / "avatar.mp4"
        clip.touch()

        result = sync_screencast_timing(script, [clip, clip])

        # Should return original script unchanged
        sc = result.segments[0].screencasts[0]
        assert sc.start == 0.0
        assert sc.end == 0.0

    def test_transcribe_requires_whisper(self, tmp_path):
        from ugckit.sync import transcribe_audio

        with pytest.raises(SyncError, match="openai-whisper"):
            transcribe_audio(tmp_path / "dummy.mp4")
