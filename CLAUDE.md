# CLAUDE.md - UGCKit

**Repo:** `/Volumes/SSD/Repos/ugckit`
**Type:** Python CLI tool
**Purpose:** Automated assembly of short UGC videos from AI avatars + screencasts

## Quick Commands

```bash
# Test parsing
python3 -m ugckit.cli list-scripts --scripts-dir /path/to/scripts/

# Show script details
python3 -m ugckit.cli show-script --script A1 --scripts-dir /path/to/scripts/

# Dry-run composition
python3 -m ugckit.cli compose --script A1 --avatars seg1.mp4 --avatars seg2.mp4 --dry-run
```

## Architecture

```
ugckit/
├── cli.py        # Click CLI entry point
├── parser.py     # MD → Script model (regex parsing)
├── composer.py   # Timeline + FFmpeg filter_complex
├── config.py     # YAML config loader
└── models.py     # Pydantic models (Script, Timeline, Config)
```

## Key Files

| File | Purpose |
|------|---------|
| [parser.py](ugckit/parser.py) | Markdown script parser with SAYS_PATTERN, CLIP_PATTERN |
| [composer.py](ugckit/composer.py) | FFmpeg filter_complex builder, `build_timeline()`, `compose_video()` |
| [models.py](ugckit/models.py) | Pydantic models: Script, Segment, Timeline, Config |
| [ugckit/config/default.yaml](ugckit/config/default.yaml) | Default composition settings |

## Data Flow

```
Markdown Script → parser.py → Script model
                                    ↓
Avatar clips + Script → composer.py → Timeline
                                           ↓
Timeline + Config → FFmpeg filter_complex → Output video
```

## Patterns

### Regex Patterns (parser.py)
- `SCRIPT_HEADER_PATTERN`: `### Script A1: "Title"`
- `CLIP_PATTERN`: `**Clip 1 (VEO 8s):**`
- `SAYS_PATTERN`: `Says: "text with apostrophes allowed"`
- `SCREENCAST_PATTERN`: `[screencast: filename @ start-end mode:pip]`

### FFmpeg Composition (composer.py)
- Scale avatars to 1080x1920
- Concat video streams: `[av0][av1]concat=n=2:v=1:a=0[base]`
- Overlay screencasts with timing: `overlay=enable='between(t,1.5,4.0)'`
- Audio normalization: `loudnorm=I=-14:TP=-1.5:LRA=11`

## Config Structure

```yaml
composition:
  overlay:
    scale: 0.4           # screencast size (40% of width)
    position: bottom-right
    margin: 50           # pixels from edge
  pip:
    head_scale: 0.25     # head cutout size
    head_position: top-right

output:
  resolution: [1080, 1920]  # 9:16 vertical
  fps: 30
  codec: libx264
  crf: 23

audio:
  normalize: true
  target_loudness: -14   # LUFS
```

## Development Phases

| Phase | Status | Features |
|-------|--------|----------|
| 1. MVP | Done | CLI, parser, overlay mode, --dry-run |
| 2. PiP | Pending | MediaPipe face detection, rembg background removal |
| 3. Smart Sync | Pending | Whisper timestamps, keyword triggers |

## DO NOT

1. Use `[\"']` in regex for quoted text (breaks on apostrophes)
2. Add MoviePy dependency (pure FFmpeg only)
3. Use PiP mode features until Phase 2 is implemented

## Related

- Scripts location: `step-saga-app/docs/product-marketing/video-prompts/`
- Avatar source: Higgsfield AI
- Output: TikTok/Reels format (9:16, <40s)
