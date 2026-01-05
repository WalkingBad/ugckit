# UGCKit Architecture

## Overview

UGCKit is a Python CLI tool for automated assembly of short vertical videos by combining AI-generated avatar clips with app screencasts.

```
┌─────────────────────────────────────────────────────────────┐
│                         UGCKit                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────┐     ┌──────────┐     ┌──────────────────┐    │
│   │ Scripts │ ──▶ │  Parser  │ ──▶ │  Script Model    │    │
│   │  (MD)   │     │          │     │  (segments,      │    │
│   └─────────┘     └──────────┘     │   screencasts)   │    │
│                                     └────────┬─────────┘    │
│                                              │              │
│   ┌─────────┐                               ▼              │
│   │ Avatar  │     ┌──────────┐     ┌──────────────────┐    │
│   │ Clips   │ ──▶ │ Composer │ ──▶ │    Timeline      │    │
│   │ (MP4)   │     │          │     │  (start, end,    │    │
│   └─────────┘     └──────────┘     │   type, file)    │    │
│                                     └────────┬─────────┘    │
│                                              │              │
│   ┌─────────┐     ┌──────────┐              ▼              │
│   │ Config  │ ──▶ │  FFmpeg  │     ┌──────────────────┐    │
│   │ (YAML)  │     │ Builder  │ ──▶ │  Output Video    │    │
│   └─────────┘     └──────────┘     │  (1080x1920)     │    │
│                                     └──────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Module Responsibilities

### cli.py - Command Line Interface

Entry point for all user interactions.

```python
@click.group()
def main():
    """UGCKit - AI UGC Video Assembly Tool."""

@main.command()
def compose(): ...    # Main composition command
def list_scripts(): ... # List available scripts
def show_script(): ...  # Show script details
```

**Key Responsibilities:**
- Parse CLI arguments
- Load configuration
- Coordinate parser and composer
- Display timeline preview
- Handle errors gracefully

### parser.py - Markdown Script Parser

Converts Markdown scripts to structured data models.

```python
# Regex patterns
SCRIPT_HEADER_PATTERN  # ### Script A1: "Title"
CLIP_PATTERN           # **Clip 1 (VEO 8s):**
SAYS_PATTERN           # Says: "text"
SCREENCAST_PATTERN     # [screencast: file @ start-end]

# Functions
def parse_markdown_file(path) -> List[Script]
def parse_script_section(content, id, title) -> Script
def parse_screencast_tag(text) -> Optional[ScreencastOverlay]
def find_script_by_id(scripts, id) -> Optional[Script]
```

**Key Responsibilities:**
- Parse script headers (ID, title, character)
- Extract clips and speech text
- Parse screencast overlay tags
- Estimate duration from word count

### composer.py - FFmpeg Composition Engine

Builds timelines and generates FFmpeg filter_complex commands.

```python
def get_video_duration(path) -> float
def build_timeline(script, clips, screencasts_dir, output) -> Timeline
def build_ffmpeg_filter_overlay(timeline, config) -> str
def compose_video(timeline, config, dry_run) -> Optional[Path]
```

**Key Responsibilities:**
- Build composition timeline from script and clips
- Generate FFmpeg filter_complex string
- Handle video scaling (1080x1920)
- Apply audio normalization
- Execute FFmpeg or show dry-run command

### models.py - Pydantic Data Models

Type-safe data structures for the entire application.

```python
# Enums
class CompositionMode(str, Enum): OVERLAY, PIP
class Position(str, Enum): TOP_LEFT, TOP_RIGHT, ...

# Script models
class ScreencastOverlay(BaseModel): file, start, end, mode
class Segment(BaseModel): id, text, duration, screencasts
class Script(BaseModel): script_id, title, segments

# Timeline models
class TimelineEntry(BaseModel): start, end, type, file
class Timeline(BaseModel): script_id, entries, output_path

# Config models
class OverlayConfig(BaseModel): scale, position, margin
class OutputConfig(BaseModel): fps, resolution, codec
class Config(BaseModel): composition, output, audio
```

### config.py - Configuration Loader

Loads and validates YAML configuration.

```python
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.yaml"

def load_config(config_path: Optional[Path] = None) -> Config
```

## Data Flow

### 1. Script Parsing

```
templates.md
     │
     ▼
┌─────────────────────────────────────────┐
│ ### Script A1: "Day 347"                │
│ **Clip 1 (VEO 8s):**                    │
│ Says: "Day three forty-seven..."        │
└─────────────────────────────────────────┘
     │
     ▼ parse_markdown_file()
     │
┌─────────────────────────────────────────┐
│ Script(                                 │
│   script_id="A1",                       │
│   title="Day 347",                      │
│   segments=[                            │
│     Segment(id=1, text="Day...", ...)   │
│   ]                                     │
│ )                                       │
└─────────────────────────────────────────┘
```

### 2. Timeline Building

```
Script + Avatar Clips
         │
         ▼ build_timeline()
         │
┌─────────────────────────────────────────┐
│ Timeline(                               │
│   entries=[                             │
│     TimelineEntry(                      │
│       start=0.0, end=6.0,               │
│       type="avatar", file="seg1.mp4"    │
│     ),                                  │
│     TimelineEntry(                      │
│       start=1.5, end=4.0,               │
│       type="screencast",                │
│       file="stats.mp4"                  │
│     ),                                  │
│     ...                                 │
│   ]                                     │
│ )                                       │
└─────────────────────────────────────────┘
```

### 3. FFmpeg Composition

```
Timeline + Config
        │
        ▼ build_ffmpeg_filter_overlay()
        │
┌─────────────────────────────────────────┐
│ [0:v]scale=1080:1920,setsar=1[av0];     │
│ [1:v]scale=1080:1920,setsar=1[av1];     │
│ [av0][av1]concat=n=2:v=1:a=0[base];     │
│ [0:a][1:a]concat=n=2:v=0:a=1[audio];    │
│ [2:v]scale=432:-1[sc0];                 │
│ [base][sc0]overlay=x=...:y=...:         │
│   enable='between(t,1.5,4.0)'[out0];    │
│ [out0]null[vout];                       │
│ [audio]loudnorm=I=-14:TP=-1.5[aout]     │
└─────────────────────────────────────────┘
        │
        ▼ compose_video()
        │
┌─────────────────────────────────────────┐
│ ffmpeg -i seg1.mp4 -i seg2.mp4          │
│   -i stats.mp4 -filter_complex "..."    │
│   -map [vout] -map [aout]               │
│   -c:v libx264 -preset medium           │
│   -crf 23 -r 30 -c:a aac -b:a 192k      │
│   -y output.mp4                         │
└─────────────────────────────────────────┘
```

## FFmpeg Filter Graph

### Overlay Mode

```
Input 0 (avatar1) ─┬─▶ scale ─▶ [av0] ─┐
Input 1 (avatar2) ─┴─▶ scale ─▶ [av1] ─┼─▶ concat ─▶ [base]
                                       │
Input 2 (screencast) ─▶ scale ─▶ [sc0] │
                                       │
              [base] + [sc0] ─▶ overlay ─▶ [vout]
                                       │
[0:a] + [1:a] ─▶ concat ─▶ loudnorm ─▶ [aout]
```

### Position Coordinates

```python
# TOP_LEFT:     x=margin,         y=margin
# TOP_RIGHT:    x=W-w-margin,     y=margin
# BOTTOM_LEFT:  x=margin,         y=H-h-margin
# BOTTOM_RIGHT: x=W-w-margin,     y=H-h-margin
```

## Configuration Schema

```yaml
composition:
  overlay:
    scale: float      # 0.0-1.0, percentage of width
    position: enum    # top-left, top-right, bottom-left, bottom-right
    margin: int       # pixels from edge
    rotation: float   # degrees
    shadow: bool

  pip:
    head_scale: float
    head_position: enum
    head_margin: int

output:
  fps: int
  bitrate: str        # e.g., "8M"
  resolution: [w, h]  # e.g., [1080, 1920]
  codec: str          # e.g., "libx264"
  preset: str         # ultrafast, fast, medium, slow
  crf: int            # 0-51, lower = better quality

audio:
  normalize: bool
  target_loudness: int  # LUFS, e.g., -14
  crossfade_ms: int
  screencast_volume: float  # 0.0 = mute

paths:
  screencasts: str
  output: str
```

## Phase Roadmap

### Phase 1: MVP (Current)

- [x] CLI with compose, list-scripts, show-script
- [x] Markdown parser with screencast tags
- [x] FFmpeg overlay composition
- [x] YAML configuration
- [x] --dry-run mode
- [x] Audio normalization

### Phase 2: PiP Mode

- [ ] MediaPipe face detection
- [ ] rembg background removal
- [ ] Head cutout extraction
- [ ] PiP composition mode

### Phase 3: Smart Sync

- [ ] Whisper audio transcription
- [ ] Word-level timestamps
- [ ] Keyword-triggered screencasts
- [ ] Automatic timing adjustment
