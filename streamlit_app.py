"""UGCKit Web UI - Streamlit interface for video composition."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from ugckit.composer import (
    FFmpegError,
    build_timeline,
    compose_video,
    compose_video_with_progress,
    format_ffmpeg_cmd,
    format_timeline,
)
from ugckit.config import load_config
from ugckit.models import CompositionMode, Position
from ugckit.parser import parse_scripts_directory

st.set_page_config(
    page_title="UGCKit", page_icon="", layout="wide", initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Base ─────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

:root {
    --accent: #7c5cfc;
    --accent-soft: rgba(124, 92, 252, .12);
    --accent-glow: rgba(124, 92, 252, .25);
    --surface: rgba(255, 255, 255, .03);
    --surface-hover: rgba(255, 255, 255, .06);
    --border: rgba(255, 255, 255, .06);
    --border-accent: rgba(124, 92, 252, .3);
    --text-primary: #e8e8ed;
    --text-secondary: #7a7a85;
    --text-muted: #4a4a55;
    --success: #34d399;
    --warning: #fbbf24;
    --error: #f87171;
    --radius: 14px;
    --radius-sm: 10px;
    --radius-xs: 8px;
}

/* ── Main container ──────────────────────────────────────────────── */
.main .block-container {
    padding: 2.5rem 3rem 4rem !important;
    max-width: 1200px;
}

/* ── Sidebar ─────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0c0c16 0%, #08080f 100%) !important;
    border-right: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 2rem;
}

/* Sidebar header styling */
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
    font-size: .7rem;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin: 1.5rem 0 .75rem;
}

/* ── File uploader ───────────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    border-radius: var(--radius) !important;
}

[data-testid="stFileUploader"] section {
    background: var(--surface) !important;
    border: 1.5px dashed rgba(124, 92, 252, .2) !important;
    border-radius: var(--radius) !important;
    padding: 1.25rem !important;
    transition: all .2s ease;
}

[data-testid="stFileUploader"] section:hover {
    border-color: rgba(124, 92, 252, .45) !important;
    background: var(--accent-soft) !important;
}

[data-testid="stFileUploader"] section > div {
    color: var(--text-secondary) !important;
    font-size: .82rem !important;
}

[data-testid="stFileUploader"] button {
    background: var(--accent) !important;
    color: white !important;
    border: none !important;
    border-radius: var(--radius-xs) !important;
    font-weight: 600 !important;
    font-size: .78rem !important;
    padding: .45rem 1rem !important;
    transition: all .2s ease !important;
}

[data-testid="stFileUploader"] button:hover {
    filter: brightness(1.15) !important;
    box-shadow: 0 4px 16px var(--accent-glow) !important;
}

/* ── Tabs ────────────────────────────────────────────────────────── */
[data-baseweb="tab-list"] {
    gap: 4px !important;
    background: var(--surface) !important;
    border-radius: var(--radius) !important;
    padding: 4px !important;
    border: 1px solid var(--border) !important;
}

[data-baseweb="tab"] {
    border-radius: var(--radius-sm) !important;
    padding: .6rem 1.5rem !important;
    font-weight: 600 !important;
    font-size: .85rem !important;
    color: var(--text-secondary) !important;
    transition: all .2s ease !important;
    border: none !important;
    background: transparent !important;
}

[data-baseweb="tab"]:hover {
    background: var(--surface-hover) !important;
    color: var(--text-primary) !important;
}

[aria-selected="true"] {
    background: var(--accent) !important;
    color: white !important;
    box-shadow: 0 2px 12px var(--accent-glow) !important;
}

/* Remove default tab underline */
[data-baseweb="tab-highlight"],
[data-baseweb="tab-border"] {
    display: none !important;
}

/* ── Buttons ─────────────────────────────────────────────────────── */
.stButton > button {
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    font-size: .85rem !important;
    padding: .65rem 1.5rem !important;
    border: 1px solid var(--border) !important;
    background: var(--surface) !important;
    color: var(--text-primary) !important;
    transition: all .2s ease !important;
    backdrop-filter: blur(8px);
}

.stButton > button:hover {
    background: var(--surface-hover) !important;
    border-color: var(--border-accent) !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, .3) !important;
    transform: translateY(-1px);
}

/* Primary button */
[data-testid="stBaseButton-primary"],
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7c5cfc 0%, #5a3fd6 100%) !important;
    border: none !important;
    color: white !important;
    box-shadow: 0 4px 16px var(--accent-glow) !important;
}

[data-testid="stBaseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover {
    filter: brightness(1.1) !important;
    box-shadow: 0 6px 24px rgba(124, 92, 252, .4) !important;
}

/* Download button */
[data-testid="stDownloadButton"] button {
    background: linear-gradient(135deg, #34d399 0%, #10b981 100%) !important;
    border: none !important;
    color: white !important;
    box-shadow: 0 4px 16px rgba(52, 211, 153, .25) !important;
}

[data-testid="stDownloadButton"] button:hover {
    filter: brightness(1.1) !important;
    box-shadow: 0 6px 24px rgba(52, 211, 153, .35) !important;
}

/* ── Expander ────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    margin-bottom: .5rem;
    overflow: hidden;
}

[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    font-size: .88rem !important;
    padding: .85rem 1rem !important;
}

[data-testid="stExpander"] summary:hover {
    background: var(--surface-hover) !important;
}

/* ── Alerts ──────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    backdrop-filter: blur(8px);
}

/* Info */
.stAlert [data-testid="stAlertContentInfo"] {
    background: rgba(124, 92, 252, .06) !important;
    border-color: rgba(124, 92, 252, .15) !important;
}

/* Success */
.stAlert [data-testid="stAlertContentSuccess"] {
    background: rgba(52, 211, 153, .06) !important;
    border-color: rgba(52, 211, 153, .15) !important;
}

/* Warning */
.stAlert [data-testid="stAlertContentWarning"] {
    background: rgba(251, 191, 36, .06) !important;
    border-color: rgba(251, 191, 36, .15) !important;
}

/* Error */
.stAlert [data-testid="stAlertContentError"] {
    background: rgba(248, 113, 113, .06) !important;
    border-color: rgba(248, 113, 113, .15) !important;
}

/* ── Code blocks ─────────────────────────────────────────────────── */
[data-testid="stCode"],
.stCodeBlock {
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border) !important;
}

code {
    font-family: 'JetBrains Mono', 'SF Mono', monospace !important;
    font-size: .82rem !important;
}

/* ── Select box / radio ──────────────────────────────────────────── */
[data-baseweb="select"] {
    border-radius: var(--radius-sm) !important;
}

[data-baseweb="select"] > div {
    background: var(--surface) !important;
    border-color: var(--border) !important;
    border-radius: var(--radius-sm) !important;
}

/* Radio (horizontal) */
[data-testid="stRadio"] > div {
    gap: 8px !important;
}

[data-testid="stRadio"] label {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    padding: .5rem 1rem !important;
    transition: all .2s ease !important;
}

[data-testid="stRadio"] label:hover {
    border-color: var(--border-accent) !important;
    background: var(--surface-hover) !important;
}

/* ── Slider ──────────────────────────────────────────────────────── */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
    background: var(--accent) !important;
    border-color: var(--accent) !important;
}

/* ── Progress bar ────────────────────────────────────────────────── */
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #7c5cfc, #5a3fd6) !important;
    border-radius: 100px !important;
}

/* ── Divider ─────────────────────────────────────────────────────── */
[data-testid="stDivider"],
hr {
    border-color: var(--border) !important;
    opacity: 1 !important;
}

/* ── Checkbox ────────────────────────────────────────────────────── */
[data-testid="stCheckbox"] span[data-baseweb="checkbox"] {
    border-radius: 5px !important;
}

/* ── Scrollbar ───────────────────────────────────────────────────── */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

::-webkit-scrollbar-track {
    background: transparent;
}

::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, .08);
    border-radius: 100px;
}

::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, .15);
}

/* ── Metric cards ────────────────────────────────────────────────── */
[data-testid="stMetricValue"] {
    font-weight: 700 !important;
    font-size: 1.8rem !important;
}

/* ── Custom classes ──────────────────────────────────────────────── */
.hero-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    background: var(--accent-soft);
    border: 1px solid rgba(124, 92, 252, .2);
    border-radius: 100px;
    font-size: .75rem;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: .02em;
    margin-bottom: .5rem;
}

.hero-title {
    font-size: 2rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1.15;
    letter-spacing: -.03em;
    margin: .25rem 0 .5rem;
}

.hero-subtitle {
    font-size: .95rem;
    color: var(--text-secondary);
    line-height: 1.5;
    margin-bottom: 1.5rem;
    max-width: 600px;
}

.section-label {
    font-size: .7rem;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: .5rem;
}

.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
}

.card-highlight {
    background: var(--accent-soft);
    border: 1px solid rgba(124, 92, 252, .15);
    border-radius: var(--radius);
    padding: 1.25rem;
}

.stat-row {
    display: flex;
    gap: 1rem;
    margin: 1rem 0;
}

.stat-item {
    flex: 1;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 1rem;
    text-align: center;
}

.stat-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--accent);
}

.stat-label {
    font-size: .75rem;
    color: var(--text-secondary);
    margin-top: .25rem;
}

.segment-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: .85rem 1rem;
    margin-bottom: .5rem;
}

.segment-header {
    display: flex;
    align-items: center;
    gap: .5rem;
    margin-bottom: .35rem;
}

.segment-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    background: var(--accent-soft);
    border-radius: 8px;
    font-size: .75rem;
    font-weight: 700;
    color: var(--accent);
}

.segment-duration {
    font-size: .75rem;
    color: var(--text-muted);
    margin-left: auto;
}

.segment-text {
    font-size: .85rem;
    color: var(--text-secondary);
    line-height: 1.5;
    padding-left: 2.25rem;
}

.screencast-tag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    background: rgba(52, 211, 153, .08);
    border: 1px solid rgba(52, 211, 153, .15);
    border-radius: 6px;
    font-size: .72rem;
    font-weight: 500;
    color: #34d399;
    margin-left: 2.25rem;
    margin-top: .25rem;
    font-family: 'JetBrains Mono', monospace;
}

.workflow-steps {
    display: flex;
    gap: .75rem;
    margin: 1rem 0 1.5rem;
}

.workflow-step {
    flex: 1;
    display: flex;
    align-items: center;
    gap: .5rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: .75rem 1rem;
    font-size: .82rem;
    color: var(--text-secondary);
}

.workflow-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    min-width: 24px;
    background: var(--accent-soft);
    border-radius: 7px;
    font-size: .72rem;
    font-weight: 700;
    color: var(--accent);
}

.file-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: .75rem;
    font-weight: 500;
}

.file-status-ok {
    background: rgba(52, 211, 153, .08);
    color: #34d399;
    border: 1px solid rgba(52, 211, 153, .12);
}

.file-status-warn {
    background: rgba(251, 191, 36, .08);
    color: #fbbf24;
    border: 1px solid rgba(251, 191, 36, .12);
}

.sidebar-logo {
    font-size: 1.1rem;
    font-weight: 800;
    letter-spacing: -.03em;
    color: var(--text-primary);
    margin-bottom: .15rem;
}

.sidebar-version {
    font-size: .72rem;
    color: var(--text-muted);
    margin-bottom: 1.5rem;
}

.sidebar-section {
    margin-bottom: 1.25rem;
}

.sidebar-section-title {
    font-size: .68rem;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: .6rem;
}

.upload-counter {
    font-size: .72rem;
    color: var(--text-muted);
    margin-top: .35rem;
}

/* ── Hide default streamlit branding ─────────────────────────────── */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}

/* ── Animation ───────────────────────────────────────────────────── */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

.element-container {
    animation: fadeIn .35s ease-out;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "tmp_dir" not in st.session_state:
    st.session_state.tmp_dir = Path(tempfile.mkdtemp(prefix="ugckit_"))

TMP = st.session_state.tmp_dir
SCRIPTS_DIR = TMP / "scripts"
AVATARS_DIR = TMP / "avatars"
SCREENCASTS_DIR = TMP / "screencasts"
OUTPUT_DIR = TMP / "output"

for d in (SCRIPTS_DIR, AVATARS_DIR, SCREENCASTS_DIR, OUTPUT_DIR):
    d.mkdir(exist_ok=True)


def save_uploads(files, target_dir: Path) -> list[Path]:
    """Write uploaded files to disk and return paths."""
    paths = []
    for f in files:
        dest = target_dir / f.name
        dest.write_bytes(f.getbuffer())
        paths.append(dest)
    return sorted(paths)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="sidebar-logo">UGCKit</div>'
        '<div class="sidebar-version">Video Composer v1.0</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sidebar-section-title">Scripts</div>', unsafe_allow_html=True)
    script_files = st.file_uploader(
        "Скрипты",
        type=["md"],
        accept_multiple_files=True,
        help='Markdown со скриптами: ### Script A1: "Название"',
        label_visibility="collapsed",
    )
    if script_files:
        save_uploads(script_files, SCRIPTS_DIR)
        st.markdown(
            f'<div class="upload-counter">{len(script_files)} loaded</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="sidebar-section-title">Avatars (.mp4)</div>', unsafe_allow_html=True)
    avatar_files = st.file_uploader(
        "Аватары",
        type=["mp4"],
        accept_multiple_files=True,
        help="AI avatar videos, one per segment",
        label_visibility="collapsed",
    )
    if avatar_files:
        save_uploads(avatar_files, AVATARS_DIR)
        st.markdown(
            f'<div class="upload-counter">{len(avatar_files)} loaded</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="sidebar-section-title">Screencasts (.mp4)</div>',
        unsafe_allow_html=True,
    )
    screencast_files = st.file_uploader(
        "Скринкасты",
        type=["mp4"],
        accept_multiple_files=True,
        help="App screen recordings for overlay",
        label_visibility="collapsed",
    )
    if screencast_files:
        save_uploads(screencast_files, SCREENCASTS_DIR)
        st.markdown(
            f'<div class="upload-counter">{len(screencast_files)} loaded</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown(
        '<div style="font-size:.72rem; color:var(--text-muted);">'
        "Files from disk are also detected automatically."
        "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Parse scripts
# ---------------------------------------------------------------------------
all_scripts = parse_scripts_directory(SCRIPTS_DIR)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_scripts, tab_compose, tab_settings = st.tabs(["Scripts", "Compose", "Settings"])

# ---------------------------------------------------------------------------
# Settings tab (load first so compose uses latest values)
# ---------------------------------------------------------------------------
with tab_settings:
    st.markdown(
        '<div class="hero-badge">Configuration</div>'
        '<div class="hero-title">Settings</div>'
        '<div class="hero-subtitle">Fine-tune composition, output, and sync parameters.</div>',
        unsafe_allow_html=True,
    )

    cfg = load_config()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<div class="section-label">Overlay Mode</div>',
            unsafe_allow_html=True,
        )
        overlay_scale = st.slider(
            "Screencast scale",
            0.1,
            0.8,
            cfg.composition.overlay.scale,
            0.05,
        )
        overlay_position = st.selectbox(
            "Screencast position",
            [p.value for p in Position],
            index=[p.value for p in Position].index(cfg.composition.overlay.position.value),
        )
        overlay_margin = st.number_input(
            "Margin (px)",
            0,
            200,
            cfg.composition.overlay.margin,
        )

        st.markdown("---")
        st.markdown(
            '<div class="section-label">Picture-in-Picture</div>',
            unsafe_allow_html=True,
        )
        pip_head_scale = st.slider(
            "Head size",
            0.1,
            0.5,
            cfg.composition.pip.head_scale,
            0.05,
        )
        pip_head_position = st.selectbox(
            "Head position",
            [p.value for p in Position],
            index=[p.value for p in Position].index(cfg.composition.pip.head_position.value),
        )

    with col2:
        st.markdown(
            '<div class="section-label">Output</div>',
            unsafe_allow_html=True,
        )
        crf = st.slider(
            "CRF (quality)",
            15,
            35,
            cfg.output.crf,
            help="Lower = better quality, larger file",
        )
        codec = st.selectbox(
            "Codec",
            ["libx264", "libx265"],
            index=0 if cfg.output.codec == "libx264" else 1,
        )

        st.markdown("---")
        st.markdown(
            '<div class="section-label">Audio</div>',
            unsafe_allow_html=True,
        )
        normalize_audio = st.checkbox(
            "Loudness normalization",
            value=cfg.audio.normalize,
        )
        target_loudness = st.slider(
            "Target loudness (LUFS)",
            -24,
            -8,
            cfg.audio.target_loudness,
            help="Social media standard: -14 LUFS",
        )

        st.markdown("---")
        st.markdown(
            '<div class="section-label">Smart Sync (Whisper)</div>',
            unsafe_allow_html=True,
        )
        enable_sync = st.checkbox(
            "Auto-sync screencasts",
            value=False,
            help="Detect screencast timing via speech keywords",
        )
        sync_model = st.selectbox(
            "Whisper model",
            ["tiny", "base", "small", "medium", "large"],
            index=1,
        )

    st.markdown("---")
    col3, col4 = st.columns(2)
    with col3:
        st.markdown(
            '<div class="section-label">Split Screen</div>',
            unsafe_allow_html=True,
        )
        split_avatar_side = st.selectbox(
            "Avatar side",
            ["left", "right"],
            help="Which side the avatar appears on",
        )
        split_ratio = st.slider(
            "Split ratio",
            0.3,
            0.7,
            0.5,
            0.05,
            help="Proportion of width for avatar side",
        )

        st.markdown("---")
        st.markdown(
            '<div class="section-label">Green Screen</div>',
            unsafe_allow_html=True,
        )
        gs_avatar_scale = st.slider(
            "Avatar scale",
            0.3,
            1.0,
            0.8,
            0.05,
            help="Size of transparent avatar overlay",
        )
        gs_avatar_position = st.selectbox(
            "Avatar position (GS)",
            [p.value for p in Position],
            index=[p.value for p in Position].index("bottom-right"),
        )

    with col4:
        st.markdown(
            '<div class="section-label">Auto-Subtitles</div>',
            unsafe_allow_html=True,
        )
        enable_subtitles = st.checkbox(
            "Enable subtitles",
            value=False,
            help="Generate karaoke-style subtitles from speech",
        )
        subtitle_font_size = st.slider(
            "Subtitle font size",
            24,
            96,
            48,
            help="Font size for subtitles",
        )
        subtitle_model = st.selectbox(
            "Subtitle Whisper model",
            ["tiny", "base", "small", "medium", "large"],
            index=1,
        )

        st.markdown("---")
        st.markdown(
            '<div class="section-label">Background Music</div>',
            unsafe_allow_html=True,
        )
        music_file_upload = st.file_uploader(
            "Music file",
            type=["mp3", "wav", "m4a", "ogg"],
            help="Background music track",
        )
        music_volume = st.slider(
            "Music volume",
            0.0,
            1.0,
            0.15,
            0.05,
            help="Volume level for background music",
        )
        music_fade_out = st.slider(
            "Fade-out (sec)",
            0.0,
            10.0,
            2.0,
            0.5,
            help="Fade-out duration at the end",
        )

    # Save music upload to disk
    music_path = None
    if music_file_upload:
        music_path = TMP / music_file_upload.name
        music_path.write_bytes(music_file_upload.getbuffer())

    # Apply settings to config
    cfg.composition.overlay.scale = overlay_scale
    cfg.composition.overlay.position = Position(overlay_position)
    cfg.composition.overlay.margin = overlay_margin
    cfg.composition.pip.head_scale = pip_head_scale
    cfg.composition.pip.head_position = Position(pip_head_position)
    cfg.composition.split.avatar_side = split_avatar_side
    cfg.composition.split.split_ratio = split_ratio
    cfg.composition.greenscreen.avatar_scale = gs_avatar_scale
    cfg.composition.greenscreen.avatar_position = Position(gs_avatar_position)
    cfg.output.crf = crf
    cfg.output.codec = codec
    cfg.audio.normalize = normalize_audio
    cfg.audio.target_loudness = target_loudness
    if enable_subtitles:
        cfg.subtitles.enabled = True
        cfg.subtitles.font_size = subtitle_font_size
        cfg.subtitles.whisper_model = subtitle_model
    if music_path:
        cfg.music.enabled = True
        cfg.music.file = music_path
        cfg.music.volume = music_volume
        cfg.music.fade_out_duration = music_fade_out

# ---------------------------------------------------------------------------
# Scripts tab
# ---------------------------------------------------------------------------
with tab_scripts:
    st.markdown(
        '<div class="hero-badge">Library</div>'
        '<div class="hero-title">Scripts</div>'
        '<div class="hero-subtitle">'
        "Upload .md files via the sidebar to populate your script library."
        "</div>",
        unsafe_allow_html=True,
    )

    if not all_scripts:
        st.markdown(
            '<div class="card-highlight" style="margin-bottom:1rem;">'
            '<div style="font-size:.85rem; color:var(--text-secondary); line-height:1.6;">'
            "No scripts loaded yet. Drop <code>.md</code> files into the sidebar.<br><br>"
            "<strong>Expected format:</strong>"
            "</div>"
            '<div style="margin-top:.75rem; padding:.75rem 1rem; background:rgba(0,0,0,.2); '
            "border-radius:8px; font-family:'JetBrains Mono',monospace; font-size:.78rem; "
            'color:var(--text-secondary); line-height:1.7;">'
            '### Script A1: "Title"<br>'
            "**Clip 1 (8s):**<br>"
            'Says: "Voiceover text"<br>'
            "[screencast: app @ 1.5-5.0 mode:overlay]"
            "</div></div>",
            unsafe_allow_html=True,
        )
    else:
        # Stats row
        total_segments = sum(len(s.segments) for s in all_scripts)
        total_duration = sum(s.total_duration for s in all_scripts)
        st.markdown(
            f'<div class="stat-row">'
            f'<div class="stat-item"><div class="stat-value">{len(all_scripts)}</div>'
            f'<div class="stat-label">Scripts</div></div>'
            f'<div class="stat-item"><div class="stat-value">{total_segments}</div>'
            f'<div class="stat-label">Segments</div></div>'
            f'<div class="stat-item"><div class="stat-value">{total_duration:.0f}s</div>'
            f'<div class="stat-label">Total Duration</div></div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        for script in all_scripts:
            with st.expander(
                f"{script.script_id}: {script.title}  \u2014  "
                f"{len(script.segments)} clips, ~{script.total_duration:.0f}s"
            ):
                for seg in script.segments:
                    # Build screencast tags
                    sc_html = ""
                    for sc in seg.screencasts:
                        mode_label = "PiP" if sc.mode == CompositionMode.PIP else "Overlay"
                        if sc.start_keyword:
                            sc_html += (
                                f'<div class="screencast-tag">'
                                f'{sc.file} @ "{sc.start_keyword}"-"{sc.end_keyword}" '
                                f"({mode_label})</div>"
                            )
                        else:
                            sc_html += (
                                f'<div class="screencast-tag">'
                                f"{sc.file} @ {sc.start}s\u2013{sc.end}s ({mode_label})</div>"
                            )

                    st.markdown(
                        f'<div class="segment-card">'
                        f'<div class="segment-header">'
                        f'<div class="segment-badge">{seg.id}</div>'
                        f'<div style="font-weight:600; font-size:.85rem;">Clip {seg.id}</div>'
                        f'<div class="segment-duration">{seg.duration:.0f}s</div>'
                        f"</div>"
                        f'<div class="segment-text">{seg.text}</div>'
                        f"{sc_html}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

# ---------------------------------------------------------------------------
# Compose tab
# ---------------------------------------------------------------------------
with tab_compose:
    st.markdown(
        '<div class="hero-badge">Production</div>'
        '<div class="hero-title">Compose</div>'
        '<div class="hero-subtitle">'
        "Select a script, match avatars, preview the timeline, and render."
        "</div>",
        unsafe_allow_html=True,
    )

    # Workflow steps
    st.markdown(
        '<div class="workflow-steps">'
        '<div class="workflow-step"><div class="workflow-num">1</div>Upload script</div>'
        '<div class="workflow-step"><div class="workflow-num">2</div>Upload avatars</div>'
        '<div class="workflow-step"><div class="workflow-num">3</div>Preview timeline</div>'
        '<div class="workflow-step"><div class="workflow-num">4</div>Render video</div>'
        "</div>",
        unsafe_allow_html=True,
    )

    if not all_scripts:
        st.warning("Upload scripts first via the sidebar.")
    else:
        script_options = {f"{s.script_id}: {s.title}": s for s in all_scripts}
        selected_label = st.selectbox("Script", list(script_options.keys()))
        selected_script = script_options[selected_label]

        # Composition mode selector
        mode_options = {
            "Overlay": CompositionMode.OVERLAY,
            "PiP": CompositionMode.PIP,
            "Split Screen": CompositionMode.SPLIT,
            "Green Screen": CompositionMode.GREENSCREEN,
        }
        comp_mode = st.radio(
            "Composition mode",
            list(mode_options.keys()),
            horizontal=True,
            help="Overlay: screencast in corner. PiP: head cutout. Split: side-by-side. Green Screen: bg removed.",
        )
        selected_mode = mode_options[comp_mode]

        # Avatar mapping
        available_avatars = sorted(AVATARS_DIR.glob("*.mp4"))

        segs_count = len(selected_script.segments)
        avs_count = len(available_avatars)
        status_class = "file-status-ok" if avs_count >= segs_count else "file-status-warn"
        status_icon = "\u2713" if avs_count >= segs_count else "\u26a0"

        st.markdown(
            f'<div style="display:flex; gap:1rem; align-items:center; margin:.75rem 0;">'
            f'<div class="file-status {status_class}">{status_icon} {avs_count} avatars</div>'
            f'<div style="font-size:.82rem; color:var(--text-muted);">'
            f"Needed: {segs_count} segments</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Auto-match: try prefix match, else assign in order
        sid = selected_script.script_id.upper()
        prefix_matched = sorted([f for f in available_avatars if f.stem.upper().startswith(sid)])
        matched_avatars = prefix_matched if prefix_matched else available_avatars

        if matched_avatars:
            with st.expander("Avatar mapping", expanded=False):
                for i, seg in enumerate(selected_script.segments):
                    if i < len(matched_avatars):
                        st.markdown(
                            f'<div style="display:flex; align-items:center; gap:.5rem; '
                            f'padding:.4rem 0; font-size:.82rem;">'
                            f'<div class="segment-badge">{seg.id}</div>'
                            f'<span style="color:var(--text-secondary);">\u2192</span>'
                            f'<span style="color:var(--text-primary);">'
                            f"{matched_avatars[i].name}</span></div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.warning(f"Segment {seg.id} \u2014 no avatar available")

        col_preview, col_compose = st.columns(2)

        # Preview timeline
        with col_preview:
            if st.button("Preview timeline", use_container_width=True):
                if not matched_avatars:
                    st.error("No avatars available.")
                else:
                    if selected_mode != CompositionMode.OVERLAY:
                        for seg in selected_script.segments:
                            for sc in seg.screencasts:
                                sc.mode = selected_mode

                    script_to_use = selected_script
                    if enable_sync:
                        try:
                            from ugckit.sync import sync_screencast_timing

                            with st.spinner("Running Whisper sync..."):
                                script_to_use = sync_screencast_timing(
                                    selected_script, matched_avatars, sync_model
                                )
                        except Exception as e:
                            st.warning(f"Sync failed: {e}")

                    output_path = OUTPUT_DIR / f"{script_to_use.script_id}.mp4"
                    try:
                        timeline = build_timeline(
                            script=script_to_use,
                            avatar_clips=matched_avatars,
                            screencasts_dir=SCREENCASTS_DIR,
                            output_path=output_path,
                        )
                        st.code(format_timeline(timeline))

                        cmd = compose_video(timeline, cfg, dry_run=True)
                        with st.expander("FFmpeg command"):
                            st.code(format_ffmpeg_cmd(cmd), language="bash")
                    except (ValueError, FFmpegError) as e:
                        st.error(str(e))

        # Compose video
        with col_compose:
            if st.button("Render video", type="primary", use_container_width=True):
                if not matched_avatars:
                    st.error("No avatars available.")
                else:
                    if selected_mode != CompositionMode.OVERLAY:
                        for seg in selected_script.segments:
                            for sc in seg.screencasts:
                                sc.mode = selected_mode

                    script_to_use = selected_script
                    if enable_sync:
                        try:
                            from ugckit.sync import sync_screencast_timing

                            with st.spinner("Running Whisper sync..."):
                                script_to_use = sync_screencast_timing(
                                    selected_script, matched_avatars, sync_model
                                )
                        except Exception as e:
                            st.warning(f"Sync failed: {e}")

                    output_path = OUTPUT_DIR / f"{script_to_use.script_id}.mp4"
                    try:
                        timeline = build_timeline(
                            script=script_to_use,
                            avatar_clips=matched_avatars,
                            screencasts_dir=SCREENCASTS_DIR,
                            output_path=output_path,
                        )

                        # Pre-processing per mode
                        head_videos = None
                        transparent_avatars = None

                        if selected_mode == CompositionMode.PIP:
                            try:
                                from ugckit.pip_processor import create_head_video

                                head_videos = []
                                with st.spinner("Generating PiP head cutouts..."):
                                    for i, avatar in enumerate(matched_avatars):
                                        head_out = OUTPUT_DIR / f"head_{i}.webm"
                                        head_path = create_head_video(
                                            avatar, head_out, cfg.composition.pip
                                        )
                                        head_videos.append(head_path)
                            except Exception as e:
                                st.warning(f"PiP head extraction failed: {e}")
                                head_videos = None

                        elif selected_mode == CompositionMode.GREENSCREEN:
                            try:
                                from ugckit.pip_processor import create_transparent_avatar

                                transparent_avatars = []
                                gs_cfg = cfg.composition.greenscreen
                                with st.spinner("Removing avatar backgrounds..."):
                                    for i, avatar in enumerate(matched_avatars):
                                        out = OUTPUT_DIR / f"transparent_{i}.webm"
                                        ta = create_transparent_avatar(
                                            avatar,
                                            out,
                                            scale=gs_cfg.avatar_scale,
                                            output_width=cfg.output.resolution[0],
                                        )
                                        transparent_avatars.append(ta)
                            except Exception as e:
                                st.warning(f"Green screen processing failed: {e}")
                                transparent_avatars = None

                        # Generate subtitles
                        subtitle_file = None
                        if cfg.subtitles.enabled:
                            try:
                                from ugckit.subtitles import generate_subtitle_file

                                with st.spinner("Generating subtitles..."):
                                    subtitle_file = generate_subtitle_file(
                                        timeline, matched_avatars, cfg
                                    )
                            except Exception as e:
                                st.warning(f"Subtitle generation failed: {e}")

                        progress_bar = st.progress(0.0, text="Rendering...")
                        result_path = compose_video_with_progress(
                            timeline,
                            cfg,
                            progress_callback=lambda p: progress_bar.progress(
                                p, text=f"Rendering... {p:.0%}"
                            ),
                            head_videos=head_videos,
                            transparent_avatars=transparent_avatars,
                            subtitle_file=subtitle_file,
                            music_file=music_path,
                        )
                        st.success(f"Done \u2014 {result_path.name}")

                        with open(result_path, "rb") as vf:
                            st.download_button(
                                "Download video",
                                data=vf,
                                file_name=result_path.name,
                                mime="video/mp4",
                                use_container_width=True,
                            )
                    except (ValueError, FFmpegError) as e:
                        st.error(str(e))

        # Batch compose
        st.markdown("---")
        if st.button("Batch render all scripts"):
            for script in all_scripts:
                s_id = script.script_id.upper()
                s_avatars = sorted(
                    [f for f in available_avatars if f.stem.upper().startswith(s_id)]
                )
                if not s_avatars:
                    s_avatars = available_avatars if len(all_scripts) == 1 else []

                if not s_avatars:
                    st.warning(f"[{script.script_id}] No matching avatars, skipped.")
                    continue

                output_path = OUTPUT_DIR / f"{script.script_id}.mp4"
                try:
                    timeline = build_timeline(
                        script=script,
                        avatar_clips=s_avatars,
                        screencasts_dir=SCREENCASTS_DIR,
                        output_path=output_path,
                    )
                    progress_bar = st.progress(0.0, text=f"Rendering {script.script_id}...")
                    result_path = compose_video_with_progress(
                        timeline,
                        cfg,
                        progress_callback=lambda p, sid=script.script_id: progress_bar.progress(
                            p, text=f"Rendering {sid}... {p:.0%}"
                        ),
                    )
                    st.success(f"[{script.script_id}] Done")
                    with open(result_path, "rb") as vf:
                        st.download_button(
                            f"Download {result_path.name}",
                            data=vf,
                            file_name=result_path.name,
                            mime="video/mp4",
                        )
                except (ValueError, FFmpegError) as e:
                    st.error(f"[{script.script_id}] {e}")
