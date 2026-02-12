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
    from ugckit.models import CompositionMode

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
    """Check if timeline has any PiP mode screencasts."""
    from ugckit.models import CompositionMode

    return any(
        e.composition_mode == CompositionMode.PIP
        for e in timeline.entries
        if e.type == "screencast"
    )


def compose_video(
    timeline: Timeline,
    config: Config,
    dry_run: bool = False,
    head_videos: Optional[List[Path]] = None,
) -> Union[Path, List[str]]:
    """Compose final video from timeline.

    Automatically selects overlay or PiP filter builder based on timeline entries.

    Args:
        timeline: Composition timeline.
        config: UGCKit configuration.
        dry_run: If True, return command list without executing.
        head_videos: Pre-processed head video files for PiP mode.

    Returns:
        Path to output video, or command list if dry_run.

    Raises:
        ValueError: If timeline has no output_path.
        FFmpegError: If files are missing or FFmpeg fails.
    """
    if not timeline.output_path:
        raise ValueError("Timeline must have output_path set")

    # Validate all files exist before building command
    validate_timeline_files(timeline)

    # Collect all input files
    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    screencast_entries = [e for e in timeline.entries if e.type == "screencast"]

    # Build input arguments and check for audio
    inputs = []
    audio_presence = []
    for entry in avatar_entries:
        inputs.extend(["-i", str(entry.file)])
        audio_presence.append(has_audio_stream(entry.file))
    for entry in screencast_entries:
        inputs.extend(["-i", str(entry.file)])

    # Add head video inputs for PiP mode
    use_pip = _timeline_has_pip(timeline)
    if use_pip and head_videos:
        for hv in head_videos:
            inputs.extend(["-i", str(hv)])

    # Build filter complex
    if use_pip:
        filter_complex = build_ffmpeg_filter_pip(
            timeline,
            config,
            audio_presence=audio_presence,
            head_videos=head_videos,
        )
    else:
        filter_complex = build_ffmpeg_filter_overlay(
            timeline,
            config,
            audio_presence=audio_presence,
        )

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

    # Full command
    cmd = ["ffmpeg"] + inputs + ["-filter_complex", filter_complex] + output_args

    if dry_run:
        return cmd

    # Ensure output directory exists
    timeline.output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run FFmpeg (5 min timeout for rendering)
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
) -> List[str]:
    """Build the full FFmpeg command for a timeline.

    Args:
        timeline: Composition timeline.
        config: UGCKit configuration.
        head_videos: Pre-processed head video files for PiP mode.

    Returns:
        FFmpeg command as list of strings.

    Raises:
        ValueError: If timeline has no output_path.
        FFmpegError: If files are missing or ffprobe fails.
    """
    if not timeline.output_path:
        raise ValueError("Timeline must have output_path set")

    validate_timeline_files(timeline)

    avatar_entries = [e for e in timeline.entries if e.type == "avatar"]
    screencast_entries = [e for e in timeline.entries if e.type == "screencast"]

    inputs: List[str] = []
    audio_presence = []
    for entry in avatar_entries:
        inputs.extend(["-i", str(entry.file)])
        audio_presence.append(has_audio_stream(entry.file))
    for entry in screencast_entries:
        inputs.extend(["-i", str(entry.file)])

    use_pip = _timeline_has_pip(timeline)
    if use_pip and head_videos:
        for hv in head_videos:
            inputs.extend(["-i", str(hv)])

    if use_pip:
        filter_complex = build_ffmpeg_filter_pip(
            timeline, config, audio_presence=audio_presence, head_videos=head_videos
        )
    else:
        filter_complex = build_ffmpeg_filter_overlay(
            timeline, config, audio_presence=audio_presence
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

    return ["ffmpeg"] + inputs + ["-filter_complex", filter_complex] + output_args


def format_ffmpeg_cmd(cmd: List[str]) -> str:
    """Format an FFmpeg command for display."""
    return shlex.join(cmd)


def compose_video_with_progress(
    timeline: Timeline,
    config: Config,
    progress_callback: Callable[[float], None],
    head_videos: Optional[List[Path]] = None,
) -> Path:
    """Compose video with progress reporting.

    Uses ffmpeg -progress pipe:1 to parse progress and report via callback.

    Args:
        timeline: Composition timeline.
        config: UGCKit configuration.
        progress_callback: Called with float 0.0-1.0 as rendering progresses.
        head_videos: Pre-processed head video files for PiP mode.

    Returns:
        Path to output video.

    Raises:
        ValueError: If timeline has no output_path.
        FFmpegError: If FFmpeg fails.
    """
    cmd = build_ffmpeg_cmd(timeline, config, head_videos=head_videos)

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
