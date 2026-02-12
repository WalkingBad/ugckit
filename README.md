# UGCKit

AI UGC Video Assembly Tool - Combine AI avatar clips with app screencasts to create short vertical videos for TikTok/Reels.

## Features

- Parse video scripts from Markdown format
- Build composition timelines with precise timing
- **4 composition modes**: Overlay, PiP, Split Screen, Green Screen
- **Auto-subtitles** — Whisper transcription with karaoke-style word highlighting (ASS)
- **Background music** — mix music under avatar speech with loop/fade support
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

# PiP enhanced mode / Green screen (optional)
pip install mediapipe rembg numpy Pillow opencv-python

# Smart Sync / Auto-subtitles (optional)
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

# PiP mode
ugckit compose \
  --script A1 \
  --avatar-dir ./avatars/ \
  --mode pip \
  --head-scale 0.25 \
  --dry-run

# Split screen mode
ugckit compose \
  --script A1 \
  --avatar-dir ./avatars/ \
  --mode split \
  --avatar-side left \
  --dry-run

# Green screen mode
ugckit compose \
  --script A1 \
  --avatar-dir ./avatars/ \
  --mode greenscreen \
  --dry-run

# Background music
ugckit compose \
  --script A1 \
  --avatar-dir ./avatars/ \
  --music bg.mp3 \
  --music-volume 0.15 \
  --dry-run

# Auto-subtitles
ugckit compose \
  --script A1 \
  --avatar-dir ./avatars/ \
  --subtitles \
  --dry-run

# Combined: split + music + subtitles
ugckit compose \
  --script A1 \
  --avatar-dir ./avatars/ \
  --mode split \
  --subtitles \
  --music bg.mp3 \
  --dry-run

# Smart Sync (Whisper keyword timing)
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
| `--mode, -m` | Composition mode: `overlay`, `pip`, `split`, `greenscreen` |
| `--head-scale` | Head size for PiP mode (0.1-0.5, default 0.25) |
| `--head-position` | Head position for PiP mode |
| `--avatar-side` | Avatar side for split mode: `left` (default) or `right` |
| `--split-ratio` | Split ratio (0.3-0.7, default 0.5) |
| `--gs-avatar-scale` | Avatar scale for green screen (0.3-1.0, default 0.8) |
| `--gs-avatar-position` | Avatar position for green screen |
| `--music` | Background music file (mp3/wav/m4a) |
| `--music-volume` | Music volume (0.0-1.0, default 0.15) |
| `--music-fade-out` | Music fade-out duration in seconds (default 2.0) |
| `--subtitles` | Enable auto-subtitles (Whisper transcription) |
| `--subtitle-font-size` | Subtitle font size (default 48) |
| `--subtitle-model` | Whisper model for subtitles: tiny, base, small, medium, large |
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

### Split Screen Mode

Avatar on one side, screencast on the other (50/50 by default).

```
┌────────────┬────────────┐
│            │            │
│   AVATAR   │ SCREENCAST │
│  (person)  │   (app)    │
│            │            │
│            │            │
└────────────┴────────────┘
```

### Green Screen Mode

Avatar background removed (rembg), composited over fullscreen screencast.

```
┌─────────────────────────┐
│                         │
│       SCREENCAST        │
│     (app recording)     │
│                         │
│         ┌───────┐       │
│         │AVATAR │       │
│         │(no bg)│       │
│         └───────┘       │
└─────────────────────────┘
```

### Post-Processing Layers

Subtitles and music are orthogonal — they work with any composition mode:

- **Auto-subtitles**: Whisper transcription → ASS file with karaoke `\kf` word highlighting
- **Background music**: loop + fade-out + amix under avatar speech

## Configuration

Edit `ugckit/config/default.yaml`:

```yaml
composition:
  overlay:
    scale: 0.4              # Screencast size (40% of width)
    position: bottom-right
    margin: 50
  pip:
    head_scale: 0.25
    head_position: top-right
  split:
    avatar_side: left        # "left" or "right"
    split_ratio: 0.5         # 0.5 = 50/50
  greenscreen:
    avatar_scale: 0.8
    avatar_position: bottom-right

output:
  fps: 30
  resolution: [1080, 1920]  # 9:16 vertical
  codec: libx264
  crf: 23

audio:
  normalize: true
  target_loudness: -14       # LUFS

subtitles:
  enabled: false
  font_size: 48
  max_words_per_line: 5
  highlight_color: "&H0000FFFF"

music:
  enabled: false
  volume: 0.15
  fade_out_duration: 2.0
  loop: true

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
[screencast: filename @ start-end mode:split]
```

Keyword-based timing (Smart Sync):
```
[screencast: filename @ word:"check this out"-word:"and done" mode:overlay]
```

- `filename`: Name without extension (will add `.mp4`) or with `.mp4`
- `start-end`: Time range in seconds relative to clip start
- `word:"phrase"`: Keyword trigger — Whisper finds when these words are spoken
- `mode`: Optional — `overlay` (default), `pip`, `split`, `greenscreen`

## Project Structure

```
ugckit/
├── ugckit/
│   ├── __init__.py
│   ├── cli.py            # Click CLI commands
│   ├── parser.py         # Markdown → Script model
│   ├── composer.py       # Timeline + FFmpeg composition (4 modes + post-processing)
│   ├── config.py         # YAML config loader
│   ├── models.py         # Pydantic data models
│   ├── pip_processor.py  # PiP head extraction + green screen transparent avatar
│   ├── subtitles.py      # Auto-subtitles (Whisper → ASS karaoke)
│   ├── sync.py           # Smart Sync (Whisper + keyword matching)
│   └── config/
│       └── default.yaml  # Default settings
├── tests/
│   ├── conftest.py
│   ├── test_parser.py
│   ├── test_composer.py
│   ├── test_cli.py
│   ├── test_pip_processor.py
│   ├── test_subtitles.py
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
- 4-mode selector: Overlay, PiP, Split Screen, Green Screen
- Split screen settings (avatar side, split ratio)
- Green screen settings (avatar scale, position)
- Auto-subtitles toggle (font size, Whisper model)
- Background music (file upload, volume, fade-out)
- Smart Sync (Whisper) toggle
- Batch composition of all scripts

## Development Roadmap

| Phase | Status | Features |
|-------|--------|----------|
| Phase 1: MVP | **Done** | CLI, parser, overlay mode, --dry-run |
| Phase 2: PiP | **Done** | Head extraction (basic FFmpeg + enhanced MediaPipe/rembg), PiP filter builder |
| Phase 3: Smart Sync | **Done** | Whisper word-level timestamps, keyword triggers |
| Phase 4: Extended | **Done** | Split screen, green screen, auto-subtitles (ASS karaoke), background music |

## Testing

```bash
pytest tests/ -v
```

160 tests covering parser, composer, CLI, PiP processor, subtitles, and sync module.

## License

MIT
