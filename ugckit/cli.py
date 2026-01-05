"""Command-line interface for UGCKit."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

import click

from ugckit.composer import build_timeline, compose_video, format_timeline
from ugckit.config import load_config
from ugckit.models import CompositionMode, Position
from ugckit.parser import find_script_by_id, parse_markdown_file, parse_scripts_directory


@click.group()
@click.version_option()
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
    required=True,
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Avatar video files (one per segment, in order)",
)
@click.option(
    "--screencasts",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Directory containing screencast files",
)
@click.option(
    "--scripts-dir",
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
    type=click.Choice(["overlay", "pip"]),
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
    "--dry-run",
    is_flag=True,
    help="Show timeline and FFmpeg command without rendering",
)
def compose(
    script: str,
    avatars: Tuple[Path, ...],
    screencasts: Optional[Path],
    scripts_dir: Optional[Path],
    output: Optional[Path],
    config: Optional[Path],
    mode: str,
    head_position: str,
    dry_run: bool,
):
    """Compose a video from script and avatar clips.

    Example:
        ugckit compose --script A1_day347 --avatars seg1.mp4 --avatars seg2.mp4

    With dry-run:
        ugckit compose --script A1_day347 --avatars *.mp4 --dry-run
    """
    # Load configuration
    cfg = load_config(config)

    # Override config with CLI options
    if mode == "pip":
        cfg.composition.pip.head_position = Position(head_position)

    # Determine screencasts directory
    if screencasts:
        screencasts_dir = screencasts
    else:
        screencasts_dir = cfg.screencasts_path

    # Parse script
    script_path = Path(script)
    if script_path.exists() and script_path.suffix == ".md":
        # Direct path to markdown file
        scripts = parse_markdown_file(script_path)
        if not scripts:
            click.echo(f"Error: No scripts found in {script_path}", err=True)
            sys.exit(1)
        parsed_script = scripts[0]
    else:
        # Script ID - search in scripts directory
        if scripts_dir:
            search_dir = scripts_dir
        else:
            # Default: look in current directory or common locations
            search_dir = Path(".")

        scripts = parse_scripts_directory(search_dir)
        parsed_script = find_script_by_id(scripts, script)

        if not parsed_script:
            click.echo(f"Error: Script '{script}' not found", err=True)
            click.echo(f"Available scripts: {[s.script_id for s in scripts]}", err=True)
            sys.exit(1)

    # Sort avatar files
    avatar_list = sorted(list(avatars))

    if len(avatar_list) < len(parsed_script.segments):
        click.echo(
            f"Warning: {len(avatar_list)} avatar clips for {len(parsed_script.segments)} segments",
            err=True,
        )

    # Determine output path
    if output:
        if output.is_dir():
            output_path = output / f"{parsed_script.script_id}.mp4"
        else:
            output_path = output
    else:
        output_path = cfg.output_path / f"{parsed_script.script_id}.mp4"

    # Build timeline
    timeline = build_timeline(
        script=parsed_script,
        avatar_clips=avatar_list,
        screencasts_dir=screencasts_dir,
        output_path=output_path,
    )

    # Display timeline
    click.echo(format_timeline(timeline))
    click.echo()

    if dry_run:
        click.echo("Dry run - no video will be rendered")
        click.echo()
        # Show FFmpeg command
        compose_video(timeline, cfg, dry_run=True)
        return

    # Compose video
    click.echo("Composing video...")
    try:
        result_path = compose_video(timeline, cfg, dry_run=False)
        click.echo(f"Done! Output: {result_path}")
    except Exception as e:
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
        click.echo(f"  {script.script_id:15} | {script.title[:40]:40} | {segments} segments | ~{duration:.0f}s")


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
    script_path = Path(script)

    if script_path.exists() and script_path.suffix == ".md":
        scripts = parse_markdown_file(script_path)
        if scripts:
            parsed_script = scripts[0]
        else:
            click.echo(f"No scripts found in {script_path}", err=True)
            return
    else:
        search_dir = scripts_dir or Path(".")
        scripts = parse_scripts_directory(search_dir)
        parsed_script = find_script_by_id(scripts, script)

        if not parsed_script:
            click.echo(f"Script '{script}' not found", err=True)
            return

    click.echo(f"Script: {parsed_script.script_id}")
    click.echo(f"Title: {parsed_script.title}")
    if parsed_script.character:
        click.echo(f"Character: {parsed_script.character}")
    click.echo(f"Total duration: ~{parsed_script.total_duration:.1f}s")
    click.echo()
    click.echo("Segments:")

    for seg in parsed_script.segments:
        click.echo(f"  [{seg.id}] ({seg.duration:.1f}s) {seg.text[:60]}...")
        for sc in seg.screencasts:
            click.echo(f"       └─ screencast: {sc.file} @ {sc.start}s-{sc.end}s")


if __name__ == "__main__":
    main()
