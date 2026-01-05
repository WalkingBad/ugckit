"""Configuration loading for UGCKit."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from ugckit.models import (
    AudioConfig,
    CompositionConfig,
    Config,
    OutputConfig,
    OverlayConfig,
    PipConfig,
)

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.yaml"


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config file. Uses default.yaml if not specified.

    Returns:
        Loaded Config object.
    """
    path = config_path or DEFAULT_CONFIG_PATH

    if not path.exists():
        return Config()

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data:
        return Config()

    # Parse composition config
    comp_data = data.get("composition", {})
    overlay_config = OverlayConfig(**comp_data.get("overlay", {}))
    pip_config = PipConfig(
        head_scale=comp_data.get("pip", {}).get("head_scale", 0.25),
        head_position=comp_data.get("pip", {}).get("head_position", "top-right"),
        head_margin=comp_data.get("pip", {}).get("head_margin", 30),
    )
    composition_config = CompositionConfig(overlay=overlay_config, pip=pip_config)

    # Parse output config
    output_data = data.get("output", {})
    resolution = output_data.get("resolution", [1080, 1920])
    output_config = OutputConfig(
        fps=output_data.get("fps", 30),
        bitrate=output_data.get("bitrate", "8M"),
        resolution=(resolution[0], resolution[1]),
        codec=output_data.get("codec", "libx264"),
        preset=output_data.get("preset", "medium"),
        crf=output_data.get("crf", 23),
    )

    # Parse audio config
    audio_data = data.get("audio", {})
    audio_config = AudioConfig(**audio_data)

    # Parse paths
    paths_data = data.get("paths", {})
    screencasts_path = Path(paths_data.get("screencasts", "./assets/screencasts"))
    output_path = Path(paths_data.get("output", "./assets/output"))

    return Config(
        composition=composition_config,
        output=output_config,
        audio=audio_config,
        screencasts_path=screencasts_path,
        output_path=output_path,
    )
