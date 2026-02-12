# UGCKit

AI UGC Video Assembly Tool - Combine AI avatar clips with app screencasts to create short vertical videos for TikTok/Reels.

## Features

- Parse video scripts from Markdown format
- Build composition timelines with precise timing
- **Overlay mode** — screencast in corner over avatar video
- **PiP mode** — screencast fullscreen, avatar head cutout in corner (basic FFmpeg crop + enhanced MediaPipe/rembg)
- **Smart Sync** — Whisper-based keyword triggers for automatic screencast timing
- Audio normalization (loudnorm filter)
- `--dry-run` mode for previewing without rendering
- **Streamlit Web UI** with Russian interface
- **Batch processing** — compose all scripts at once
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
# Core
pip install click pyyaml pydantic

# PiP enhanced mode (optional)
pip install mediapipe rembg numpy Pillow

# Smart Sync (optional)
pip install openai-whisper

# Web UI (optional)
pip install streamlit
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
  --avatar-dir ./avatars/ \
  --scripts-dir ./scripts/ \
  --dry-run

# Compose video (overlay mode)
ugckit compose \
  --script A1 \
  --avatar-dir ./avatars/ \
  --screencasts ./assets/screencasts/ \
  --output ./output/

# Compose video (PiP mode)
ugckit compose \
  --script A1 \
  --avatar-dir ./avatars/ \
  --mode pip \
  --head-scale 0.25 \
  --dry-run

# Compose with Smart Sync (Whisper)
ugckit compose \
  --script A1 \
  --avatar-dir ./avatars/ \
  --sync --sync-model base \
  --dry-run

# Batch compose all scripts
ugckit batch \
  --scripts-dir ./scripts/ \
  --avatar-dir ./avatars/ \
  --dry-run

# Launch Web UI
streamlit run streamlit_app.py
```

## CLI Reference

### `ugckit compose`

Compose a video from script and avatar clips.

| Option | Description |
|--------|-------------|
| `--script, -s` | Script ID (required) |
| `--avatars, -a` | Avatar video files, one per segment (multiple) |
| `--avatar-dir` | Directory with avatar .mp4 files |
| `--screencasts, -c` | Directory containing screencast files |
| `--scripts-dir, -d` | Directory containing script markdown files |
| `--output, -o` | Output directory or file path |
| `--config` | Path to config YAML file |
| `--mode, -m` | Composition mode: `overlay` (default) or `pip` |
| `--head-scale` | Head size for PiP mode (0.1-0.5, default 0.25) |
| `--head-position` | Head position for PiP mode (top-left, top-right, bottom-left, bottom-right) |
| `--sync` | Enable Smart Sync (Whisper keyword timing) |
| `--sync-model` | Whisper model: tiny, base, small, medium, large (default: base) |
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

### PiP Mode

Screencast fullscreen, avatar head cutout in corner.

Two-tier head extraction:
- **Basic** (FFmpeg-only): center crop + circular mask, always available
- **Enhanced** (MediaPipe + rembg): face detection + background removal, requires optional deps

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

Numeric timing:
```
[screencast: filename @ start-end mode:pip]
```

Keyword-based timing (Smart Sync):
```
[screencast: filename @ word:"check this out"-word:"and done" mode:overlay]
```

- `filename`: Name without extension (will add `.mp4`) or with `.mp4`
- `start-end`: Time range in seconds relative to clip start
- `word:"phrase"`: Keyword trigger — Whisper finds when these words are spoken
- `mode`: Optional, `overlay` (default) or `pip`

## Project Structure

```
ugckit/
├── ugckit/
│   ├── __init__.py
│   ├── cli.py            # Click CLI commands
│   ├── parser.py         # Markdown → Script model
│   ├── composer.py       # Timeline + FFmpeg composition (overlay + PiP)
│   ├── config.py         # YAML config loader
│   ├── models.py         # Pydantic data models
│   ├── pip_processor.py  # PiP head extraction (basic + enhanced)
│   ├── sync.py           # Smart Sync (Whisper + keyword matching)
│   └── config/
│       └── default.yaml  # Default settings
├── tests/
│   ├── conftest.py
│   ├── test_parser.py
│   ├── test_composer.py
│   ├── test_cli.py
│   ├── test_pip_processor.py
│   └── test_sync.py
├── streamlit_app.py      # Web UI (Russian)
├── pyproject.toml
├── CLAUDE.md
└── README.md
```

## Web UI

Launch the Streamlit web interface (Russian):

```bash
streamlit run streamlit_app.py
```

Features:
- Drag-and-drop file uploads (scripts, avatars, screencasts)
- Timeline preview and FFmpeg command inspection
- Overlay / PiP mode toggle
- Smart Sync (Whisper) toggle
- Batch composition of all scripts
- Settings panel (CRF, codec, audio normalization, PiP head size)

## Development Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| Phase 1: MVP | **Done** | CLI, parser, overlay mode, --dry-run |
| Phase 2: PiP | **Done** | Head extraction (basic FFmpeg + enhanced MediaPipe/rembg), PiP filter builder |
| Phase 3: Smart Sync | **Done** | Whisper word-level timestamps, keyword triggers |

## Testing

```bash
pytest tests/ -v
```

121 tests covering parser, composer, CLI, PiP processor, and sync module.

## License

MIT
