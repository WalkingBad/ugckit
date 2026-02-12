"""Auto-subtitle generation for UGCKit (Phase 4).

Transcribes avatar clips using Whisper, generates ASS subtitle files
with karaoke-style word highlighting.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ugckit.models import Config, SubtitleConfig, Timeline


@dataclass
class WordTimestamp:
    """A word with its absolute position in the final video timeline."""

    word: str
    start: float  # seconds from video start
    end: float


@dataclass
class SubtitleLine:
    """A line of subtitle text with timing."""

    words: list[WordTimestamp]
    start: float
    end: float
    text: str


def generate_subtitle_file(
    timeline: Timeline,
    avatar_clips: list[Path],
    config: Config,
) -> Optional[Path]:
    """Transcribe avatar clips and generate an ASS subtitle file.

    Returns:
        Path to generated .ass file, or None if subtitles are disabled.
    """
    sub_cfg = config.subtitles
    if not sub_cfg.enabled:
        return None

    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    words = _transcribe_all_clips(avatar_entries, avatar_clips, sub_cfg.whisper_model)
    if not words:
        return None

    lines = _group_words_into_lines(words, sub_cfg.max_words_per_line)
    if not lines:
        return None

    output_path = Path(tempfile.mktemp(suffix=".ass", prefix="ugckit_subs_"))
    return _write_ass_file(lines, sub_cfg, output_path, config.output.resolution)


def _transcribe_all_clips(
    avatar_entries: list,
    avatar_clips: list[Path],
    model_name: str,
) -> list[WordTimestamp]:
    """Transcribe each avatar clip, offset timestamps by clip start in timeline."""
    from ugckit.sync import transcribe_audio

    all_words: list[WordTimestamp] = []

    for i, entry in enumerate(avatar_entries):
        if i >= len(avatar_clips):
            break

        clip_path = avatar_clips[i]
        clip_offset = entry.start

        try:
            clip_words = transcribe_audio(clip_path, model_name)
        except Exception:
            continue

        for w in clip_words:
            all_words.append(
                WordTimestamp(
                    word=w.word,
                    start=clip_offset + w.start,
                    end=clip_offset + w.end,
                )
            )

    return all_words


def _group_words_into_lines(
    words: list[WordTimestamp],
    max_words: int,
) -> list[SubtitleLine]:
    """Group consecutive words into subtitle display lines."""
    if not words:
        return []

    lines: list[SubtitleLine] = []
    i = 0

    while i < len(words):
        chunk = words[i : i + max_words]
        text = " ".join(w.word for w in chunk)
        line = SubtitleLine(
            words=chunk,
            start=chunk[0].start,
            end=chunk[-1].end,
            text=text,
        )
        lines.append(line)
        i += max_words

    return lines


def _format_ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp: H:MM:SS.cc (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _write_ass_file(
    lines: list[SubtitleLine],
    config: SubtitleConfig,
    output_path: Path,
    resolution: tuple[int, int],
) -> Path:
    """Write an ASS subtitle file with karaoke \\k tags for word highlighting."""
    w, h = resolution
    margin_v = config.position_y

    header = f"""[Script Info]
Title: UGCKit Subtitles
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{config.font_name},{config.font_size},&H00FFFFFF,{config.highlight_color},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{config.outline_width},1,2,20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    for line in lines:
        start = _format_ass_time(line.start)
        end = _format_ass_time(line.end)

        # Build karaoke text with \k tags (centisecond durations)
        karaoke_parts = []
        for word in line.words:
            duration_cs = int((word.end - word.start) * 100)
            karaoke_parts.append(f"{{\\kf{duration_cs}}}{word.word}")

        text = "".join(karaoke_parts)
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    content = header + "\n".join(events) + "\n"
    output_path.write_text(content, encoding="utf-8")
    return output_path
