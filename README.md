# UGCKit

AI UGC Video Assembly Tool - Combine AI avatar clips with app screencasts to create short vertical videos for TikTok/Reels.

## Installation

```bash
# Clone the repo
git clone https://github.com/nickolay/ugckit.git
cd ugckit

# Install in development mode
pip install -e .

# Or with optional dependencies for Phase 2/3
pip install -e ".[phase2,phase3]"
```

### System Requirements

- Python 3.11+
- FFmpeg (`brew install ffmpeg`)

## Quick Start

```bash
# List available scripts
ugckit list-scripts --scripts-dir ./scripts/

# Show script details
ugckit show-script --script A1_day347

# Preview timeline (dry-run)
ugckit compose \
  --script A1_day347 \
  --avatars ./avatars/mike_seg*.mp4 \
  --dry-run

# Compose video
ugckit compose \
  --script A1_day347 \
  --avatars ./avatars/mike_seg1.mp4 \
  --avatars ./avatars/mike_seg2.mp4 \
  --screencasts ./assets/screencasts/ \
  --output ./output/
```

## Composition Modes

### Overlay Mode (default)
Avatar video as background, screencast in corner.

```bash
ugckit compose --script A1 --avatars *.mp4 --mode overlay
```

### PiP Mode
Screencast fullscreen, avatar head cutout in corner.

```bash
ugckit compose --script A1 --avatars *.mp4 --mode pip --head-position top-right
```

## Configuration

Edit `config/default.yaml` to customize:

```yaml
composition:
  overlay:
    scale: 0.4              # 40% of screen width
    position: bottom-right
    margin: 50
    rotation: 5

output:
  fps: 30
  bitrate: "8M"
  resolution: [1080, 1920]  # 9:16 vertical

audio:
  normalize: true
  crossfade_ms: 100
  screencast_volume: 0.0    # mute screencast
```

## Project Structure

```
ugckit/
├── ugckit/           # Python package
│   ├── cli.py        # Click CLI
│   ├── parser.py     # MD script parser
│   ├── composer.py   # FFmpeg composition
│   └── models.py     # Pydantic models
├── config/
│   └── default.yaml  # Default settings
├── assets/
│   ├── screencasts/  # App recordings
│   └── output/       # Generated videos
└── pyproject.toml
```

## Script Format

Scripts use markdown format with screencast tags:

```markdown
### Script A1: "Day 347"

**Clip 1 (VEO 8s):**
[screencast: stats_screen @ 1.5-4.0]
Says: "Day 347. I'm still walking to Mordor."

**Clip 2 (VEO 8s):**
Says: "My coworkers think I'm crazy."
```

## License

MIT
