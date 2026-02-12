"""FFmpeg video composition for UGCKit.

Handles video assembly using FFmpeg filter_complex.
"""

from __future__ import annotations

import shlex
import subprocess
import warnings
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

from ugckit.models import (
    CompositionMode,
    Config,
    Position,
    Script,
    Timeline,
    TimelineEntry,
)


class FFmpegError(Exception):
    """FFmpeg/ffprobe execution error."""

    pass


def get_video_duration(video_path: Path) -> float:
    """Get duration of a video file using ffprobe.

    Args:
        video_path: Path to video file.

    Returns:
        Duration in seconds.

    Raises:
        FFmpegError: If ffprobe fails or returns invalid data.
    """
    if not video_path.exists():
        raise FFmpegError(f"Video file not found: {video_path}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise FFmpegError(f"ffprobe timed out for {video_path}")

    if result.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {video_path}: {result.stderr}")

    try:
        return float(result.stdout.strip())
    except ValueError as e:
        raise FFmpegError(f"Invalid duration from ffprobe for {video_path}: {result.stdout}") from e


def has_audio_stream(video_path: Path) -> bool:
    """Check if video file has an audio stream.

    Args:
        video_path: Path to video file.

    Returns:
        True if audio stream exists.

    Raises:
        FFmpegError: If ffprobe fails.
    """
    if not video_path.exists():
        raise FFmpegError(f"Video file not found: {video_path}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise FFmpegError(f"ffprobe timed out for {video_path}")

    if result.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {video_path}: {result.stderr}")

    return bool(result.stdout.strip())


def build_timeline(
    script: Script,
    avatar_clips: List[Path],
    screencasts_dir: Path,
    output_path: Path,
) -> Timeline:
    """Build composition timeline from script and avatar clips.

    Args:
        script: Parsed script.
        avatar_clips: List of avatar video files (one per segment).
        screencasts_dir: Directory containing screencast files.
        output_path: Output video path.

    Returns:
        Timeline object with all entries.

    Raises:
        ValueError: If avatar_clips is empty.
        FFmpegError: If video file is missing or invalid.
    """
    if not avatar_clips:
        raise ValueError("avatar_clips cannot be empty")

    entries: List[TimelineEntry] = []
    current_time = 0.0

    for i, segment in enumerate(script.segments):
        if i >= len(avatar_clips):
            break

        avatar_clip = avatar_clips[i]

        # Get actual duration from video file
        duration = get_video_duration(avatar_clip)

        # Add avatar entry
        entries.append(
            TimelineEntry(
                start=current_time,
                end=current_time + duration,
                type="avatar",
                file=avatar_clip,
                parent_segment=segment.id,
            )
        )

        # Add screencast entries
        for sc in segment.screencasts:
            sc_path = screencasts_dir / sc.file
            if sc_path.exists():
                sc_end = min(current_time + sc.end, current_time + duration)
                entries.append(
                    TimelineEntry(
                        start=current_time + sc.start,
                        end=sc_end,
                        type="screencast",
                        file=sc_path,
                        parent_segment=segment.id,
                        composition_mode=sc.mode,
                    )
                )
            else:
                warnings.warn(f"Screencast not found: {sc_path}", stacklevel=2)

        current_time += duration

    return Timeline(
        script_id=script.script_id,
        total_duration=current_time,
        entries=entries,
        output_path=output_path,
    )


def format_timeline(timeline: Timeline) -> str:
    """Format timeline for display.

    Args:
        timeline: Timeline to format.

    Returns:
        Formatted string representation.
    """
    lines = [
        f"Timeline for {timeline.script_id} (total: {timeline.total_duration:.1f}s):",
        "━" * 50,
    ]

    for entry in timeline.entries:
        indent = "  " if entry.type == "avatar" else "  └─ "
        type_str = entry.type
        file_str = entry.file.name
        time_str = f"{entry.start:5.1f}s - {entry.end:5.1f}s"

        lines.append(f"{time_str} │ {indent}{type_str}: {file_str}")

    lines.append("━" * 50)
    if timeline.output_path:
        lines.append(f"Output: {timeline.output_path}")

    return "\n".join(lines)


def position_to_overlay_coords(
    position: Position,
    margin: int,
    overlay_width: str = "overlay_w",
    overlay_height: str = "overlay_h",
) -> Tuple[str, str]:
    """Convert position enum to FFmpeg overlay coordinates.

    Args:
        position: Corner position.
        margin: Margin from edge in pixels.
        overlay_width: Variable name for overlay width.
        overlay_height: Variable name for overlay height.

    Returns:
        Tuple of (x, y) coordinate expressions.
    """
    if position == Position.TOP_LEFT:
        return (str(margin), str(margin))
    elif position == Position.TOP_RIGHT:
        return (f"W-{overlay_width}-{margin}", str(margin))
    elif position == Position.BOTTOM_LEFT:
        return (str(margin), f"H-{overlay_height}-{margin}")
    else:  # BOTTOM_RIGHT
        return (f"W-{overlay_width}-{margin}", f"H-{overlay_height}-{margin}")


def build_ffmpeg_filter_overlay(
    timeline: Timeline,
    config: Config,
    audio_presence: Optional[List[bool]] = None,
) -> str:
    """Build FFmpeg filter_complex string for overlay mode.

    Args:
        timeline: Composition timeline.
        config: UGCKit configuration.
        audio_presence: Per-clip audio presence flags.

    Returns:
        FFmpeg filter_complex string.
    """
    filters = []
    overlay_cfg = config.composition.overlay
    output_cfg = config.output

    # Count inputs
    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    screencast_entries = [e for e in timeline.entries if e.type == "screencast"]
    if audio_presence is None:
        audio_presence = [True] * len(avatar_entries)
    if len(audio_presence) != len(avatar_entries):
        raise ValueError("audio_presence length must match avatar entries")

    # Scale avatars to output resolution
    for i, _ in enumerate(avatar_entries):
        filters.append(
            f"[{i}:v]scale={output_cfg.resolution[0]}:{output_cfg.resolution[1]},"
            f"setsar=1[av{i}]"
        )

    # Concatenate avatars
    if len(avatar_entries) > 1:
        concat_inputs = "".join(f"[av{i}]" for i in range(len(avatar_entries)))
        filters.append(f"{concat_inputs}concat=n={len(avatar_entries)}:v=1:a=0[base]")
    else:
        filters.append("[av0]copy[base]")

    # Build audio timeline per clip
    audio_labels = []
    for i, has_audio in enumerate(audio_presence):
        label = f"a{i}"
        if has_audio:
            filters.append(f"[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[{label}]")
        else:
            duration = avatar_entries[i].end - avatar_entries[i].start
            filters.append(
                f"anullsrc=r=48000:cl=stereo,atrim=0:{duration:.2f},"
                f"asetpts=PTS-STARTPTS[{label}]"
            )
        audio_labels.append(f"[{label}]")

    if len(audio_labels) > 1:
        filters.append(f"{''.join(audio_labels)}concat=n={len(audio_labels)}:v=0:a=1[audio]")
    elif len(audio_labels) == 1:
        filters.append(f"{audio_labels[0]}anull[audio]")
    else:
        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{timeline.total_duration:.2f}[audio]")

    # Apply screencast overlays
    current_base = "base"
    sc_input_offset = len(avatar_entries)

    for i, sc_entry in enumerate(screencast_entries):
        sc_idx = sc_input_offset + i
        next_base = f"out{i}"

        # Scale screencast
        scale_w = int(output_cfg.resolution[0] * overlay_cfg.scale)
        filters.append(f"[{sc_idx}:v]scale={scale_w}:-1[sc{i}]")

        # Get position coordinates
        x, y = position_to_overlay_coords(
            overlay_cfg.position,
            overlay_cfg.margin,
            "w",
            "h",
        )

        # Overlay with timing
        enable = f"between(t,{sc_entry.start:.2f},{sc_entry.end:.2f})"
        filters.append(f"[{current_base}][sc{i}]overlay=x={x}:y={y}:enable='{enable}'[{next_base}]")
        current_base = next_base

    # Final output
    if screencast_entries:
        filters.append(f"[{current_base}]null[vout]")
    else:
        filters.append("[base]null[vout]")

    # Audio normalization
    if config.audio.normalize:
        filters.append(f"[audio]loudnorm=I={config.audio.target_loudness}:TP=-1.5:LRA=11[aout]")
    else:
        filters.append("[audio]anull[aout]")

    return ";".join(filters)


def build_ffmpeg_filter_pip(
    timeline: Timeline,
    config: Config,
    audio_presence: Optional[List[bool]] = None,
    head_videos: Optional[List[Path]] = None,
) -> str:
    """Build FFmpeg filter_complex string for PiP mode.

    In PiP mode: screencast goes fullscreen as overlay, head video in corner.

    Args:
        timeline: Composition timeline.
        config: UGCKit configuration.
        audio_presence: Per-clip audio presence flags.
        head_videos: Pre-processed head video files (one per avatar clip).

    Returns:
        FFmpeg filter_complex string.
    """

    filters = []
    output_cfg = config.output
    pip_cfg = config.composition.pip

    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    screencast_entries = [e for e in timeline.entries if e.type == "screencast"]
    pip_screencasts = [e for e in screencast_entries if e.composition_mode == CompositionMode.PIP]
    overlay_screencasts = [
        e for e in screencast_entries if e.composition_mode != CompositionMode.PIP
    ]

    if audio_presence is None:
        audio_presence = [True] * len(avatar_entries)
    if len(audio_presence) != len(avatar_entries):
        raise ValueError("audio_presence length must match avatar entries")

    # Input layout:
    # [0..n-1]: avatar clips
    # [n..n+sc-1]: screencast clips
    # [n+sc..]: head videos (if provided)
    num_avatars = len(avatar_entries)
    num_screencasts = len(screencast_entries)
    head_input_offset = num_avatars + num_screencasts

    # Scale avatars to output resolution
    for i in range(num_avatars):
        filters.append(
            f"[{i}:v]scale={output_cfg.resolution[0]}:{output_cfg.resolution[1]},"
            f"setsar=1[av{i}]"
        )

    # Concatenate avatars
    if num_avatars > 1:
        concat_inputs = "".join(f"[av{i}]" for i in range(num_avatars))
        filters.append(f"{concat_inputs}concat=n={num_avatars}:v=1:a=0[base]")
    else:
        filters.append("[av0]copy[base]")

    # Build audio timeline (same as overlay mode - audio from avatars)
    audio_labels = []
    for i, has_audio in enumerate(audio_presence):
        label = f"a{i}"
        if has_audio:
            filters.append(f"[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[{label}]")
        else:
            duration = avatar_entries[i].end - avatar_entries[i].start
            filters.append(
                f"anullsrc=r=48000:cl=stereo,atrim=0:{duration:.2f},"
                f"asetpts=PTS-STARTPTS[{label}]"
            )
        audio_labels.append(f"[{label}]")

    if len(audio_labels) > 1:
        filters.append(f"{''.join(audio_labels)}concat=n={len(audio_labels)}:v=0:a=1[audio]")
    elif len(audio_labels) == 1:
        filters.append(f"{audio_labels[0]}anull[audio]")
    else:
        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{timeline.total_duration:.2f}[audio]")

    current_base = "base"

    # Apply overlay-mode screencasts (same as before)
    overlay_cfg = config.composition.overlay
    for i, sc_entry in enumerate(overlay_screencasts):
        # Find this screencast's input index
        sc_idx = num_avatars + screencast_entries.index(sc_entry)
        next_base = f"ov{i}"

        scale_w = int(output_cfg.resolution[0] * overlay_cfg.scale)
        filters.append(f"[{sc_idx}:v]scale={scale_w}:-1[osc{i}]")

        x, y = position_to_overlay_coords(overlay_cfg.position, overlay_cfg.margin, "w", "h")
        enable = f"between(t,{sc_entry.start:.2f},{sc_entry.end:.2f})"
        filters.append(
            f"[{current_base}][osc{i}]overlay=x={x}:y={y}:enable='{enable}'[{next_base}]"
        )
        current_base = next_base

    # Apply PiP screencasts (screencast fullscreen, head in corner)
    for i, sc_entry in enumerate(pip_screencasts):
        sc_idx = num_avatars + screencast_entries.index(sc_entry)

        # Scale screencast to fullscreen
        next_base_sc = f"pip_sc{i}"
        filters.append(
            f"[{sc_idx}:v]scale={output_cfg.resolution[0]}:{output_cfg.resolution[1]},"
            f"setsar=1[psc{i}]"
        )

        # Overlay fullscreen screencast on base
        enable = f"between(t,{sc_entry.start:.2f},{sc_entry.end:.2f})"
        filters.append(f"[{current_base}][psc{i}]overlay=0:0:enable='{enable}'[{next_base_sc}]")
        current_base = next_base_sc

        # Overlay head video in corner (if head videos provided)
        if head_videos:
            # Find which avatar this screencast belongs to
            seg_id = sc_entry.parent_segment
            avatar_idx = None
            for ai, ae in enumerate(avatar_entries):
                if ae.parent_segment == seg_id:
                    avatar_idx = ai
                    break

            if avatar_idx is not None and avatar_idx < len(head_videos):
                head_idx = head_input_offset + avatar_idx
                next_base_head = f"pip_h{i}"

                x, y = position_to_overlay_coords(
                    pip_cfg.head_position, pip_cfg.head_margin, "w", "h"
                )
                filters.append(
                    f"[{current_base}][{head_idx}:v]overlay=x={x}:y={y}:"
                    f"enable='{enable}'[{next_base_head}]"
                )
                current_base = next_base_head

    # Final output
    filters.append(f"[{current_base}]null[vout]")

    # Audio normalization
    if config.audio.normalize:
        filters.append(f"[audio]loudnorm=I={config.audio.target_loudness}:TP=-1.5:LRA=11[aout]")
    else:
        filters.append("[audio]anull[aout]")

    return ";".join(filters)


def _build_audio_pipeline(
    filters: list,
    avatar_entries: list,
    audio_presence: List[bool],
    timeline_total_duration: float,
) -> None:
    """Build audio concat pipeline (shared across all modes)."""
    audio_labels = []
    for i, has_audio in enumerate(audio_presence):
        label = f"a{i}"
        if has_audio:
            filters.append(f"[{i}:a]aresample=48000,asetpts=PTS-STARTPTS[{label}]")
        else:
            duration = avatar_entries[i].end - avatar_entries[i].start
            filters.append(
                f"anullsrc=r=48000:cl=stereo,atrim=0:{duration:.2f},"
                f"asetpts=PTS-STARTPTS[{label}]"
            )
        audio_labels.append(f"[{label}]")

    if len(audio_labels) > 1:
        filters.append(f"{''.join(audio_labels)}concat=n={len(audio_labels)}:v=0:a=1[audio]")
    elif len(audio_labels) == 1:
        filters.append(f"{audio_labels[0]}anull[audio]")
    else:
        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{timeline_total_duration:.2f}[audio]")


def build_ffmpeg_filter_split(
    timeline: Timeline,
    config: Config,
    audio_presence: Optional[List[bool]] = None,
) -> str:
    """Build FFmpeg filter_complex string for split screen mode.

    Avatar on one side, screencast on the other (50/50 by default).
    """
    filters = []
    output_cfg = config.output
    split_cfg = config.composition.split

    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    screencast_entries = [e for e in timeline.entries if e.type == "screencast"]
    if audio_presence is None:
        audio_presence = [True] * len(avatar_entries)
    if len(audio_presence) != len(avatar_entries):
        raise ValueError("audio_presence length must match avatar entries")

    w, h = output_cfg.resolution
    avatar_w = int(w * split_cfg.split_ratio)
    sc_w = w - avatar_w

    # Scale avatars to output resolution
    for i in range(len(avatar_entries)):
        filters.append(f"[{i}:v]scale={w}:{h},setsar=1[av{i}]")

    # Concatenate avatars
    if len(avatar_entries) > 1:
        concat_inputs = "".join(f"[av{i}]" for i in range(len(avatar_entries)))
        filters.append(f"{concat_inputs}concat=n={len(avatar_entries)}:v=1:a=0[base]")
    else:
        filters.append("[av0]copy[base]")

    # Audio
    _build_audio_pipeline(filters, avatar_entries, audio_presence, timeline.total_duration)

    # Apply split screen overlays
    current_base = "base"
    sc_input_offset = len(avatar_entries)

    for i, sc_entry in enumerate(screencast_entries):
        sc_idx = sc_input_offset + i
        next_base = f"split_{i}"

        # Split current base into two: one for crop, one for overlay
        crop_label = f"{current_base}_crop{i}"
        ov_label = f"{current_base}_ov{i}"
        filters.append(f"[{current_base}]split=2[{crop_label}][{ov_label}]")

        # Crop avatar to left/right portion and scale screencast to remaining
        if split_cfg.avatar_side == "left":
            filters.append(f"[{crop_label}]crop={avatar_w}:{h}:0:0[left_{i}]")
            filters.append(f"[{sc_idx}:v]scale={sc_w}:{h},setsar=1[right_{i}]")
            filters.append(f"[left_{i}][right_{i}]hstack=inputs=2[hs_{i}]")
        else:
            filters.append(f"[{crop_label}]crop={avatar_w}:{h}:{w - avatar_w}:0[right_{i}]")
            filters.append(f"[{sc_idx}:v]scale={sc_w}:{h},setsar=1[left_{i}]")
            filters.append(f"[left_{i}][right_{i}]hstack=inputs=2[hs_{i}]")

        # Overlay hstacked frame on base with timing
        enable = f"between(t,{sc_entry.start:.2f},{sc_entry.end:.2f})"
        filters.append(f"[{ov_label}][hs_{i}]overlay=0:0:enable='{enable}'[{next_base}]")
        current_base = next_base

    # Final output
    if screencast_entries:
        filters.append(f"[{current_base}]null[vout]")
    else:
        filters.append("[base]null[vout]")

    # Audio normalization
    if config.audio.normalize:
        filters.append(f"[audio]loudnorm=I={config.audio.target_loudness}:TP=-1.5:LRA=11[aout]")
    else:
        filters.append("[audio]anull[aout]")

    return ";".join(filters)


def build_ffmpeg_filter_greenscreen(
    timeline: Timeline,
    config: Config,
    audio_presence: Optional[List[bool]] = None,
    transparent_avatars: Optional[List[Path]] = None,
) -> str:
    """Build FFmpeg filter_complex string for green screen mode.

    Screencast as fullscreen background, transparent avatar overlay.
    """
    filters = []
    output_cfg = config.output
    gs_cfg = config.composition.greenscreen

    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    screencast_entries = [e for e in timeline.entries if e.type == "screencast"]
    if audio_presence is None:
        audio_presence = [True] * len(avatar_entries)
    if len(audio_presence) != len(avatar_entries):
        raise ValueError("audio_presence length must match avatar entries")

    w, h = output_cfg.resolution
    num_avatars = len(avatar_entries)
    num_screencasts = len(screencast_entries)
    # Input layout: avatars, screencasts, transparent_avatars
    ta_input_offset = num_avatars + num_screencasts

    # Scale avatars to output resolution (used when no screencast active)
    for i in range(num_avatars):
        filters.append(f"[{i}:v]scale={w}:{h},setsar=1[av{i}]")

    # Concatenate avatars
    if num_avatars > 1:
        concat_inputs = "".join(f"[av{i}]" for i in range(num_avatars))
        filters.append(f"{concat_inputs}concat=n={num_avatars}:v=1:a=0[base]")
    else:
        filters.append("[av0]copy[base]")

    # Audio
    _build_audio_pipeline(filters, avatar_entries, audio_presence, timeline.total_duration)

    current_base = "base"

    for i, sc_entry in enumerate(screencast_entries):
        sc_idx = num_avatars + i
        enable = f"between(t,{sc_entry.start:.2f},{sc_entry.end:.2f})"

        # Fullscreen screencast as background
        filters.append(f"[{sc_idx}:v]scale={w}:{h},setsar=1[bg_{i}]")
        next_base_sc = f"sc_base_{i}"
        filters.append(f"[{current_base}][bg_{i}]overlay=0:0:enable='{enable}'[{next_base_sc}]")
        current_base = next_base_sc

        # Overlay transparent avatar
        if transparent_avatars:
            seg_id = sc_entry.parent_segment
            avatar_idx = None
            for ai, ae in enumerate(avatar_entries):
                if ae.parent_segment == seg_id:
                    avatar_idx = ai
                    break

            if avatar_idx is not None and avatar_idx < len(transparent_avatars):
                ta_idx = ta_input_offset + avatar_idx
                avatar_w = int(w * gs_cfg.avatar_scale)

                x, y = position_to_overlay_coords(
                    gs_cfg.avatar_position, gs_cfg.avatar_margin, "w", "h"
                )
                next_base_ta = f"gs_{i}"
                filters.append(f"[{ta_idx}:v]scale={avatar_w}:-1[ta_{i}]")
                filters.append(
                    f"[{current_base}][ta_{i}]overlay=x={x}:y={y}:"
                    f"enable='{enable}'[{next_base_ta}]"
                )
                current_base = next_base_ta

    # Final output
    filters.append(f"[{current_base}]null[vout]")

    # Audio normalization
    if config.audio.normalize:
        filters.append(f"[audio]loudnorm=I={config.audio.target_loudness}:TP=-1.5:LRA=11[aout]")
    else:
        filters.append("[audio]anull[aout]")

    return ";".join(filters)


def wrap_with_post_processing(
    filter_complex: str,
    subtitle_file: Optional[Path] = None,
    music_input_index: Optional[int] = None,
    music_config: Optional[MusicConfig] = None,
    total_duration: float = 0.0,
) -> str:
    """Wrap a filter_complex with subtitle and music post-processing.

    Renames [vout]/[aout] to intermediate labels, then applies subtitle
    overlay and/or music mixing as needed.
    """
    has_subs = subtitle_file is not None
    has_music = music_input_index is not None and music_config is not None

    if not has_subs and not has_music:
        return filter_complex

    parts = filter_complex

    if has_subs:
        # Rename [vout] -> [vout_pre], apply ASS subtitles -> [vout]
        parts = parts.replace("[vout]", "[vout_pre]", 1)
        # Escape path for ASS filter (colons, backslashes)
        ass_path = str(subtitle_file).replace("\\", "\\\\").replace(":", "\\:")
        parts += f";[vout_pre]ass='{ass_path}'[vout]"

    if has_music:
        # Rename [aout] -> [aout_pre], mix with music -> [aout]
        parts = parts.replace("[aout]", "[aout_pre]", 1)
        dur = total_duration
        fade_dur = music_config.fade_out_duration
        fade_start = max(0.0, dur - fade_dur)
        vol = music_config.volume

        if music_config.loop:
            parts += (
                f";[{music_input_index}:a]aloop=loop=-1:size=2e+09,"
                f"atrim=0:{dur:.2f},asetpts=PTS-STARTPTS[music_loop]"
            )
        else:
            parts += (
                f";[{music_input_index}:a]atrim=0:{dur:.2f}," f"asetpts=PTS-STARTPTS[music_loop]"
            )

        parts += (
            f";[music_loop]afade=t=out:st={fade_start:.2f}:d={fade_dur:.2f}[music_faded]"
            f";[aout_pre][music_faded]amix=inputs=2:duration=first:"
            f"weights=1 {vol:.2f}[aout]"
        )

    return parts


def _detect_composition_mode(timeline: Timeline) -> CompositionMode:
    """Detect the composition mode from timeline screencast entries."""
    modes = {e.composition_mode for e in timeline.entries if e.type == "screencast"}
    for m in [CompositionMode.GREENSCREEN, CompositionMode.PIP, CompositionMode.SPLIT]:
        if m in modes:
            return m
    return CompositionMode.OVERLAY


def validate_timeline_files(timeline: Timeline) -> None:
    """Validate all files in timeline exist.

    Args:
        timeline: Timeline to validate.

    Raises:
        FFmpegError: If any file is missing.
    """
    missing = []
    for entry in timeline.entries:
        if not entry.file.exists():
            missing.append(str(entry.file))

    if missing:
        raise FFmpegError(f"Missing files: {', '.join(missing)}")


def _timeline_has_pip(timeline: Timeline) -> bool:
    """Check if timeline has any PiP mode screencasts (legacy helper)."""
    return _detect_composition_mode(timeline) == CompositionMode.PIP


def compose_video(
    timeline: Timeline,
    config: Config,
    dry_run: bool = False,
    head_videos: Optional[List[Path]] = None,
    transparent_avatars: Optional[List[Path]] = None,
    subtitle_file: Optional[Path] = None,
    music_file: Optional[Path] = None,
) -> Union[Path, List[str]]:
    """Compose final video from timeline.

    Automatically selects filter builder based on timeline entries.

    Args:
        timeline: Composition timeline.
        config: UGCKit configuration.
        dry_run: If True, return command list without executing.
        head_videos: Pre-processed head video files for PiP mode.
        transparent_avatars: Transparent avatar videos for green screen mode.
        subtitle_file: ASS subtitle file for overlay.
        music_file: Background music file path.

    Returns:
        Path to output video, or command list if dry_run.

    Raises:
        ValueError: If timeline has no output_path.
        FFmpegError: If files are missing or FFmpeg fails.
    """
    if not timeline.output_path:
        raise ValueError("Timeline must have output_path set")

    validate_timeline_files(timeline)

    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    screencast_entries = [e for e in timeline.entries if e.type == "screencast"]

    inputs = []
    audio_presence = []
    for entry in avatar_entries:
        inputs.extend(["-i", str(entry.file)])
        audio_presence.append(has_audio_stream(entry.file))
    for entry in screencast_entries:
        inputs.extend(["-i", str(entry.file)])

    mode = _detect_composition_mode(timeline)

    # Add extra inputs per mode
    if mode == CompositionMode.PIP and head_videos:
        for hv in head_videos:
            inputs.extend(["-i", str(hv)])
    elif mode == CompositionMode.GREENSCREEN and transparent_avatars:
        for ta in transparent_avatars:
            inputs.extend(["-i", str(ta)])

    # Music input
    music_input_index = None
    effective_music = music_file or (config.music.file if config.music.enabled else None)
    if effective_music:
        music_input_index = len(inputs) // 2  # count of -i pairs
        inputs.extend(["-i", str(effective_music)])

    # Build filter complex
    if mode == CompositionMode.PIP:
        filter_complex = build_ffmpeg_filter_pip(
            timeline,
            config,
            audio_presence=audio_presence,
            head_videos=head_videos,
        )
    elif mode == CompositionMode.SPLIT:
        filter_complex = build_ffmpeg_filter_split(
            timeline,
            config,
            audio_presence=audio_presence,
        )
    elif mode == CompositionMode.GREENSCREEN:
        filter_complex = build_ffmpeg_filter_greenscreen(
            timeline,
            config,
            audio_presence=audio_presence,
            transparent_avatars=transparent_avatars,
        )
    else:
        filter_complex = build_ffmpeg_filter_overlay(
            timeline,
            config,
            audio_presence=audio_presence,
        )

    # Post-processing: subtitles + music
    filter_complex = wrap_with_post_processing(
        filter_complex,
        subtitle_file=subtitle_file,
        music_input_index=music_input_index,
        music_config=config.music if effective_music else None,
        total_duration=timeline.total_duration,
    )

    output_cfg = config.output
    output_args = [
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        output_cfg.codec,
        "-preset",
        output_cfg.preset,
        "-crf",
        str(output_cfg.crf),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(output_cfg.fps),
        "-c:a",
        config.audio.codec,
        "-b:a",
        config.audio.bitrate,
        "-movflags",
        "+faststart",
        "-y",
        str(timeline.output_path),
    ]

    cmd = ["ffmpeg"] + inputs + ["-filter_complex", filter_complex] + output_args

    if dry_run:
        return cmd

    timeline.output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise FFmpegError("FFmpeg rendering timed out (5 min limit)")
    if result.returncode != 0:
        raise FFmpegError(f"FFmpeg failed: {result.stderr}")

    return timeline.output_path


def build_ffmpeg_cmd(
    timeline: Timeline,
    config: Config,
    head_videos: Optional[List[Path]] = None,
    transparent_avatars: Optional[List[Path]] = None,
    subtitle_file: Optional[Path] = None,
    music_file: Optional[Path] = None,
) -> List[str]:
    """Build the full FFmpeg command for a timeline.

    Delegates to compose_video with dry_run=True.
    """
    result = compose_video(
        timeline,
        config,
        dry_run=True,
        head_videos=head_videos,
        transparent_avatars=transparent_avatars,
        subtitle_file=subtitle_file,
        music_file=music_file,
    )
    return result


def format_ffmpeg_cmd(cmd: List[str]) -> str:
    """Format an FFmpeg command for display."""
    return shlex.join(cmd)


def compose_video_with_progress(
    timeline: Timeline,
    config: Config,
    progress_callback: Callable[[float], None],
    head_videos: Optional[List[Path]] = None,
    transparent_avatars: Optional[List[Path]] = None,
    subtitle_file: Optional[Path] = None,
    music_file: Optional[Path] = None,
) -> Path:
    """Compose video with progress reporting.

    Uses ffmpeg -progress pipe:1 to parse progress and report via callback.
    """
    cmd = build_ffmpeg_cmd(
        timeline,
        config,
        head_videos=head_videos,
        transparent_avatars=transparent_avatars,
        subtitle_file=subtitle_file,
        music_file=music_file,
    )

    # Insert progress flags before output path
    # Replace -y with progress args + -y
    idx = cmd.index("-y")
    cmd[idx:idx] = ["-progress", "pipe:1", "-nostats"]

    timeline.output_path.parent.mkdir(parents=True, exist_ok=True)

    total_us = timeline.total_duration * 1_000_000

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us="):
                try:
                    current_us = int(line.split("=", 1)[1])
                    progress = min(current_us / total_us, 1.0) if total_us > 0 else 0.0
                    progress_callback(progress)
                except (ValueError, ZeroDivisionError):
                    pass
            elif line == "progress=end":
                progress_callback(1.0)

        proc.wait()
    except Exception:
        proc.kill()
        raise

    if proc.returncode != 0:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise FFmpegError(f"FFmpeg failed: {stderr}")

    return timeline.output_path
