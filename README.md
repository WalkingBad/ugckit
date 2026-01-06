# UGCKit

AI UGC Video Assembly Tool - Combine AI avatar clips with app screencasts to create short vertical videos for TikTok/Reels.

## Features

- Parse video scripts from Markdown format
- Build composition timelines with precise timing
- Overlay screencasts on avatar videos
- Audio normalization (loudnorm filter)
- `--dry-run` mode for previewing without rendering
- YAML configuration for all settings

## Installation

### System Requirements

- Python 3.11+
- FFmpeg (`brew install ffmpeg` on macOS)

### Install

```bash
cd ugckit
pip install -e .
```

Or install dependencies manually:
```bash
pip install click pyyaml pydantic
```

## Quick Start

```bash
# List available scripts
ugckit list-scripts --scripts-dir ./scripts/

# Show script details
ugckit show-script --script A1 --scripts-dir ./scripts/

# Preview timeline (dry-run)
ugckit compose \
  --script A1 \
  --avatars ./avatars/seg1.mp4 \
  --avatars ./avatars/seg2.mp4 \
  --scripts-dir ./scripts/ \
  --dry-run

# Compose video
ugckit compose \
  --script A1 \
  --avatars ./avatars/seg1.mp4 \
  --avatars ./avatars/seg2.mp4 \
  --screencasts ./assets/screencasts/ \
  --output ./output/
```

## CLI Reference

### `ugckit compose`

Compose a video from script and avatar clips.

| Option | Description |
|--------|-------------|
| `--script, -s` | Script ID or path to markdown file (required) |
| `--avatars, -a` | Avatar video files, one per segment (required, multiple) |
| `--screencasts, -c` | Directory containing screencast files |
| `--scripts-dir` | Directory containing script markdown files |
| `--output, -o` | Output directory or file path |
| `--config` | Path to config YAML file |
| `--mode, -m` | Composition mode: `overlay` (default) or `pip` (Phase 2, shows warning) |
| `--head-position` | Head position for PiP mode (Phase 2) |
| `--dry-run` | Show timeline and FFmpeg command without rendering |

### `ugckit list-scripts`

List all available scripts in a directory.

```bash
ugckit list-scripts --scripts-dir ./scripts/
```

### `ugckit show-script`

Show details of a specific script.

```bash
ugckit show-script --script A1 --scripts-dir ./scripts/
```

## Composition Modes

### Overlay Mode (default)

Avatar video as background, screencast appears in corner at specified times.

```
┌─────────────────────────┐
│                         │
│      AVATAR VIDEO       │
│    (person walking)     │
│                         │
│           ┌────────┐    │
│           │SCREEN- │    │
│           │CAST    │    │
│           └────────┘    │
└─────────────────────────┘
```

### PiP Mode (Phase 2)

Screencast fullscreen, avatar head cutout in corner.

```
┌─────────────────────────┐
│                         │
│       SCREENCAST        │
│     (app recording)     │
│                         │
│   ┌────────┐            │
│   │ HEAD   │            │
│   │(cutout)│            │
│   └────────┘            │
└─────────────────────────┘
```

## Configuration

Edit `ugckit/config/default.yaml`:

```yaml
composition:
  overlay:
    scale: 0.4              # Screencast size (40% of width)
    position: bottom-right  # top-left, top-right, bottom-left, bottom-right
    margin: 50              # Pixels from edge

output:
  fps: 30
  resolution: [1080, 1920]  # 9:16 vertical
  codec: libx264
  preset: medium
  crf: 23

audio:
  normalize: true           # Apply loudnorm filter
  target_loudness: -14      # LUFS

paths:
  screencasts: ./assets/screencasts
  output: ./assets/output
```

## Script Format

Scripts use Markdown format with optional screencast tags:

```markdown
### Script A1: "Day 347" (Office Worker Mike)

**Clip 1 (VEO 8s):**
Says: "Day three forty-seven. I'm still walking to Mordor."

**Clip 2 (VEO 8s):**
[screencast: stats_screen @ 1.5-4.0]
Says: "My coworkers think I'm crazy. But look at these stats."

**Clip 3 (VEO 8s):**
Says: "It's an app called MistyWay."
```

### Screencast Tag Format

```
[screencast: filename @ start-end mode:pip]
```

- `filename`: Name without extension (will add `.mp4`)
- `start-end`: Time range in seconds relative to clip start
- `mode`: Optional, `overlay` (default) or `pip`

## Project Structure

```
ugckit/
├── ugckit/
│   ├── __init__.py
│   ├── cli.py          # Click CLI commands
│   ├── parser.py       # Markdown → Script model
│   ├── composer.py     # Timeline + FFmpeg composition
│   ├── config.py       # YAML config loader
│   ├── models.py       # Pydantic data models
│   └── config/
│       └── default.yaml  # Default settings
├── assets/
│   ├── screencasts/    # App screen recordings
│   ├── avatars/        # AI avatar clips
│   └── output/         # Generated videos
├── docs/
│   ├── ARCHITECTURE.md
│   └── USAGE_RU.md     # Russian instructions
├── pyproject.toml
├── CLAUDE.md
└── README.md
```

## Development Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| Phase 1: MVP | **Done** | CLI, parser, overlay mode, --dry-run |
| Phase 2: PiP | Planned | MediaPipe face detection, rembg background removal |
| Phase 3: Smart Sync | Planned | Whisper timestamps, keyword-triggered screencasts |

## License

MIT
