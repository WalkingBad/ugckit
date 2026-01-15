"""Configuration loading for UGCKit."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from ugckit.models import Config

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "default.yaml"


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

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return Config()

    return Config.model_validate(data)
