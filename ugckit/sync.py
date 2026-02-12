"""Smart Sync module for UGCKit (Phase 3).

Uses Whisper for speech-to-text with word-level timestamps,
then matches keyword triggers to actual spoken timing.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ugckit.models import ScreencastOverlay, Script


@dataclass
class WordTimestamp:
    """A single word with its timing in the audio."""

    word: str
    start: float  # seconds
    end: float  # seconds


class SyncError(Exception):
    """Error during sync processing."""

    pass


def transcribe_audio(
    video_path: Path,
    model_name: str = "base",
) -> list[WordTimestamp]:
    """Run Whisper on video audio, return word-level timestamps.

    Args:
        video_path: Path to video file.
        model_name: Whisper model size (tiny, base, small, medium, large).

    Returns:
        List of WordTimestamp with per-word timing.

    Raises:
        SyncError: If Whisper fails or is not installed.
    """
    try:
        import whisper
    except ImportError:
        raise SyncError("Smart Sync requires openai-whisper: pip install openai-whisper")

    # Extract audio to temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise SyncError(f"Audio extraction failed: {result.stderr[:300]}")

        model = whisper.load_model(model_name)
        result = model.transcribe(
            str(wav_path),
            word_timestamps=True,
            language=None,  # auto-detect
        )

        timestamps = []
        for segment in result.get("segments", []):
            for word_info in segment.get("words", []):
                timestamps.append(
                    WordTimestamp(
                        word=word_info["word"].strip().lower(),
                        start=word_info["start"],
                        end=word_info["end"],
                    )
                )

        return timestamps
    finally:
        wav_path.unlink(missing_ok=True)


def match_keyword_timing(
    transcript: list[WordTimestamp],
    keyword: str,
) -> Optional[float]:
    """Find timestamp when a keyword phrase is spoken.

    Supports multi-word phrases by matching consecutive words.

    Args:
        transcript: List of word timestamps from Whisper.
        keyword: Keyword or phrase to find (case-insensitive).

    Returns:
        Start time in seconds when keyword is spoken, or None if not found.
    """
    keyword_words = keyword.lower().split()
    if not keyword_words or not transcript:
        return None

    for i in range(len(transcript) - len(keyword_words) + 1):
        match = True
        for j, kw in enumerate(keyword_words):
            # Fuzzy match: transcript word contains the keyword word
            t_word = transcript[i + j].word.strip(".,!?;:'\"").lower()
            if t_word != kw and kw not in t_word:
                match = False
                break
        if match:
            return transcript[i].start

    return None


def sync_screencast_timing(
    script: Script,
    avatar_clips: list[Path],
    model_name: str = "base",
) -> Script:
    """Replace keyword-based screencast timing with actual timestamps from speech.

    For each segment with keyword-triggered screencasts, runs Whisper on the
    corresponding avatar clip and resolves keyword timestamps.

    Args:
        script: Parsed script with keyword-based screencasts.
        avatar_clips: Avatar video files (one per segment).
        model_name: Whisper model size.

    Returns:
        New Script with resolved screencast timings.
    """
    # Cache transcripts per clip
    transcripts: dict[str, list[WordTimestamp]] = {}
    updated_segments = []

    for i, segment in enumerate(script.segments):
        has_keywords = any(sc.start_keyword or sc.end_keyword for sc in segment.screencasts)

        if not has_keywords or i >= len(avatar_clips):
            updated_segments.append(segment)
            continue

        # Transcribe this avatar clip
        clip_path = avatar_clips[i]
        clip_key = str(clip_path)

        if clip_key not in transcripts:
            try:
                transcripts[clip_key] = transcribe_audio(clip_path, model_name)
            except SyncError:
                updated_segments.append(segment)
                continue

        transcript = transcripts[clip_key]

        # Resolve keyword timing for each screencast
        updated_screencasts = []
        for sc in segment.screencasts:
            new_start = sc.start
            new_end = sc.end

            if sc.start_keyword:
                matched_time = match_keyword_timing(transcript, sc.start_keyword)
                if matched_time is not None:
                    new_start = matched_time

            if sc.end_keyword:
                matched_time = match_keyword_timing(transcript, sc.end_keyword)
                if matched_time is not None:
                    new_end = matched_time

            # Ensure end > start
            if new_end <= new_start:
                new_end = new_start + (sc.end - sc.start)

            updated_screencasts.append(
                ScreencastOverlay(
                    file=sc.file,
                    start=new_start,
                    end=new_end,
                    mode=sc.mode,
                    start_keyword=sc.start_keyword,
                    end_keyword=sc.end_keyword,
                )
            )

        updated_segments.append(segment.model_copy(update={"screencasts": updated_screencasts}))

    return script.model_copy(update={"segments": updated_segments})
