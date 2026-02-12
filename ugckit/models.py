"""Pydantic models for UGCKit."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


class CompositionMode(str, Enum):
    """Video composition mode."""

    OVERLAY = "overlay"  # Avatar as background, screencast in corner
    PIP = "pip"  # Screencast fullscreen, head cutout in corner
    SPLIT = "split"  # Avatar left, screencast right (50/50)
    GREENSCREEN = "greenscreen"  # Avatar bg removed, composite over screencast


class Position(str, Enum):
    """Corner position for overlays."""

    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"


class ScreencastOverlay(BaseModel):
    """Screencast overlay definition."""

    file: str  # Filename in screencasts folder
    start: float  # Start time in seconds
    end: float  # End time in seconds
    mode: CompositionMode = CompositionMode.OVERLAY
    start_keyword: Optional[str] = None  # Keyword trigger for start (Phase 3)
    end_keyword: Optional[str] = None  # Keyword trigger for end (Phase 3)


class Segment(BaseModel):
    """A segment of the video (one avatar clip)."""

    id: int
    text: str
    duration: float  # Expected duration in seconds
    screencasts: List[ScreencastOverlay] = Field(default_factory=list)


class Script(BaseModel):
    """Parsed script with all segments."""

    script_id: str
    title: str
    character: Optional[str] = None
    total_duration: float = 0.0
    segments: List[Segment] = Field(default_factory=list)


class TimelineEntry(BaseModel):
    """Entry in the composition timeline."""

    start: float
    end: float
    type: Literal["avatar", "screencast"]
    file: Path
    parent_segment: Optional[int] = None  # For screencasts, which segment they belong to
    composition_mode: CompositionMode = CompositionMode.OVERLAY


class Timeline(BaseModel):
    """Full composition timeline."""

    script_id: str
    total_duration: float
    entries: List[TimelineEntry] = Field(default_factory=list)
    output_path: Optional[Path] = None


class OverlayConfig(BaseModel):
    """Configuration for overlay mode."""

    scale: float = 0.4
    position: Position = Position.BOTTOM_RIGHT
    margin: int = 50


class PipConfig(BaseModel):
    """Configuration for PiP mode."""

    head_scale: float = 0.25
    head_position: Position = Position.TOP_RIGHT
    head_margin: int = 30


class SplitConfig(BaseModel):
    """Configuration for split screen mode."""

    avatar_side: str = "left"  # "left" or "right"
    split_ratio: float = 0.5  # 0.5 = 50/50


class GreenScreenConfig(BaseModel):
    """Configuration for green screen mode."""

    avatar_scale: float = 0.8
    avatar_position: Position = Position.BOTTOM_RIGHT
    avatar_margin: int = 30


class SubtitleConfig(BaseModel):
    """Configuration for auto-subtitles."""

    enabled: bool = False
    font_name: str = "Arial"
    font_size: int = 48
    outline_width: int = 3
    position_y: int = 200  # pixels from bottom
    max_words_per_line: int = 5
    highlight_color: str = "&H0000FFFF"  # ASS yellow highlight
    whisper_model: str = "base"


class MusicConfig(BaseModel):
    """Configuration for background music."""

    enabled: bool = False
    file: Optional[Path] = None
    volume: float = 0.15  # 0.0-1.0
    fade_out_duration: float = 2.0
    loop: bool = True


class OutputConfig(BaseModel):
    """Output video configuration."""

    fps: int = 30
    resolution: Tuple[int, int] = (1080, 1920)
    codec: str = "libx264"
    preset: str = "medium"
    crf: int = 23


class AudioConfig(BaseModel):
    """Audio processing configuration."""

    normalize: bool = True
    target_loudness: int = -14
    codec: str = "aac"
    bitrate: str = "192k"


class CompositionConfig(BaseModel):
    """Full composition configuration."""

    overlay: OverlayConfig = Field(default_factory=OverlayConfig)
    pip: PipConfig = Field(default_factory=PipConfig)
    split: SplitConfig = Field(default_factory=SplitConfig)
    greenscreen: GreenScreenConfig = Field(default_factory=GreenScreenConfig)


class Config(BaseModel):
    """Full UGCKit configuration."""

    composition: CompositionConfig = Field(default_factory=CompositionConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    subtitles: SubtitleConfig = Field(default_factory=SubtitleConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    screencasts_path: Path = Path("./assets/screencasts")
    output_path: Path = Path("./assets/output")

    @model_validator(mode="before")
    @classmethod
    def transform_yaml_structure(cls, data: dict) -> dict:
        """Transform YAML structure to model structure."""
        if not isinstance(data, dict):
            return data

        # Handle paths section from YAML
        paths = data.pop("paths", {})
        if paths:
            if "screencasts" in paths:
                data["screencasts_path"] = paths["screencasts"]
            if "output" in paths:
                data["output_path"] = paths["output"]

        # Handle resolution as list -> tuple
        if "output" in data and "resolution" in data["output"]:
            res = data["output"]["resolution"]
            if isinstance(res, list) and len(res) == 2:
                data["output"]["resolution"] = tuple(res)

        return data
