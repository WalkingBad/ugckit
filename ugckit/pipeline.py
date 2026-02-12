"""Shared pipeline operations for UGCKit.

Framework-agnostic functions used by both CLI and Streamlit UI.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from ugckit.models import Config, Script, Timeline


def prepare_pip_videos(avatar_list: list[Path], config: Config) -> list[Path]:
    """Create head cutout videos for PiP mode. Returns [] on failure."""
    from ugckit.pip_processor import PipProcessingError, create_head_video

    head_videos = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="ugckit_pip_"))

    for i, avatar in enumerate(avatar_list):
        head_out = tmp_dir / f"head_{i}.webm"
        try:
            head_path = create_head_video(avatar, head_out, config.composition.pip)
            head_videos.append(head_path)
        except PipProcessingError:
            return []

    return head_videos


def prepare_greenscreen_videos(avatar_list: list[Path], config: Config) -> list[Path]:
    """Create transparent avatar videos. Returns [] on failure."""
    from ugckit.pip_processor import PipProcessingError, create_transparent_avatar

    gs_cfg = config.composition.greenscreen
    transparent_avatars = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="ugckit_gs_"))

    for i, avatar in enumerate(avatar_list):
        out = tmp_dir / f"transparent_{i}.webm"
        try:
            ta_path = create_transparent_avatar(
                avatar,
                out,
                scale=gs_cfg.avatar_scale,
                output_width=config.output.resolution[0],
            )
            transparent_avatars.append(ta_path)
        except (ImportError, PipProcessingError):
            return []

    return transparent_avatars


def apply_sync(script: Script, avatar_list: list[Path], model_name: str) -> Script:
    """Resolve keyword-based screencast timing via Whisper. Returns original on failure."""
    from ugckit.sync import SyncError, sync_screencast_timing

    try:
        return sync_screencast_timing(script, avatar_list, model_name)
    except SyncError:
        return script


def generate_subtitles(
    timeline: Timeline, avatar_list: list[Path], config: Config
) -> Optional[Path]:
    """Generate ASS subtitle file. Returns None on failure."""
    try:
        from ugckit.subtitles import generate_subtitle_file

        return generate_subtitle_file(timeline, avatar_list, config)
    except Exception:
        return None
