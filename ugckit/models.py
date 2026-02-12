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

    scale: float = Field(default=0.4, ge=0.1, le=1.0)
    position: Position = Position.BOTTOM_RIGHT
    margin: int = Field(default=50, ge=0)


class PipConfig(BaseModel):
    """Configuration for PiP mode."""

    head_scale: float = Field(default=0.25, ge=0.05, le=0.5)
    head_position: Position = Position.TOP_RIGHT
    head_margin: int = Field(default=30, ge=0)


class SplitConfig(BaseModel):
    """Configuration for split screen mode."""

    avatar_side: Literal["left", "right"] = "left"
    split_ratio: float = Field(default=0.5, ge=0.2, le=0.8)


class GreenScreenConfig(BaseModel):
    """Configuration for green screen mode."""

    avatar_scale: float = Field(default=0.8, ge=0.1, le=1.0)
    avatar_position: Position = Position.BOTTOM_RIGHT
    avatar_margin: int = Field(default=30, ge=0)


class SubtitleConfig(BaseModel):
    """Configuration for auto-subtitles."""

    enabled: bool = False
    font_name: str = "Arial"
    font_size: int = Field(default=48, ge=8, le=200)
    outline_width: int = Field(default=3, ge=0, le=20)
    position_y: int = Field(default=200, ge=0)
    max_words_per_line: int = Field(default=5, ge=1, le=20)
    highlight_color: str = "&H0000FFFF"  # ASS yellow highlight
    whisper_model: str = "base"


class MusicConfig(BaseModel):
    """Configuration for background music."""

    enabled: bool = False
    file: Optional[Path] = None
    volume: float = Field(default=0.15, ge=0.0, le=1.0)
    fade_out_duration: float = Field(default=2.0, ge=0.0)
    loop: bool = True


class OutputConfig(BaseModel):
    """Output video configuration."""

    fps: int = Field(default=30, ge=1, le=120)
    resolution: Tuple[int, int] = (1080, 1920)
    codec: str = "libx264"
    preset: str = "medium"
    crf: int = Field(default=23, ge=0, le=51)


class AudioConfig(BaseModel):
    """Audio processing configuration."""

    normalize: bool = True
    target_loudness: int = Field(default=-14, ge=-70, le=0)
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
