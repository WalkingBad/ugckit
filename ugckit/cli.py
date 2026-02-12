"""Command-line interface for UGCKit."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

import click

from ugckit.composer import (
    FFmpegError,
    build_timeline,
    compose_video,
    format_ffmpeg_cmd,
    format_timeline,
)
from ugckit.config import load_config
from ugckit.models import CompositionMode, Position
from ugckit.parser import load_script, parse_scripts_directory
from ugckit.pipeline import (
    apply_sync,
    generate_subtitles,
    prepare_greenscreen_videos,
    prepare_pip_videos,
)


@click.group()
@click.version_option(version="0.1.0")
def main():
    """UGCKit - AI UGC Video Assembly Tool.

    Combine AI avatar clips with app screencasts to create
    short vertical videos for TikTok/Reels.
    """
    pass


@main.command()
@click.option(
    "--script",
    "-s",
    required=True,
    help="Script ID (e.g., A1_day347) or path to markdown file",
)
@click.option(
    "--avatars",
    "-a",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Avatar video files (one per segment, in order)",
)
@click.option(
    "--avatar-dir",
    type=click.Path(exists=True, path_type=Path),
    help="Directory containing avatar .mp4 files (sorted by filename)",
)
@click.option(
    "--screencasts",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Directory containing screencast files",
)
@click.option(
    "--scripts-dir",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    help="Directory containing script markdown files",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output directory or file path",
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config YAML file",
)
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["overlay", "pip", "split", "greenscreen"]),
    default="overlay",
    help="Composition mode",
)
@click.option(
    "--head-position",
    type=click.Choice(["top-left", "top-right", "bottom-left", "bottom-right"]),
    default="top-right",
    help="Head position for PiP mode",
)
@click.option(
    "--head-scale",
    type=float,
    default=0.25,
    help="Head size as fraction of output width (0.1-0.5)",
)
@click.option(
    "--sync",
    is_flag=True,
    help="Enable Smart Sync (Whisper) for keyword-based screencast timing",
)
@click.option(
    "--sync-model",
    type=click.Choice(["tiny", "base", "small", "medium", "large"]),
    default="base",
    help="Whisper model size for Smart Sync",
)
@click.option(
    "--avatar-side",
    type=click.Choice(["left", "right"]),
    default="left",
    help="Avatar side for split screen mode",
)
@click.option(
    "--split-ratio",
    type=float,
    default=0.5,
    help="Split ratio (0.3-0.7, default 0.5 = 50/50)",
)
@click.option(
    "--gs-avatar-scale",
    type=float,
    default=0.8,
    help="Avatar scale for green screen mode (0.3-1.0)",
)
@click.option(
    "--gs-avatar-position",
    type=click.Choice(["top-left", "top-right", "bottom-left", "bottom-right"]),
    default="bottom-right",
    help="Avatar position for green screen mode",
)
@click.option(
    "--music",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Background music file (mp3/wav/m4a)",
)
@click.option(
    "--music-volume",
    type=float,
    default=0.15,
    help="Music volume (0.0-1.0, default 0.15)",
)
@click.option(
    "--music-fade-out",
    type=float,
    default=2.0,
    help="Music fade-out duration in seconds",
)
@click.option(
    "--subtitles",
    is_flag=True,
    help="Enable auto-subtitles (Whisper transcription)",
)
@click.option(
    "--subtitle-font-size",
    type=int,
    default=48,
    help="Subtitle font size",
)
@click.option(
    "--subtitle-model",
    type=click.Choice(["tiny", "base", "small", "medium", "large"]),
    default="base",
    help="Whisper model for subtitle transcription",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show timeline and FFmpeg command without rendering",
)
def compose(
    script: str,
    avatars: Tuple[Path, ...],
    avatar_dir: Optional[Path],
    screencasts: Optional[Path],
    scripts_dir: Optional[Path],
    output: Optional[Path],
    config: Optional[Path],
    mode: str,
    head_position: str,
    head_scale: float,
    sync: bool,
    sync_model: str,
    avatar_side: str,
    split_ratio: float,
    gs_avatar_scale: float,
    gs_avatar_position: str,
    music: Optional[Path],
    music_volume: float,
    music_fade_out: float,
    subtitles: bool,
    subtitle_font_size: int,
    subtitle_model: str,
    dry_run: bool,
):
    """Compose a video from script and avatar clips.

    Provide avatars via --avatars (one per segment) or --avatar-dir (auto-sorted).

    Example:
        ugckit compose --script A1 --avatars seg1.mp4 --avatars seg2.mp4
        ugckit compose --script A1 --avatar-dir ./avatars/ --mode pip
    """
    if not avatars and not avatar_dir:
        click.echo("Error: provide --avatars or --avatar-dir", err=True)
        sys.exit(1)

    # Load configuration
    cfg = load_config(config)

    # Determine screencasts directory
    screencasts_dir = screencasts or cfg.screencasts_path

    # Parse script
    try:
        parsed_script = load_script(script, scripts_dir)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Resolve avatar list
    if avatar_dir:
        avatar_list = sorted(avatar_dir.glob("*.mp4"))
        if not avatar_list:
            click.echo(f"Error: no .mp4 files in {avatar_dir}", err=True)
            sys.exit(1)
    else:
        avatar_list = list(avatars)

    if len(avatar_list) < len(parsed_script.segments):
        click.echo(
            f"Warning: {len(avatar_list)} avatar clips for {len(parsed_script.segments)} segments",
            err=True,
        )

    # Smart Sync: resolve keyword-based screencast timing
    if sync:
        click.echo("Running Smart Sync (Whisper)...")
        parsed_script = apply_sync(parsed_script, avatar_list, sync_model)

    # Override screencast modes based on --mode
    mode_enum = CompositionMode(mode)
    if mode_enum != CompositionMode.OVERLAY:
        for seg in parsed_script.segments:
            for sc in seg.screencasts:
                sc.mode = mode_enum

    # Apply split/greenscreen config from CLI
    cfg.composition.split.avatar_side = avatar_side
    cfg.composition.split.split_ratio = split_ratio
    cfg.composition.greenscreen.avatar_scale = gs_avatar_scale
    cfg.composition.greenscreen.avatar_position = Position(gs_avatar_position)

    # Music config
    if music:
        cfg.music.enabled = True
        cfg.music.file = music
        cfg.music.volume = music_volume
        cfg.music.fade_out_duration = music_fade_out

    # Subtitle config
    if subtitles:
        cfg.subtitles.enabled = True
        cfg.subtitles.font_size = subtitle_font_size
        cfg.subtitles.whisper_model = subtitle_model

    # Determine output path
    if output:
        if output.is_dir():
            output_path = output / f"{parsed_script.script_id}.mp4"
        else:
            output_path = output
    else:
        output_path = cfg.output_path / f"{parsed_script.script_id}.mp4"

    # Build timeline
    try:
        timeline = build_timeline(
            script=parsed_script,
            avatar_clips=avatar_list,
            screencasts_dir=screencasts_dir,
            output_path=output_path,
        )
    except (ValueError, FFmpegError) as e:
        click.echo(f"Error building timeline: {e}", err=True)
        sys.exit(1)

    # Pre-process for PiP mode
    head_videos = None
    if mode == "pip":
        click.echo("Generating head videos for PiP mode...")
        cfg.composition.pip.head_position = Position(head_position)
        cfg.composition.pip.head_scale = head_scale
        head_videos = prepare_pip_videos(avatar_list, cfg)
        if not head_videos:
            click.echo("Warning: PiP head extraction failed, using overlay mode", err=True)

    # Pre-process for green screen mode
    transparent_avatars = None
    if mode == "greenscreen":
        click.echo("Generating transparent avatars for green screen mode...")
        transparent_avatars = prepare_greenscreen_videos(avatar_list, cfg)
        if not transparent_avatars:
            click.echo("Warning: green screen processing failed, using overlay mode", err=True)

    # Generate subtitles
    subtitle_file = None
    if subtitles:
        click.echo("Generating subtitles (Whisper)...")
        subtitle_file = generate_subtitles(timeline, avatar_list, cfg)

    # Display timeline
    click.echo(format_timeline(timeline))
    click.echo()

    if dry_run:
        click.echo("Dry run - no video will be rendered")
        click.echo()
        cmd = compose_video(
            timeline,
            cfg,
            dry_run=True,
            head_videos=head_videos,
            transparent_avatars=transparent_avatars,
            subtitle_file=subtitle_file,
            music_file=music,
        )
        click.echo("FFmpeg command:")
        click.echo(format_ffmpeg_cmd(cmd))
        return

    # Compose video
    click.echo("Composing video...")
    try:
        result_path = compose_video(
            timeline,
            cfg,
            dry_run=False,
            head_videos=head_videos,
            transparent_avatars=transparent_avatars,
            subtitle_file=subtitle_file,
            music_file=music,
        )
        click.echo(f"Done! Output: {result_path}")
    except (ValueError, FFmpegError) as e:
        click.echo(f"Error composing video: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option(
    "--scripts-dir",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Directory containing script markdown files",
)
def list_scripts(scripts_dir: Path):
    """List all available scripts.

    Example:
        ugckit list-scripts --scripts-dir ./scripts/
    """
    scripts = parse_scripts_directory(scripts_dir)

    if not scripts:
        click.echo("No scripts found")
        return

    click.echo(f"Found {len(scripts)} scripts:")
    click.echo()

    for script in scripts:
        segments = len(script.segments)
        duration = script.total_duration
        click.echo(
            f"  {script.script_id:15} | {script.title[:40]:40} | {segments} segments | ~{duration:.0f}s"
        )


@main.command()
@click.option(
    "--script",
    "-s",
    required=True,
    help="Script ID or path to markdown file",
)
@click.option(
    "--scripts-dir",
    type=click.Path(exists=True, path_type=Path),
    help="Directory containing script markdown files",
)
def show_script(script: str, scripts_dir: Optional[Path]):
    """Show details of a specific script.

    Example:
        ugckit show-script --script A1_day347
    """
    try:
        parsed_script = load_script(script, scripts_dir)
    except (FileNotFoundError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo(f"Script: {parsed_script.script_id}")
    click.echo(f"Title: {parsed_script.title}")
    if parsed_script.character:
        click.echo(f"Character: {parsed_script.character}")
    click.echo(f"Total duration: ~{parsed_script.total_duration:.1f}s")
    click.echo()
    click.echo("Segments:")

    for seg in parsed_script.segments:
        suffix = "..." if len(seg.text) > 60 else ""
        click.echo(f"  [{seg.id}] ({seg.duration:.1f}s) {seg.text[:60]}{suffix}")
        for sc in seg.screencasts:
            mode_str = f" [{sc.mode.value}]" if sc.mode != CompositionMode.OVERLAY else ""
            if sc.start_keyword:
                click.echo(
                    f'       └─ screencast: {sc.file} @ word:"{sc.start_keyword}"-word:"{sc.end_keyword}"{mode_str}'
                )
            else:
                click.echo(f"       └─ screencast: {sc.file} @ {sc.start}s-{sc.end}s{mode_str}")


@main.command()
@click.option(
    "--scripts-dir",
    "-d",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Directory containing script markdown files",
)
@click.option(
    "--avatar-dir",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Directory containing avatar .mp4 files (matched by script ID prefix)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output directory",
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config YAML file",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show timelines and FFmpeg commands without rendering",
)
def batch(
    scripts_dir: Path,
    avatar_dir: Path,
    output: Optional[Path],
    config: Optional[Path],
    dry_run: bool,
):
    """Batch compose videos for all scripts with matching avatars.

    Avatar files are matched by script ID prefix (e.g., A1_seg1.mp4 -> script A1).

    Example:
        ugckit batch --scripts-dir ./scripts/ --avatar-dir ./avatars/ --dry-run
    """
    cfg = load_config(config)
    scripts = parse_scripts_directory(scripts_dir)

    if not scripts:
        click.echo("No scripts found", err=True)
        sys.exit(1)

    # Collect all avatar files
    all_avatars = sorted(avatar_dir.glob("*.mp4"))
    if not all_avatars:
        click.echo(f"No .mp4 files in {avatar_dir}", err=True)
        sys.exit(1)

    output_dir = output or cfg.output_path
    screencasts_dir = cfg.screencasts_path

    success = 0
    errors = 0

    for script in scripts:
        sid = script.script_id.upper()

        # Match avatars by script ID prefix (e.g., A1_seg1.mp4)
        matched = [f for f in all_avatars if f.stem.upper().startswith(sid)]

        # If no prefix match, try all avatars (single-script batch)
        if not matched and len(scripts) == 1:
            matched = all_avatars

        if not matched:
            click.echo(f"  [{script.script_id}] SKIP - no matching avatars")
            continue

        matched.sort()
        output_path = output_dir / f"{script.script_id}.mp4"

        click.echo(f"  [{script.script_id}] {script.title} ({len(matched)} clips)")

        try:
            timeline = build_timeline(
                script=script,
                avatar_clips=matched,
                screencasts_dir=screencasts_dir,
                output_path=output_path,
            )
        except (ValueError, FFmpegError) as e:
            click.echo(f"  [{script.script_id}] ERROR: {e}", err=True)
            errors += 1
            continue

        if dry_run:
            click.echo(format_timeline(timeline))
            cmd = compose_video(timeline, cfg, dry_run=True)
            click.echo("FFmpeg command:")
            click.echo(format_ffmpeg_cmd(cmd))
            click.echo()
            success += 1
            continue

        try:
            result_path = compose_video(timeline, cfg, dry_run=False)
            click.echo(f"  [{script.script_id}] OK -> {result_path}")
            success += 1
        except (ValueError, FFmpegError) as e:
            click.echo(f"  [{script.script_id}] FAIL: {e}", err=True)
            errors += 1

    click.echo()
    click.echo(f"Batch complete: {success} ok, {errors} errors")


if __name__ == "__main__":
    main()
