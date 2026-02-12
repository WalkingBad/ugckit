# CLAUDE.md - UGCKit

**Repo:** `/Volumes/SSD/Repos/ugckit`
**Type:** Python CLI tool
**Purpose:** Automated assembly of short UGC videos from AI avatars + screencasts

## Quick Commands

```bash
# List scripts
ugckit list-scripts -d /path/to/scripts/

# Show script details
ugckit show-script -s A1 --scripts-dir /path/to/scripts/

# Dry-run overlay mode
ugckit compose -s A1 --avatar-dir ./avatars/ -d ./scripts/ --dry-run

# Dry-run PiP mode
ugckit compose -s A1 --avatar-dir ./avatars/ -d ./scripts/ --mode pip --dry-run

# Compose with Smart Sync
ugckit compose -s A1 --avatar-dir ./avatars/ -d ./scripts/ --sync --dry-run

# Batch all scripts
ugckit batch -d ./scripts/ --avatar-dir ./avatars/ --dry-run

# Web UI
streamlit run streamlit_app.py

# Tests
pytest tests/ -v
```

## Architecture

```
ugckit/
├── cli.py            # Click CLI entry point
├── parser.py         # MD → Script model (regex parsing)
├── composer.py       # Timeline + FFmpeg filter_complex (overlay + PiP)
├── config.py         # YAML config loader
├── models.py         # Pydantic models (Script, Timeline, Config)
├── pip_processor.py  # PiP head extraction (basic FFmpeg + enhanced MediaPipe)
└── sync.py           # Smart Sync (Whisper transcription + keyword matching)
```

## Key Files

| File | Purpose |
|------|---------|
| [parser.py](ugckit/parser.py) | Markdown script parser with SAYS_PATTERN, CLIP_PATTERN, SCREENCAST_KEYWORD_PATTERN |
| [composer.py](ugckit/composer.py) | FFmpeg filter_complex builder, `build_timeline()`, `compose_video()`, `build_ffmpeg_filter_pip()` |
| [models.py](ugckit/models.py) | Pydantic models: Script, Segment, Timeline, Config |
| [pip_processor.py](ugckit/pip_processor.py) | Head extraction: `create_head_video()` (basic circular crop + enhanced face detection) |
| [sync.py](ugckit/sync.py) | Whisper transcription, `match_keyword_timing()`, `sync_screencast_timing()` |
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
- `SCREENCAST_KEYWORD_PATTERN`: `[screencast: filename @ word:"start phrase"-word:"end phrase" mode:pip]`

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
| 2. PiP | Done | Head extraction (basic FFmpeg + enhanced MediaPipe/rembg), PiP filter builder |
| 3. Smart Sync | Done | Whisper word-level timestamps, keyword triggers in screencast tags |

## DO NOT

1. Use `[\"']` in regex for quoted text (breaks on apostrophes)
2. Add MoviePy dependency (pure FFmpeg only)

## Related

- Scripts location: `step-saga-app/docs/product-marketing/video-prompts/`
- Avatar source: Higgsfield AI
- Output: TikTok/Reels format (9:16, <40s)
