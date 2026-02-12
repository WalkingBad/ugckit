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

# Dry-run split screen
ugckit compose -s A1 --avatar-dir ./avatars/ -d ./scripts/ --mode split --dry-run

# Dry-run green screen
ugckit compose -s A1 --avatar-dir ./avatars/ -d ./scripts/ --mode greenscreen --dry-run

# Compose with Smart Sync
ugckit compose -s A1 --avatar-dir ./avatars/ -d ./scripts/ --sync --dry-run

# Compose with background music
ugckit compose -s A1 --avatar-dir ./avatars/ -d ./scripts/ --music bg.mp3 --dry-run

# Compose with auto-subtitles
ugckit compose -s A1 --avatar-dir ./avatars/ -d ./scripts/ --subtitles --dry-run

# Combined: split + music + subtitles
ugckit compose -s A1 --avatar-dir ./avatars/ -d ./scripts/ --mode split --subtitles --music bg.mp3 --dry-run

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
├── composer.py       # Timeline + FFmpeg filter_complex (overlay/PiP/split/greenscreen)
├── config.py         # YAML config loader
├── models.py         # Pydantic models (Script, Timeline, Config) with Field validators
├── pipeline.py       # Shared pipeline ops (PiP, greenscreen, sync, subtitles)
├── pip_processor.py  # PiP head extraction + green screen transparent avatar
├── subtitles.py      # Auto-subtitles (Whisper → ASS karaoke)
└── sync.py           # Smart Sync (Whisper transcription + keyword matching + model cache)
```

## Key Files

| File | Purpose |
|------|---------|
| [parser.py](ugckit/parser.py) | Markdown script parser with SAYS_PATTERN, CLIP_PATTERN, SCREENCAST_KEYWORD_PATTERN |
| [composer.py](ugckit/composer.py) | FFmpeg filter_complex builders for all 4 modes + `_finalize_filter()` + `_FILTER_BUILDERS` registry |
| [models.py](ugckit/models.py) | Pydantic models with Field validators: Script, Segment, Timeline, Config, SplitConfig, GreenScreenConfig, SubtitleConfig, MusicConfig |
| [pipeline.py](ugckit/pipeline.py) | Shared pipeline: `prepare_pip_videos()`, `prepare_greenscreen_videos()`, `apply_sync()`, `generate_subtitles()` |
| [pip_processor.py](ugckit/pip_processor.py) | `create_head_video()` (PiP) + `create_transparent_avatar()` (green screen) |
| [subtitles.py](ugckit/subtitles.py) | Whisper transcription → ASS subtitle file with karaoke `\kf` tags |
| [sync.py](ugckit/sync.py) | Whisper transcription, `match_keyword_timing()`, `sync_screencast_timing()` |
| [ugckit/config/default.yaml](ugckit/config/default.yaml) | Default composition settings |

## Data Flow

```
Markdown Script → parser.py → Script model
                                    ↓
Avatar clips + Script → composer.py → Timeline
                                           ↓
Timeline + Config → FFmpeg filter_complex → Output video
                         ↓
              wrap_with_post_processing():
                [vout] → ass subtitle overlay → [vout]
                [aout] → amix with music      → [aout]
```

## Composition Modes

| Mode | Description | Filter builder |
|------|-------------|----------------|
| `overlay` | Avatar fullscreen, screencast in corner | `build_ffmpeg_filter_overlay()` |
| `pip` | Screencast fullscreen, head cutout in corner | `build_ffmpeg_filter_pip()` |
| `split` | Avatar left, screencast right (hstack) | `build_ffmpeg_filter_split()` |
| `greenscreen` | Avatar bg removed, composite over screencast | `build_ffmpeg_filter_greenscreen()` |

Post-processing (subtitles + music) is orthogonal — applied after any mode's filter chain.

## Patterns

### Regex Patterns (parser.py)
- `SCRIPT_HEADER_PATTERN`: `### Script A1: "Title"`
- `CLIP_PATTERN`: `**Clip 1 (VEO 8s):**`
- `SAYS_PATTERN`: `Says: "text with apostrophes allowed"`
- `SCREENCAST_PATTERN`: `[screencast: filename @ start-end mode:split]`
- `SCREENCAST_KEYWORD_PATTERN`: `[screencast: filename @ word:"start phrase"-word:"end phrase" mode:pip]`
- Supported modes: `overlay`, `pip`, `split`, `greenscreen`

### FFmpeg Composition (composer.py)
- Scale avatars to 1080x1920
- Concat video streams: `[av0][av1]concat=n=2:v=1:a=0[base]`
- Overlay screencasts with timing: `overlay=enable='between(t,1.5,4.0)'`
- Audio normalization: `loudnorm=I=-14:TP=-1.5:LRA=11`
- Music mixing: `aloop` + `afade` + `amix`
- Subtitles: `ass='path.ass'` filter

## Config Structure

```yaml
composition:
  overlay:
    scale: 0.4           # screencast size (40% of width)
    position: bottom-right
    margin: 50
  pip:
    head_scale: 0.25
    head_position: top-right
  split:
    avatar_side: left     # "left" or "right"
    split_ratio: 0.5      # 0.5 = 50/50
  greenscreen:
    avatar_scale: 0.8
    avatar_position: bottom-right

output:
  resolution: [1080, 1920]  # 9:16 vertical
  fps: 30
  codec: libx264
  crf: 23

audio:
  normalize: true
  target_loudness: -14   # LUFS

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
```

## Development Phases

| Phase | Status | Features |
|-------|--------|----------|
| 1. MVP | Done | CLI, parser, overlay mode, --dry-run |
| 2. PiP | Done | Head extraction (basic FFmpeg + enhanced MediaPipe/rembg), PiP filter builder |
| 3. Smart Sync | Done | Whisper word-level timestamps, keyword triggers in screencast tags |
| 4. Split + GS + Subs + Music | Done | Split screen, green screen, auto-subtitles (ASS karaoke), background music |

## DO NOT

1. Use `[\"']` in regex for quoted text (breaks on apostrophes)
2. Add MoviePy dependency (pure FFmpeg only)

## Related

- Scripts location: `step-saga-app/docs/product-marketing/video-prompts/`
- Avatar source: Higgsfield AI
- Output: TikTok/Reels format (9:16, <40s)
