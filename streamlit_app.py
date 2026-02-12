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
from ugckit.pipeline import (
    apply_sync,
    generate_subtitles,
    prepare_greenscreen_videos,
    prepare_pip_videos,
)

st.set_page_config(
    page_title="UGCKit — Сборка UGC видео",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POSITION_LABELS = {
    "top-left": "Вверху слева",
    "top-right": "Вверху справа",
    "bottom-left": "Внизу слева",
    "bottom-right": "Внизу справа",
}
POSITION_OPTIONS = list(POSITION_LABELS.keys())
POSITION_DISPLAY = list(POSITION_LABELS.values())

MODE_DESCRIPTIONS = {
    "Оверлей": "Аватар на весь экран, скринкаст в углу",
    "PiP": "Скринкаст на весь экран, голова аватара в углу",
    "Сплит": "Аватар и скринкаст рядом (50/50)",
    "Хромакей": "Фон аватара удалён, фигура поверх скринкаста",
}

MODE_MAP = {
    "Оверлей": CompositionMode.OVERLAY,
    "PiP": CompositionMode.PIP,
    "Сплит": CompositionMode.SPLIT,
    "Хромакей": CompositionMode.GREENSCREEN,
}

MODE_LABEL_MAP = {
    CompositionMode.PIP: "PiP",
    CompositionMode.OVERLAY: "Оверлей",
    CompositionMode.SPLIT: "Сплит",
    CompositionMode.GREENSCREEN: "Хромакей",
}


def _pos_selectbox(label: str, default: str, help_text: str, key: str | None = None):
    """Position selectbox with Russian labels."""
    idx = POSITION_OPTIONS.index(default) if default in POSITION_OPTIONS else 0
    sel = st.selectbox(
        label,
        POSITION_DISPLAY,
        index=idx,
        help=help_text,
        key=key,
    )
    return POSITION_OPTIONS[POSITION_DISPLAY.index(sel)]


# ---------------------------------------------------------------------------
# Custom CSS — Brutalist Swiss Style (dark theme + purple accent)
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Base ─────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    -webkit-font-smoothing: antialiased;
}

:root {
    --accent: #7c5cfc;
    --accent-soft: rgba(124, 92, 252, .12);
    --accent-glow: rgba(124, 92, 252, .25);
    --accent-bright: #9d85fd;
    --accent-deep: #5a3fd6;
    --surface: rgba(255, 255, 255, .03);
    --surface-hover: rgba(255, 255, 255, .06);
    --border: rgba(255, 255, 255, .06);
    --border-accent: rgba(124, 92, 252, .3);
    --text-primary: #e8e8ed;
    --text-secondary: #8a8a95;
    --text-muted: #6a6a75;
    --success: #34d399;
    --warning: #fbbf24;
    --error: #f87171;
    --radius: 14px;
    --radius-sm: 10px;
    --radius-xs: 8px;
}

/* ── Noise texture overlay ───────────────────────────────────────── */
.noise-overlay {
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 9999;
    opacity: 0.04;
    mix-blend-mode: overlay;
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
    padding-top: 1.5rem;
}

/* Tighter sidebar spacing */
[data-testid="stSidebar"] .stElementContainer {
    margin-bottom: 0 !important;
}

[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
    gap: .35rem !important;
}

/* Sidebar header styling */
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
    font-size: .7rem;
    font-weight: 700;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin: 1rem 0 .5rem;
}

/* ── Brutalist sidebar branding ──────────────────────────────────── */
.sidebar-logo {
    font-size: 1.3rem;
    font-weight: 300;
    letter-spacing: .08em;
    color: var(--text-primary);
    margin-bottom: .15rem;
}

.sidebar-logo .dot {
    color: var(--accent);
    margin: 0 1px;
}

.sidebar-version {
    font-size: .65rem;
    font-weight: 300;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 1.25rem;
}

/* ── Numbered upload blocks ──────────────────────────────────────── */
.upload-block {
    border-bottom: 1px solid var(--border);
    padding: .85rem 0 .5rem;
}

.upload-block:last-child {
    border-bottom: none;
}

.upload-block-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: .3rem;
}

.upload-block-title {
    font-size: .92rem;
    font-weight: 300;
    letter-spacing: -0.01em;
    color: var(--text-primary);
}

.upload-block-title .num-index {
    font-weight: 300;
    color: var(--text-muted);
    margin-right: 6px;
    font-size: .85rem;
}

.upload-block-status {
    font-size: .6rem;
    font-weight: 500;
    letter-spacing: .08em;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 3px;
}

.upload-block-status.required {
    color: var(--accent);
    background: var(--accent-soft);
}

.upload-block-status.optional {
    color: var(--text-muted);
    background: rgba(255,255,255,.03);
}

.upload-block-meta {
    font-size: .68rem;
    letter-spacing: .03em;
    text-transform: uppercase;
    color: var(--text-muted);
    opacity: .7;
    margin-bottom: .2rem;
}

.upload-block-hint {
    font-size: .72rem;
    color: var(--text-secondary);
    line-height: 1.4;
    margin-bottom: .35rem;
    opacity: .8;
}

.upload-counter {
    font-size: .72rem;
    color: var(--text-muted);
    margin-top: .15rem;
}

/* ── File uploader ───────────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    border-radius: var(--radius) !important;
    margin-bottom: .25rem !important;
}

/* Dropzone section (the dashed box) */
[data-testid="stFileUploaderDropzone"] {
    background: var(--surface) !important;
    border: 1px dashed rgba(124, 92, 252, .15) !important;
    border-radius: var(--radius-xs) !important;
    padding: .65rem .75rem !important;
    transition: all .2s ease;
    min-height: auto !important;
}

[data-testid="stFileUploaderDropzone"]:hover {
    border-color: rgba(124, 92, 252, .45) !important;
    background: var(--accent-soft) !important;
}

/* Uploader button base styles */
[data-testid="stFileUploaderDropzone"] button {
    background: var(--accent) !important;
    color: white !important;
    border: none !important;
    border-radius: var(--radius-xs) !important;
    font-weight: 600 !important;
    padding: .35rem .75rem !important;
    font-size: .78rem !important;
    transition: all .2s ease !important;
}

[data-testid="stFileUploaderDropzone"] button:hover {
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
    padding: .75rem 1.5rem !important;
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
    transform: translateY(-2px);
}

/* Primary button — gradient hover like macket */
[data-testid="stBaseButton-primary"],
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #7c5cfc 0%, #5a3fd6 100%) !important;
    border: none !important;
    color: white !important;
    box-shadow: 0 4px 16px var(--accent-glow) !important;
    text-transform: uppercase !important;
    letter-spacing: .05em !important;
    font-weight: 500 !important;
    position: relative;
    overflow: hidden;
    transition: all .25s ease !important;
}

[data-testid="stBaseButton-primary"]:hover,
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(45deg, var(--accent-bright), var(--accent-deep)) !important;
    box-shadow: 0 8px 32px rgba(124, 92, 252, .45) !important;
    transform: translateY(-2px) !important;
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
    transform: translateY(-2px) !important;
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

.stAlert [data-testid="stAlertContentInfo"] {
    background: rgba(124, 92, 252, .06) !important;
    border-color: rgba(124, 92, 252, .15) !important;
}

.stAlert [data-testid="stAlertContentSuccess"] {
    background: rgba(52, 211, 153, .06) !important;
    border-color: rgba(52, 211, 153, .15) !important;
}

.stAlert [data-testid="stAlertContentWarning"] {
    background: rgba(251, 191, 36, .06) !important;
    border-color: rgba(251, 191, 36, .15) !important;
}

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

/* ── Slider — diamond thumb ──────────────────────────────────────── */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
    background: var(--accent) !important;
    border-color: var(--accent) !important;
    border-radius: 2px !important;
    transform: rotate(45deg) !important;
    width: 14px !important;
    height: 14px !important;
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

/* ── Brutalist section headers ───────────────────────────────────── */
.section-header-brutal {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: .85rem;
    margin-bottom: 1.25rem;
}

.section-header-brutal h2 {
    font-size: 1.35rem;
    font-weight: 300;
    letter-spacing: -0.02em;
    color: var(--text-primary);
    margin: 0;
}

.section-header-brutal .diamonds {
    font-size: .65rem;
    letter-spacing: 4px;
    color: var(--accent);
    opacity: .6;
}

/* ── Brutalist labels ────────────────────────────────────────────── */
.section-label {
    font-size: .65rem;
    font-weight: 500;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: .5rem;
    opacity: .7;
}

.section-desc {
    font-size: .85rem;
    font-weight: 300;
    color: var(--text-secondary);
    margin-bottom: 1rem;
}

/* ── Custom classes ──────────────────────────────────────────────── */
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

/* ── Stat row — brutalist thin numbers ───────────────────────────── */
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
    font-size: 1.8rem;
    font-weight: 300;
    letter-spacing: -0.02em;
    color: var(--accent);
}

.stat-label {
    font-size: .65rem;
    font-weight: 500;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin-top: .35rem;
    opacity: .7;
}

/* ── Segment cards ───────────────────────────────────────────────── */
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
    font-size: .78rem;
    font-weight: 500;
    color: #34d399;
    margin-left: 2.25rem;
    margin-top: .25rem;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Workflow steps ──────────────────────────────────────────────── */
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
    color: var(--text-muted);
}

.workflow-step-active {
    border-color: var(--border-accent);
    color: var(--text-primary);
    background: var(--accent-soft);
}

.workflow-step-done {
    border-color: rgba(52, 211, 153, .2);
    color: var(--success);
    background: rgba(52, 211, 153, .04);
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

.workflow-step-done .workflow-num {
    background: rgba(52, 211, 153, .12);
    color: var(--success);
}

/* ── Readiness / file status ─────────────────────────────────────── */
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

.readiness-bar {
    display: flex;
    gap: .75rem;
    align-items: center;
    margin: .75rem 0;
    flex-wrap: wrap;
}

.mode-desc {
    font-size: .82rem;
    color: var(--text-secondary);
    padding: .5rem .75rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-xs);
    margin: .5rem 0 1rem;
}

/* ── Preview placeholder ─────────────────────────────────────────── */
.preview-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 3rem 2rem;
    margin: 1.5rem 0;
    position: relative;
    overflow: hidden;
    min-height: 300px;
    background: rgba(0,0,0,.15);
}

.preview-placeholder .gradient-orb {
    position: absolute;
    width: 300px;
    height: 300px;
    background: radial-gradient(circle, rgba(124,92,252,.3) 0%, rgba(124,92,252,0) 70%),
                radial-gradient(circle, rgba(90,63,214,.2) 0%, rgba(90,63,214,0) 70%);
    background-position: 30% 30%, 70% 70%;
    filter: blur(40px);
    opacity: .5;
    animation: breathe 8s infinite alternate;
    pointer-events: none;
}

@keyframes breathe {
    0% { transform: scale(1); opacity: .4; }
    100% { transform: scale(1.15); opacity: .6; }
}

.preview-placeholder .preview-label {
    font-size: .6rem;
    font-weight: 500;
    letter-spacing: .1em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: .5rem;
    z-index: 1;
}

.preview-placeholder .preview-text {
    font-size: 1.5rem;
    font-weight: 300;
    letter-spacing: -0.02em;
    color: var(--text-secondary);
    z-index: 1;
}

/* ── Status bar ──────────────────────────────────────────────────── */
.status-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: .65rem 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius-xs);
    margin-top: .75rem;
    background: var(--surface);
}

.status-bar .status-item {
    font-size: .65rem;
    font-weight: 500;
    letter-spacing: .05em;
    text-transform: uppercase;
    color: var(--text-muted);
    opacity: .7;
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
<div class="noise-overlay"></div>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# JS-based translation of Streamlit built-in UI text
# ---------------------------------------------------------------------------
import streamlit.components.v1 as _components

_components.html(
    """
<script>
(function() {
    var doc = window.parent.document;
    if (!doc) return;
    var T = {
        'Drag and drop file here': '\u041f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0444\u0430\u0439\u043b \u0441\u044e\u0434\u0430',
        'Drag and drop files here': '\u041f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0444\u0430\u0439\u043b\u044b \u0441\u044e\u0434\u0430',
        'Browse files': '\u0412\u044b\u0431\u0440\u0430\u0442\u044c \u0444\u0430\u0439\u043b\u044b',
        'Browse directories': '\u0412\u044b\u0431\u0440\u0430\u0442\u044c \u043f\u0430\u043f\u043a\u0438'
    };
    var limitRe = /Limit (\\d+)\\s*MB per file/i;
    var extRe = /\\u00b7\\s*[A-Z0-9, ]+$/;
    function tr() {
        doc.querySelectorAll('[data-testid="stFileUploaderDropzoneInstructions"]').forEach(function(el) {
            var walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
            var n;
            while (n = walker.nextNode()) {
                var t = n.textContent.trim();
                if (T[t]) { n.textContent = T[t]; continue; }
                if (limitRe.test(n.textContent)) {
                    n.textContent = n.textContent
                        .replace(limitRe, '\u041c\u0430\u043a\u0441. $1 \u041c\u0411 \u043d\u0430 \u0444\u0430\u0439\u043b')
                        .replace(extRe, '');
                }
            }
        });
        doc.querySelectorAll('[data-testid="stFileUploaderDropzone"] button').forEach(function(btn) {
            var walker = doc.createTreeWalker(btn, NodeFilter.SHOW_TEXT, null, false);
            var n;
            while (n = walker.nextNode()) {
                var t = n.textContent.trim();
                if (T[t]) n.textContent = T[t];
            }
        });
    }
    tr();
    new MutationObserver(function() { requestAnimationFrame(tr); })
        .observe(doc.body, {childList: true, subtree: true});
})();
</script>
""",
    height=0,
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
        '<div class="sidebar-logo">UGC<span class="dot">&middot;</span>KIT</div>'
        '<div class="sidebar-version">V.01</div>',
        unsafe_allow_html=True,
    )

    # .01 Script
    st.markdown(
        '<div class="upload-block">'
        '<div class="upload-block-header">'
        '<span class="upload-block-title"><span class="num-index">.01</span>Скрипт</span>'
        '<span class="upload-block-status required">ОБЯЗАТЕЛЬНО</span>'
        "</div>"
        '<div class="upload-block-meta">Markdown (.md)</div>'
        '<div class="upload-block-hint">Загрузите сценарий с таймкодами и озвучкой.</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    script_files = st.file_uploader(
        "Скрипты",
        type=["md"],
        accept_multiple_files=True,
        help=(
            "Markdown-файлы со сценариями видео. Каждый файл может содержать несколько скриптов. "
            'Формат заголовка: ### Script A1: "Название". '
            'Клипы: **Clip 1 (8s):**. Озвучка: Says: "Текст".'
        ),
        label_visibility="collapsed",
    )
    if script_files:
        save_uploads(script_files, SCRIPTS_DIR)
        total_size = sum(f.size for f in script_files)
        size_str = (
            f"{total_size / 1024:.1f} КБ"
            if total_size < 1024 * 1024
            else f"{total_size / 1024 / 1024:.1f} МБ"
        )
        st.markdown(
            f'<div class="upload-counter">{len(script_files)} файл(ов) &middot; {size_str}</div>',
            unsafe_allow_html=True,
        )

    # .02 Avatar
    st.markdown(
        '<div class="upload-block">'
        '<div class="upload-block-header">'
        '<span class="upload-block-title"><span class="num-index">.02</span>Аватар</span>'
        '<span class="upload-block-status required">ОБЯЗАТЕЛЬНО</span>'
        "</div>"
        '<div class="upload-block-meta">Видео (.mp4)</div>'
        '<div class="upload-block-hint">Видео с AI-аватаром, по одному на клип.</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    avatar_files = st.file_uploader(
        "Аватары",
        type=["mp4"],
        accept_multiple_files=True,
        help=(
            "Видео с AI-аватарами (Higgsfield, HeyGen и т.д.). "
            "По одному файлу на каждый клип в скрипте. "
            "Порядок определяется по имени файла (напр. A1_clip1.mp4, A1_clip2.mp4)."
        ),
        label_visibility="collapsed",
    )
    if avatar_files:
        save_uploads(avatar_files, AVATARS_DIR)
        total_size = sum(f.size for f in avatar_files)
        size_str = (
            f"{total_size / 1024:.1f} КБ"
            if total_size < 1024 * 1024
            else f"{total_size / 1024 / 1024:.1f} МБ"
        )
        st.markdown(
            f'<div class="upload-counter">{len(avatar_files)} файл(ов) &middot; {size_str}</div>',
            unsafe_allow_html=True,
        )

    # .03 Screencast
    st.markdown(
        '<div class="upload-block">'
        '<div class="upload-block-header">'
        '<span class="upload-block-title"><span class="num-index">.03</span>Скринкаст</span>'
        '<span class="upload-block-status optional">ОПЦИОНАЛЬНО</span>'
        "</div>"
        '<div class="upload-block-meta">Видео (.mp4)</div>'
        '<div class="upload-block-hint">Запись экрана для наложения на видео.</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    screencast_files = st.file_uploader(
        "Скринкасты",
        type=["mp4"],
        accept_multiple_files=True,
        help=(
            "Записи экрана приложения для наложения на видео. "
            "Имя файла должно совпадать с тегом [screencast: имя_файла @ ...] в скрипте. "
            "Поддерживается любое разрешение — скринкаст будет масштабирован автоматически."
        ),
        label_visibility="collapsed",
    )
    if screencast_files:
        save_uploads(screencast_files, SCREENCASTS_DIR)
        total_size = sum(f.size for f in screencast_files)
        size_str = (
            f"{total_size / 1024:.1f} КБ"
            if total_size < 1024 * 1024
            else f"{total_size / 1024 / 1024:.1f} МБ"
        )
        st.markdown(
            f'<div class="upload-counter">{len(screencast_files)} файл(ов) &middot; {size_str}</div>',
            unsafe_allow_html=True,
        )

    # .04 Music
    st.markdown(
        '<div class="upload-block">'
        '<div class="upload-block-header">'
        '<span class="upload-block-title"><span class="num-index">.04</span>Музыка</span>'
        '<span class="upload-block-status optional">ОПЦИОНАЛЬНО</span>'
        "</div>"
        '<div class="upload-block-meta">Аудио (.mp3, .wav, .m4a, .ogg)</div>'
        '<div class="upload-block-hint">Фоновый трек, зацикленный на длину видео.</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    music_file_upload = st.file_uploader(
        "Музыка",
        type=["mp3", "wav", "m4a", "ogg"],
        help=(
            "Фоновый музыкальный трек. "
            "Поддерживаются форматы: MP3, WAV, M4A, OGG. "
            "Музыка будет зациклена на длительность видео и микширована с озвучкой."
        ),
        label_visibility="collapsed",
    )
    if music_file_upload:
        size_str = (
            f"{music_file_upload.size / 1024:.1f} КБ"
            if music_file_upload.size < 1024 * 1024
            else f"{music_file_upload.size / 1024 / 1024:.1f} МБ"
        )
        st.markdown(
            f'<div class="upload-counter">{music_file_upload.name} &middot; {size_str}</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Parse scripts
# ---------------------------------------------------------------------------
all_scripts = parse_scripts_directory(SCRIPTS_DIR)

# Validate uploaded scripts
if script_files and not all_scripts:
    st.sidebar.error(
        "Загруженные файлы не содержат скриптов в формате UGCKit. "
        'Проверьте формат: ### Script A1: "Название"'
    )

# Load config
cfg = load_config()

# Save music to disk
music_path = None
if music_file_upload:
    music_path = TMP / music_file_upload.name
    music_path.write_bytes(music_file_upload.getbuffer())

# ---------------------------------------------------------------------------
# Tabs (reordered: Scripts → Settings → Compose)
# ---------------------------------------------------------------------------
tab_scripts, tab_settings, tab_compose = st.tabs(["Скрипты", "Настройки", "Сборка"])

# ---------------------------------------------------------------------------
# Settings tab (global settings only — mode-specific settings on Compose tab)
# ---------------------------------------------------------------------------
with tab_settings:
    st.markdown(
        '<div class="section-header-brutal">'
        "<h2>Настройки</h2>"
        '<span class="diamonds">&#9670;&#9670;&#9670;</span>'
        "</div>"
        '<div class="section-desc">Качество видео, звук, субтитры и синхронизация.</div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            '<div class="section-label">Качество видео</div>',
            unsafe_allow_html=True,
        )
        crf = st.slider(
            "Качество видео",
            15,
            35,
            cfg.output.crf,
            help=(
                "Чем ниже — тем лучше качество, но тяжелее файл. "
                "18–23 — оптимально для соцсетей. "
                "15 — почти без потерь, 35 — сильное сжатие."
            ),
            label_visibility="collapsed",
        )
        codec_options = ["H.264 (быстрый)", "H.265 (компактный)"]
        codec_values = ["libx264", "libx265"]
        codec_idx = 0 if cfg.output.codec == "libx264" else 1
        codec_display = st.selectbox(
            "Формат видео",
            codec_options,
            index=codec_idx,
            help=(
                "H.264 — быстрее кодирование, максимальная совместимость. "
                "H.265 — меньше размер файла при том же качестве, но медленнее. "
                "Для TikTok/Reels рекомендуется H.264."
            ),
        )
        codec = codec_values[codec_options.index(codec_display)]

        st.markdown("---")
        st.markdown(
            '<div class="section-label">Аудио</div>',
            unsafe_allow_html=True,
        )
        normalize_audio = st.checkbox(
            "Нормализация громкости",
            value=cfg.audio.normalize,
            help=(
                "Выравнивание громкости по стандарту LUFS. "
                "Включите, чтобы все клипы звучали одинаково громко, "
                "даже если исходные аватары записаны с разной громкостью."
            ),
        )
        if normalize_audio:
            target_loudness = st.slider(
                "Целевая громкость",
                -24,
                -8,
                cfg.audio.target_loudness,
                help=(
                    "Стандарт для соцсетей: -14. "
                    "-24 — очень тихо, -8 — очень громко. "
                    "TikTok и Instagram рекомендуют -14."
                ),
            )
        else:
            target_loudness = cfg.audio.target_loudness

        if music_path:
            st.markdown("---")
            st.markdown(
                '<div class="section-label">Фоновая музыка</div>',
                unsafe_allow_html=True,
            )
            music_volume = st.slider(
                "Громкость музыки",
                0,
                100,
                15,
                5,
                format="%d%%",
                help=(
                    "Уровень громкости фоновой музыки относительно озвучки. "
                    "15% — ненавязчивый фон. "
                    "30–50% — заметная музыка. 100% — одинаковая громкость с озвучкой."
                ),
            )
            music_fade_out = st.slider(
                "Затухание (сек.)",
                0.0,
                10.0,
                2.0,
                0.5,
                help=(
                    "Длительность плавного затухания музыки в конце видео. "
                    "0 — резкое обрывание. 2–3 сек. — плавный финиш."
                ),
            )
        else:
            music_volume = 15
            music_fade_out = 2.0

    with col2:
        st.markdown(
            '<div class="section-label">Субтитры</div>',
            unsafe_allow_html=True,
        )
        enable_subtitles = st.checkbox(
            "Включить субтитры",
            value=False,
            help=(
                "Генерация субтитров в стиле караоке на основе распознавания речи. "
                "Слова подсвечиваются по мере произнесения. "
                "Требует openai-whisper."
            ),
        )
        if enable_subtitles:
            subtitle_font_size = st.slider(
                "Размер шрифта субтитров",
                24,
                96,
                48,
                help="Размер текста субтитров в пикселях. 48 — стандарт для 1080x1920. Увеличьте до 64–96 для агрессивного стиля.",
            )
        else:
            subtitle_font_size = 48

        st.markdown("---")
        st.markdown(
            '<div class="section-label">Умная синхронизация</div>',
            unsafe_allow_html=True,
        )
        enable_sync = st.checkbox(
            "Авто-синхронизация скринкастов",
            value=False,
            help=(
                "Автоматическое определение тайминга скринкастов по ключевым словам в речи аватара. "
                'Используйте теги word:"..." в скрипте вместо числовых таймкодов. '
                "Требует openai-whisper."
            ),
        )

        if enable_sync or enable_subtitles:
            st.markdown("---")
            st.markdown(
                '<div class="section-label">Модель Whisper</div>',
                unsafe_allow_html=True,
            )
            whisper_model = st.selectbox(
                "Модель Whisper",
                ["tiny", "base", "small", "medium", "large"],
                index=1,
                help=(
                    "Одна модель для синхронизации и субтитров. "
                    "tiny — быстрая, но менее точная. "
                    "base — хороший баланс скорости и качества. "
                    "large — максимальная точность, но медленная."
                ),
            )
        else:
            whisper_model = "base"

    # Apply global settings to config
    cfg.output.crf = crf
    cfg.output.codec = codec
    cfg.audio.normalize = normalize_audio
    cfg.audio.target_loudness = target_loudness
    if enable_subtitles:
        cfg.subtitles.enabled = True
        cfg.subtitles.font_size = subtitle_font_size
        cfg.subtitles.whisper_model = whisper_model
    if music_path:
        cfg.music.enabled = True
        cfg.music.file = music_path
        cfg.music.volume = music_volume / 100
        cfg.music.fade_out_duration = music_fade_out

# ---------------------------------------------------------------------------
# Scripts tab
# ---------------------------------------------------------------------------
with tab_scripts:
    st.markdown(
        '<div class="section-header-brutal">'
        "<h2>Скрипты</h2>"
        '<span class="diamonds">&#9670;&#9670;&#9670;</span>'
        "</div>"
        '<div class="section-desc">'
        "Автоматическая сборка коротких видео для TikTok и Reels: аватар + скринкаст + субтитры."
        "</div>",
        unsafe_allow_html=True,
    )

    if not all_scripts:
        st.markdown(
            '<div class="card-highlight" style="margin-bottom:1rem;">'
            '<div style="font-size:.85rem; color:var(--text-secondary); line-height:1.6;">'
            "Скрипты ещё не загружены. Перетащите <code>.md</code> файлы в боковую панель.<br><br>"
            "<strong>Ожидаемый формат:</strong>"
            "</div>"
            '<div style="margin-top:.75rem; padding:.75rem 1rem; background:rgba(0,0,0,.2); '
            "border-radius:8px; font-family:'JetBrains Mono',monospace; font-size:.78rem; "
            'color:var(--text-secondary); line-height:1.7;">'
            '### Script A1: "Название"<br>'
            "**Clip 1 (8s):**<br>"
            'Says: "Текст озвучки"<br>'
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
            f'<div class="stat-label">Скриптов</div></div>'
            f'<div class="stat-item"><div class="stat-value">{total_segments}</div>'
            f'<div class="stat-label">Сегментов</div></div>'
            f'<div class="stat-item"><div class="stat-value">{total_duration:.0f}с</div>'
            f'<div class="stat-label">Общая длительность</div></div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        for script in all_scripts:
            with st.expander(
                f"{script.script_id}: {script.title}  —  "
                f"{len(script.segments)} клипов, ~{script.total_duration:.0f}с"
            ):
                for seg in script.segments:
                    # Build screencast tags
                    sc_html = ""
                    for sc in seg.screencasts:
                        mode_label = MODE_LABEL_MAP.get(sc.mode, sc.mode.value)
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
                        f'<div style="font-weight:600; font-size:.85rem;">Клип {seg.id}</div>'
                        f'<div class="segment-duration">{seg.duration:.0f}с</div>'
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
        '<div class="section-header-brutal">'
        "<h2>Сборка</h2>"
        '<span class="diamonds">&#9670;&#9670;&#9670;</span>'
        "</div>",
        unsafe_allow_html=True,
    )

    if not all_scripts:
        st.markdown(
            '<div class="preview-placeholder">'
            '<div class="gradient-orb"></div>'
            '<div class="preview-label">ПРЕВЬЮ</div>'
            '<div class="preview-text">Ожидание файлов</div>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="status-bar">'
            '<div class="status-item">Прим. рендер: ~45с</div>'
            '<div class="status-item">Очередь: пусто</div>'
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        # --- Script selector ---
        script_options = {f"{s.script_id}: {s.title}": s for s in all_scripts}
        selected_label = st.selectbox(
            "Скрипт",
            list(script_options.keys()),
            help="Выберите сценарий для сборки. Каждый скрипт содержит набор клипов с озвучкой и скринкастами.",
        )
        selected_script = script_options[selected_label]

        # --- Mode selector ---
        comp_mode = st.radio(
            "Режим композиции",
            list(MODE_MAP.keys()),
            horizontal=True,
            help=(
                "Оверлей: аватар на весь экран, скринкаст в углу. "
                "PiP: скринкаст на весь экран, голова аватара в углу. "
                "Сплит: аватар и скринкаст рядом. "
                "Хромакей: фон аватара удаляется, фигура накладывается на скринкаст."
            ),
        )
        selected_mode = MODE_MAP[comp_mode]

        # Mode description
        st.markdown(
            f'<div class="mode-desc">{MODE_DESCRIPTIONS[comp_mode]}</div>',
            unsafe_allow_html=True,
        )

        # --- Mode-specific settings (inline, only for selected mode) ---
        if selected_mode == CompositionMode.OVERLAY:
            mc1, mc2, mc3 = st.columns(3)
            with mc1:
                overlay_scale = st.slider(
                    "Масштаб скринкаста",
                    10,
                    80,
                    int(cfg.composition.overlay.scale * 100),
                    5,
                    format="%d%%",
                    help="Размер скринкаста относительно ширины видео.",
                )
                cfg.composition.overlay.scale = overlay_scale / 100
            with mc2:
                overlay_position = _pos_selectbox(
                    "Позиция скринкаста",
                    cfg.composition.overlay.position.value,
                    "Угол экрана для размещения скринкаста.",
                )
                cfg.composition.overlay.position = Position(overlay_position)
            with mc3:
                overlay_margin = st.number_input(
                    "Отступ (пкс.)",
                    0,
                    200,
                    cfg.composition.overlay.margin,
                    help="Расстояние в пикселях от края кадра. Рекомендуемо: 30–70.",
                )
                cfg.composition.overlay.margin = overlay_margin

        elif selected_mode == CompositionMode.PIP:
            mc1, mc2 = st.columns(2)
            with mc1:
                pip_head_scale = st.slider(
                    "Размер головы",
                    10,
                    50,
                    int(cfg.composition.pip.head_scale * 100),
                    5,
                    format="%d%%",
                    help="Размер круглой вырезки головы аватара относительно ширины видео.",
                )
                cfg.composition.pip.head_scale = pip_head_scale / 100
            with mc2:
                pip_head_position = _pos_selectbox(
                    "Позиция головы",
                    cfg.composition.pip.head_position.value,
                    "Угол экрана для размещения круглой вырезки головы аватара.",
                )
                cfg.composition.pip.head_position = Position(pip_head_position)

        elif selected_mode == CompositionMode.SPLIT:
            mc1, mc2 = st.columns(2)
            with mc1:
                side_options = ["Слева", "Справа"]
                side_values = ["left", "right"]
                side_idx = (
                    side_values.index(cfg.composition.split.avatar_side)
                    if cfg.composition.split.avatar_side in side_values
                    else 0
                )
                side_display = st.selectbox(
                    "Сторона аватара",
                    side_options,
                    index=side_idx,
                    help="На какой стороне экрана будет аватар. Скринкаст займёт противоположную сторону.",
                )
                cfg.composition.split.avatar_side = side_values[side_options.index(side_display)]
            with mc2:
                split_ratio = st.slider(
                    "Пропорция разделения",
                    30,
                    70,
                    50,
                    5,
                    format="%d%%",
                    help="Доля ширины экрана для стороны аватара. 50% = пополам.",
                )
                cfg.composition.split.split_ratio = split_ratio / 100

        elif selected_mode == CompositionMode.GREENSCREEN:
            mc1, mc2 = st.columns(2)
            with mc1:
                gs_avatar_scale = st.slider(
                    "Масштаб аватара",
                    30,
                    100,
                    80,
                    5,
                    format="%d%%",
                    help="Размер прозрачного аватара. Фон удаляется, остаётся только фигура. Требует rembg.",
                )
                cfg.composition.greenscreen.avatar_scale = gs_avatar_scale / 100
            with mc2:
                gs_avatar_position = _pos_selectbox(
                    "Позиция аватара",
                    "bottom-right",
                    "Угол экрана для размещения прозрачного аватара поверх скринкаста.",
                )
                cfg.composition.greenscreen.avatar_position = Position(gs_avatar_position)

        # --- Dynamic workflow steps ---
        available_avatars = sorted(AVATARS_DIR.glob("*.mp4"))
        segs_count = len(selected_script.segments)
        avs_count = len(available_avatars)

        step1_done = len(all_scripts) > 0
        step2_done = avs_count >= segs_count
        step3_active = step1_done and step2_done

        def _step_cls(done: bool, active: bool = False) -> str:
            if done:
                return "workflow-step workflow-step-done"
            if active:
                return "workflow-step workflow-step-active"
            return "workflow-step"

        st.markdown(
            f'<div class="workflow-steps">'
            f'<div class="{_step_cls(step1_done)}"><div class="workflow-num">{"&#9670;" if step1_done else "1"}</div>Скрипт загружен</div>'
            f'<div class="{_step_cls(step2_done)}"><div class="workflow-num">{"&#9670;" if step2_done else "2"}</div>Аватары ({avs_count}/{segs_count})</div>'
            f'<div class="{_step_cls(False, step3_active)}"><div class="workflow-num">3</div>Проверить таймлайн</div>'
            f'<div class="{_step_cls(False)}"><div class="workflow-num">4</div>Собрать видео</div>'
            "</div>",
            unsafe_allow_html=True,
        )

        # --- Readiness indicator ---
        readiness_items = []
        if step1_done:
            readiness_items.append(
                f'<div class="file-status file-status-ok">&#9670; {len(all_scripts)} скриптов</div>'
            )
        else:
            readiness_items.append(
                '<div class="file-status file-status-warn">&#9671; Нет скриптов</div>'
            )

        if step2_done:
            readiness_items.append(
                f'<div class="file-status file-status-ok">&#9670; {avs_count} аватаров</div>'
            )
        else:
            readiness_items.append(
                f'<div class="file-status file-status-warn">&#9671; {avs_count}/{segs_count} аватаров</div>'
            )

        sc_needed = any(sc for seg in selected_script.segments for sc in seg.screencasts)
        sc_available = len(list(SCREENCASTS_DIR.glob("*.mp4")))
        if sc_needed:
            if sc_available > 0:
                readiness_items.append(
                    f'<div class="file-status file-status-ok">&#9670; {sc_available} скринкастов</div>'
                )
            else:
                readiness_items.append(
                    '<div class="file-status file-status-warn">&#9671; Нужны скринкасты</div>'
                )

        st.markdown(
            f'<div class="readiness-bar">{"".join(readiness_items)}</div>',
            unsafe_allow_html=True,
        )

        # --- Avatar binding (expanded by default) ---
        sid = selected_script.script_id.upper()
        prefix_matched = sorted([f for f in available_avatars if f.stem.upper().startswith(sid)])
        matched_avatars = prefix_matched if prefix_matched else available_avatars

        if matched_avatars:
            binding_title = (
                f"Привязка аватаров ({min(len(matched_avatars), segs_count)}/{segs_count})"
            )
            with st.expander(binding_title, expanded=True):
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
                        st.warning(
                            f"Сегмент {seg.id} — нет аватара. "
                            f"Загрузите файл {sid}_clip{seg.id}.mp4 через боковую панель."
                        )

            if avs_count > segs_count:
                st.info(f"Будут использованы первые {segs_count} из {avs_count} аватаров.")

        # --- Auto timeline preview ---
        if step3_active and matched_avatars:
            # Override mode for screencasts
            if selected_mode != CompositionMode.OVERLAY:
                for seg in selected_script.segments:
                    for sc in seg.screencasts:
                        sc.mode = selected_mode

            script_to_use = selected_script
            if enable_sync:
                with st.spinner(f"Запуск Whisper ({whisper_model}) для синхронизации..."):
                    synced = apply_sync(selected_script, matched_avatars, whisper_model)
                    if synced is not selected_script:
                        script_to_use = synced
                    else:
                        st.warning(
                            "Синхронизация не удалась. Возможная причина: не установлен openai-whisper."
                        )

            output_path = OUTPUT_DIR / f"{script_to_use.script_id}.mp4"
            try:
                timeline = build_timeline(
                    script=script_to_use,
                    avatar_clips=matched_avatars,
                    screencasts_dir=SCREENCASTS_DIR,
                    output_path=output_path,
                )

                with st.expander("Таймлайн", expanded=False):
                    st.code(format_timeline(timeline))
                    cmd = compose_video(timeline, cfg, dry_run=True)
                    st.code(format_ffmpeg_cmd(cmd), language="bash")
            except (ValueError, FFmpegError) as e:
                st.error(str(e))
                timeline = None
        else:
            timeline = None
            output_path = None

        # --- Compose button ---
        st.markdown("")  # spacing
        can_compose = step3_active and matched_avatars and timeline is not None

        if st.button(
            "Собрать видео",
            type="primary",
            use_container_width=True,
            disabled=not can_compose,
        ):
            try:
                # Pre-processing per mode
                head_videos = None
                transparent_avatars = None

                if selected_mode == CompositionMode.PIP:
                    with st.spinner("Генерация вырезки головы для PiP..."):
                        head_videos = prepare_pip_videos(matched_avatars, cfg) or None
                    if not head_videos:
                        st.warning(
                            "PiP обработка не удалась. Видео будет собрано без вырезки головы."
                        )

                elif selected_mode == CompositionMode.GREENSCREEN:
                    with st.spinner("Удаление фона аватаров..."):
                        transparent_avatars = (
                            prepare_greenscreen_videos(matched_avatars, cfg) or None
                        )
                    if not transparent_avatars:
                        st.warning("Удаление фона не удалось. Видео будет собрано без хромакея.")

                # Generate subtitles
                subtitle_file = None
                if cfg.subtitles.enabled:
                    with st.spinner("Генерация субтитров..."):
                        subtitle_file = generate_subtitles(timeline, matched_avatars, cfg)
                    if not subtitle_file:
                        st.warning(
                            "Субтитры не удалось сгенерировать. Видео будет собрано без субтитров."
                        )

                progress_bar = st.progress(0.0, text="Рендеринг...")
                result_path = compose_video_with_progress(
                    timeline,
                    cfg,
                    progress_callback=lambda p: progress_bar.progress(
                        p,
                        text=f"Рендеринг... {p:.0%}",
                    ),
                    head_videos=head_videos,
                    transparent_avatars=transparent_avatars,
                    subtitle_file=subtitle_file,
                    music_file=music_path,
                )

                # Save result to session state
                st.session_state["last_output"] = result_path

                file_size_mb = result_path.stat().st_size / 1024 / 1024
                st.success(f"Готово! {result_path.name} ({file_size_mb:.1f} МБ)")
            except (ValueError, FFmpegError) as e:
                st.error(str(e))

        # --- Show last result (persists across reruns) ---
        last_output = st.session_state.get("last_output")
        if last_output and Path(last_output).exists():
            st.video(str(last_output))
            with open(last_output, "rb") as vf:
                st.download_button(
                    "Скачать видео",
                    data=vf,
                    file_name=Path(last_output).name,
                    mime="video/mp4",
                    use_container_width=True,
                )
        elif not can_compose:
            # Preview placeholder when files are loaded but not ready
            st.markdown(
                '<div class="preview-placeholder">'
                '<div class="gradient-orb"></div>'
                '<div class="preview-label">ПРЕВЬЮ</div>'
                '<div class="preview-text">Ожидание файлов</div>'
                "</div>",
                unsafe_allow_html=True,
            )

        # Status bar
        est_render = f"~{int(selected_script.total_duration * 1.5)}с" if selected_script else "~45с"
        st.markdown(
            f'<div class="status-bar">'
            f'<div class="status-item">Прим. рендер: {est_render}</div>'
            f'<div class="status-item">Очередь: пусто</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        # --- Batch compose ---
        st.markdown("---")
        with st.expander("Пакетная сборка всех скриптов"):
            st.markdown(
                '<div style="font-size:.85rem; color:var(--text-secondary); margin-bottom:.75rem;">'
                "Соберёт все загруженные скрипты. Аватары привязываются автоматически "
                "по префиксу (A1_clip1.mp4 → скрипт A1). Используются текущие настройки."
                "</div>",
                unsafe_allow_html=True,
            )
            confirm_batch = st.checkbox(
                "Подтверждаю пакетную сборку",
                help="Поставьте галочку и нажмите кнопку ниже для запуска.",
            )
            if st.button(
                "Собрать все скрипты",
                disabled=not confirm_batch,
            ):
                for script in all_scripts:
                    s_id = script.script_id.upper()
                    s_avatars = sorted(
                        [f for f in available_avatars if f.stem.upper().startswith(s_id)]
                    )
                    if not s_avatars:
                        s_avatars = available_avatars if len(all_scripts) == 1 else []

                    if not s_avatars:
                        st.warning(f"[{script.script_id}] Нет подходящих аватаров, пропуск.")
                        continue

                    # Apply mode override
                    if selected_mode != CompositionMode.OVERLAY:
                        for seg in script.segments:
                            for sc in seg.screencasts:
                                sc.mode = selected_mode

                    batch_output = OUTPUT_DIR / f"{script.script_id}.mp4"
                    try:
                        batch_timeline = build_timeline(
                            script=script,
                            avatar_clips=s_avatars,
                            screencasts_dir=SCREENCASTS_DIR,
                            output_path=batch_output,
                        )

                        # Pre-processing per mode (batch)
                        batch_head_videos = None
                        batch_transparent_avatars = None

                        if selected_mode == CompositionMode.PIP:
                            try:
                                from ugckit.pip_processor import create_head_video

                                batch_head_videos = []
                                with st.spinner(f"[{script.script_id}] Вырезка головы..."):
                                    for i, avatar in enumerate(s_avatars):
                                        head_out = (
                                            OUTPUT_DIR / f"batch_head_{script.script_id}_{i}.webm"
                                        )
                                        head_path = create_head_video(
                                            avatar, head_out, cfg.composition.pip
                                        )
                                        batch_head_videos.append(head_path)
                            except Exception:
                                batch_head_videos = None

                        elif selected_mode == CompositionMode.GREENSCREEN:
                            try:
                                from ugckit.pip_processor import (
                                    create_transparent_avatar,
                                )

                                batch_transparent_avatars = []
                                gs_cfg = cfg.composition.greenscreen
                                with st.spinner(f"[{script.script_id}] Удаление фона..."):
                                    for i, avatar in enumerate(s_avatars):
                                        out = (
                                            OUTPUT_DIR / f"batch_trans_{script.script_id}_{i}.webm"
                                        )
                                        ta = create_transparent_avatar(
                                            avatar,
                                            out,
                                            scale=gs_cfg.avatar_scale,
                                            output_width=cfg.output.resolution[0],
                                        )
                                        batch_transparent_avatars.append(ta)
                            except Exception:
                                batch_transparent_avatars = None

                        # Subtitles for batch
                        batch_subtitle_file = None
                        if cfg.subtitles.enabled:
                            try:
                                from ugckit.subtitles import generate_subtitle_file

                                with st.spinner(f"[{script.script_id}] Субтитры..."):
                                    batch_subtitle_file = generate_subtitle_file(
                                        batch_timeline, s_avatars, cfg
                                    )
                            except Exception:
                                batch_subtitle_file = None

                        progress_bar = st.progress(
                            0.0,
                            text=f"Рендеринг {script.script_id}...",
                        )
                        result_path = compose_video_with_progress(
                            batch_timeline,
                            cfg,
                            progress_callback=lambda p, sid=script.script_id: progress_bar.progress(
                                p,
                                text=f"Рендеринг {sid}... {p:.0%}",
                            ),
                            head_videos=batch_head_videos,
                            transparent_avatars=batch_transparent_avatars,
                            subtitle_file=batch_subtitle_file,
                            music_file=music_path,
                        )
                        st.success(f"[{script.script_id}] Готово!")
                        with open(result_path, "rb") as vf:
                            st.download_button(
                                f"Скачать {result_path.name}",
                                data=vf,
                                file_name=result_path.name,
                                mime="video/mp4",
                            )
                    except (ValueError, FFmpegError) as e:
                        st.error(f"[{script.script_id}] {e}")
