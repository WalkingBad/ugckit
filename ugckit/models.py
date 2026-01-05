"""Pydantic models for UGCKit."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


class CompositionMode(str, Enum):
    """Video composition mode."""

    OVERLAY = "overlay"  # Avatar as background, screencast in corner
    PIP = "pip"  # Screencast fullscreen, head cutout in corner


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


class Segment(BaseModel):
    """A segment of the video (one avatar clip)."""

    id: int
    text: str
    duration: float  # Expected duration in seconds
    avatar_clip: Optional[Path] = None  # Path to avatar video file
    screencasts: List[ScreencastOverlay] = Field(default_factory=list)
    composition_mode: CompositionMode = CompositionMode.OVERLAY


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
    rotation: float = 5.0
    shadow: bool = True


class PipConfig(BaseModel):
    """Configuration for PiP mode."""

    head_scale: float = 0.25
    head_position: Position = Position.TOP_RIGHT
    head_margin: int = 30


class OutputConfig(BaseModel):
    """Output video configuration."""

    fps: int = 30
    bitrate: str = "8M"
    resolution: Tuple[int, int] = (1080, 1920)
    codec: str = "libx264"
    preset: str = "medium"
    crf: int = 23


class AudioConfig(BaseModel):
    """Audio processing configuration."""

    normalize: bool = True
    target_loudness: int = -14
    crossfade_ms: int = 100
    screencast_volume: float = 0.0


class CompositionConfig(BaseModel):
    """Full composition configuration."""

    overlay: OverlayConfig = Field(default_factory=OverlayConfig)
    pip: PipConfig = Field(default_factory=PipConfig)


class Config(BaseModel):
    """Full UGCKit configuration."""

    composition: CompositionConfig = Field(default_factory=CompositionConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    screencasts_path: Path = Path("./assets/screencasts")
    output_path: Path = Path("./assets/output")
