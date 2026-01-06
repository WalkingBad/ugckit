"""FFmpeg video composition for UGCKit.

Handles video assembly using FFmpeg filter_complex.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from ugckit.models import (
    CompositionMode,
    Config,
    Position,
    Script,
    Timeline,
    TimelineEntry,
)


def get_video_duration(video_path: Path) -> float:
    """Get duration of a video file using ffprobe.

    Args:
        video_path: Path to video file.

    Returns:
        Duration in seconds.
    """
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
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def has_audio_stream(video_path: Path) -> bool:
    """Check if video file has an audio stream.

    Args:
        video_path: Path to video file.

    Returns:
        True if audio stream exists.
    """
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
    result = subprocess.run(cmd, capture_output=True, text=True)
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
    """
    entries: List[TimelineEntry] = []
    current_time = 0.0

    for i, segment in enumerate(script.segments):
        if i >= len(avatar_clips):
            break

        avatar_clip = avatar_clips[i]

        # Get actual duration from video file
        try:
            duration = get_video_duration(avatar_clip)
        except (subprocess.CalledProcessError, FileNotFoundError):
            duration = segment.duration

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
                entries.append(
                    TimelineEntry(
                        start=current_time + sc.start,
                        end=current_time + sc.end,
                        type="screencast",
                        file=sc_path,
                        parent_segment=segment.id,
                    )
                )

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
    has_audio: bool = True,
) -> str:
    """Build FFmpeg filter_complex string for overlay mode.

    Args:
        timeline: Composition timeline.
        config: UGCKit configuration.
        has_audio: Whether avatar clips have audio streams.

    Returns:
        FFmpeg filter_complex string.
    """
    filters = []
    overlay_cfg = config.composition.overlay
    output_cfg = config.output

    # Count inputs
    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    screencast_entries = [e for e in timeline.entries if e.type == "screencast"]

    # Scale avatars to output resolution
    for i, _ in enumerate(avatar_entries):
        filters.append(
            f"[{i}:v]scale={output_cfg.resolution[0]}:{output_cfg.resolution[1]},"
            f"setsar=1[av{i}]"
        )

    # Concatenate avatars
    if len(avatar_entries) > 1:
        concat_inputs = "".join(f"[av{i}]" for i in range(len(avatar_entries)))
        if has_audio:
            audio_inputs = "".join(f"[{i}:a]" for i in range(len(avatar_entries)))
            filters.append(
                f"{concat_inputs}concat=n={len(avatar_entries)}:v=1:a=0[base];"
                f"{audio_inputs}concat=n={len(avatar_entries)}:v=0:a=1[audio]"
            )
        else:
            # No audio - just concat video, generate silent audio
            filters.append(
                f"{concat_inputs}concat=n={len(avatar_entries)}:v=1:a=0[base];"
                f"anullsrc=r=48000:cl=stereo,atrim=0:{timeline.total_duration:.2f}[audio]"
            )
    else:
        if has_audio:
            filters.append("[av0]copy[base];[0:a]anull[audio]")
        else:
            # No audio - generate silent audio
            filters.append(
                f"[av0]copy[base];"
                f"anullsrc=r=48000:cl=stereo,atrim=0:{timeline.total_duration:.2f}[audio]"
            )

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
            f"w",
            f"h",
        )

        # Overlay with timing
        enable = f"between(t,{sc_entry.start:.2f},{sc_entry.end:.2f})"
        filters.append(
            f"[{current_base}][sc{i}]overlay=x={x}:y={y}:enable='{enable}'[{next_base}]"
        )
        current_base = next_base

    # Final output
    if screencast_entries:
        filters.append(f"[{current_base}]null[vout]")
    else:
        filters.append("[base]null[vout]")

    # Audio normalization
    if config.audio.normalize:
        filters.append(
            f"[audio]loudnorm=I={config.audio.target_loudness}:TP=-1.5:LRA=11[aout]"
        )
    else:
        filters.append("[audio]anull[aout]")

    return ";".join(filters)


def compose_video(
    timeline: Timeline,
    config: Config,
    dry_run: bool = False,
) -> Optional[Path]:
    """Compose final video from timeline.

    Args:
        timeline: Composition timeline.
        config: UGCKit configuration.
        dry_run: If True, only print command without executing.

    Returns:
        Path to output video, or None if dry_run.
    """
    if not timeline.output_path:
        raise ValueError("Timeline must have output_path set")

    # Collect all input files
    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    screencast_entries = [e for e in timeline.entries if e.type == "screencast"]

    # Build input arguments and check for audio
    inputs = []
    all_have_audio = True
    for entry in avatar_entries:
        inputs.extend(["-i", str(entry.file)])
        if not has_audio_stream(entry.file):
            all_have_audio = False
    for entry in screencast_entries:
        inputs.extend(["-i", str(entry.file)])

    # Build filter complex
    filter_complex = build_ffmpeg_filter_overlay(timeline, config, has_audio=all_have_audio)

    # Build output arguments
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
        "-r",
        str(output_cfg.fps),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-y",  # Overwrite output
        str(timeline.output_path),
    ]

    # Full command
    cmd = ["ffmpeg"] + inputs + ["-filter_complex", filter_complex] + output_args

    if dry_run:
        print("FFmpeg command:")
        print(" ".join(cmd))
        return None

    # Ensure output directory exists
    timeline.output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run FFmpeg
    subprocess.run(cmd, check=True)

    return timeline.output_path
