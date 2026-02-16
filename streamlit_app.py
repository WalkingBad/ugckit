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
    initial_sidebar_state="collapsed",
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
# Custom CSS — Redesigned (Helvetica / Fixed Grid)
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
/* ── Reset & Variables ───────────────────────────────────────────── */
:root {
    --bg: #ffffff;
    --ink: #000000;
    --accent-red: #ff1a1a;
    --accent-blue: #1a1aff;
    --border-color: #000000;
    --font-main: "Helvetica Neue", Helvetica, Arial, sans-serif;
    --space-xs: 4px;
    --space-sm: 8px;
    --space-md: 16px;
    --space-lg: 24px;
    --space-xl: 32px;
}

html, body, [class*="css"] {
    font-family: var(--font-main) !important;
    background-color: var(--bg);
    color: var(--ink);
    -webkit-font-smoothing: antialiased;
    font-size: 13px;
    line-height: 1.4;
}

/* ── Hide default Streamlit chrome ───────────────────────────────── */
[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
.stDeployButton,
[data-testid="manage-app-button"] {
    display: none !important;
}

[data-testid="stAppViewBlockContainer"] {
    padding: 0 !important;
    max-width: 100vw !important;
}

.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
    overflow: hidden;
}

/* ── Global Layout Grid ──────────────────────────────────────────── */
/*
   We need a grid: [Sidebar 60px] [Assets 320px] [Settings 320px] [Preview 1fr]
   Streamlit's main container wraps everything. We'll use CSS to force the layout.
*/

/* Force the main horizontal block to behave like our grid */
/* ── Global Layout Grid ──────────────────────────────────────────── */
/*
   We need a grid: [Sidebar 60px] [Assets 320px] [Settings 320px] [Preview 1fr]
   Streamlit's main container wraps everything. We'll use CSS to force the layout.
*/
[data-testid="stAppViewContainer"] > .main .block-container {
    padding: 0 !important;
    max-width: 100vw !important;
    margin: 0 !important;
    overflow-x: hidden;
}

/* Force the main horizontal block to behave like our grid */
[data-testid="stHorizontalBlock"] {
    display: grid !important;
    grid-template-columns: 320px 320px 1fr !important; /* Assets, Settings, Output */
    width: calc(100vw - 60px) !important; /* Subtract sidebar width */
    margin-left: 60px !important; /* Offset for fixed sidebar */
    gap: 0 !important;
    height: 100vh;
    align-content: start;
}

/* Columns */
[data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important; /* Allow shrinking if needed */
    flex: none !important; /* Disable flex behavior */
    height: 100vh;
    overflow-y: auto;
    background: var(--bg);
    border-right: 1px solid var(--border-color);
}

[data-testid="stColumn"]:last-child {
    border-right: none;
}

/* Fixed Sidebar Injection */
/* Fixed Sidebar Injection */
.custom-sidebar {
    position: fixed;
    top: 0;
    left: 0;
    width: 60px;
    height: 100vh;
    background: var(--bg);
    border-right: 1px solid var(--border-color);
    z-index: 99999; /* Higher z-index to stay on top */
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-lg) 0;
}

.custom-sidebar span {
    writing-mode: vertical-rl;
    text-orientation: mixed;
    transform: rotate(180deg); /* Keep rotation for main text if desired, or remove if "TIKTOK" should read down */
    /* The user specificially complained about "full sh*t", so let's stick to standard vertical text reading from bottom-up or top-down cleanly. */
    /* Design reference suggests bottom-up. */
}

.custom-sidebar .version {
    margin-top: auto; 
    writing-mode: horizontal-tb; /* Keep version horizontal or small at bottom */
    transform: none;
    font-size: 10px;
}

.custom-sidebar span {
    font-size: 32px;
    letter-spacing: 0.05em;
    font-weight: 300;
}

.custom-sidebar .version {
    font-size: 14px; 
    margin-top: auto; 
    transform: rotate(0); /* Reset rotation for version if needed, but original design has it vertical too? */
    /* Original design: generic vertical text. Let's keep it consistent. */
}

/* ── Typography & Headers ────────────────────────────────────────── */
h1, h2, h3 {
    font-family: var(--font-main) !important;
    font-weight: 300 !important;
    letter-spacing: -0.02em !important;
}

.section-header {
    font-size: 24px;
    padding: var(--space-lg);
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--bg);
    position: sticky;
    top: 0;
    z-index: 10;
}

.section-header h2 {
    margin: 0;
    padding: 0;
    font-size: 24px;
}

.section-header span.diamonds {
    font-size: 12px;
    letter-spacing: 4px;
    color: var(--ink);
}

/* ── Upload Items (Assets) ───────────────────────────────────────── */
.upload-item {
    padding: var(--space-lg);
    border-bottom: 1px solid var(--border-color);
    transition: background 0.2s;
}

.upload-item:hover {
    background: #f5f5f5;
}

.upload-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-sm);
}

.upload-title {
    font-size: 16px;
    color: var(--ink);
}

.num-index {
    font-weight: 300;
    margin-right: var(--space-sm);
}

.file-status {
    font-size: 11px;
    text-transform: uppercase;
    gap: 6px;
    display: flex;
    align-items: center;
}

.label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: var(--space-sm);
    display: block;
    opacity: 0.7;
    color: var(--ink);
}

/* ── File Uploader Override ──────────────────────────────────────── */
[data-testid="stFileUploader"] {
    margin: 0 !important;
    padding: 0 !important;
}

[data-testid="stFileUploaderDropzone"] {
    background: transparent !important;
    border: 1px dashed var(--ink) !important;
    border-radius: 0 !important;
    height: 80px !important;
    min-height: 80px !important;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: var(--space-sm);
}

[data-testid="stFileUploaderDropzone"]:hover {
    background: rgba(0,0,0,0.02) !important;
}

[data-testid="stFileUploaderDropzone"] button {
    display: none; /* Hide default 'Browse files' button */
}

/* ── Controls (Settings) ─────────────────────────────────────────── */
.control-group {
    padding: var(--space-lg);
    border-bottom: 1px solid var(--border-color);
    min-height: 100px; /* Enforce consistent height for better vertical rhythm */
}

/* Sliders */
[data-testid="stSlider"] {
    padding-top: var(--space-md) !important;
    padding-bottom: var(--space-md) !important;
    position: relative;
    z-index: 10;
}

/* Fix Slider Thumb: Diamond shape via pseudo-element so text stays upright */
[data-testid="stSlider"] [role="slider"] {
    background: transparent !important; /* Transparent container */
    width: 16px !important;
    height: 16px !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    border: none !important;
    transform: none !important; /* NO rotation on container */
    display: flex;
    align-items: center;
    justify-content: center;
}

/* The Diamond Shape */
[data-testid="stSlider"] [role="slider"]::after {
    content: "";
    position: absolute;
    width: 100%;
    height: 100%;
    background: var(--ink);
    transform: rotate(45deg);
    z-index: -1;
}

/* Fix Slider Value Label: Just position it, no rotation needed */
[data-testid="stThumbValue"] {
    font-family: var(--font-main) !important;
    font-size: 11px !important;
    color: var(--ink) !important;
    background: transparent !important;
    transform: none !important; /* Ensure no rotation */
    position: absolute;
    top: -24px;
    left: 50%;
    transform: translateX(-50%) !important; /* Center horizontally */
    width: 40px;
    text-align: center;
    pointer-events: none;
}

[data-testid="stSlider"] [data-baseweb="slider"] > div > div:first-child {
    background: var(--ink) !important;
    height: 1px !important;
}

/* Selectbox */
[data-baseweb="select"] {
    border-radius: 0 !important;
}
[data-baseweb="select"] > div {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid var(--ink) !important;
    border-radius: 0 !important;
    padding-left: 0 !important;
    font-size: 14px !important;
}

/* Checkbox */
[data-testid="stCheckbox"] label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
}

/* ── Output / Preview ────────────────────────────────────────────── */
.gradient-orb {
    position: absolute;
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, var(--accent-red) 0%, rgba(0,0,0,0) 70%),
                radial-gradient(circle, var(--accent-blue) 0%, rgba(0,0,0,0) 70%);
    background-position: 30% 30%, 70% 70%;
    filter: blur(60px) contrast(1.2);
    opacity: 0.15;
    mix-blend-mode: multiply;
    z-index: 0;
    pointer-events: none;
    animation: breathe 10s infinite alternate;
}

@keyframes breathe {
    0% { transform: scale(1); opacity: 0.15; }
    100% { transform: scale(1.1); opacity: 0.25; }
}

.wireframe-svg {
    position: absolute;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 100%; height: 100%;
    pointer-events: none;
    z-index: 0;
    opacity: 0.6;
}

/* Center Output Content */
/* The parent of preview-placeholder needs to align it */
[data-testid="stColumn"]:nth-child(3) [data-testid="stMarkdownContainer"] > div {
     /* Target the inner div of markdown in 3rd column if possible, or force canvas itself */
     display: flex;
     justify-content: center;
     align-items: center;
     height: 100%;
}

.preview-canvas {
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
    height: 100%;
    position: relative;
}

.preview-placeholder {
    border: 1px solid var(--ink);
    width: 280px;
    height: 500px; 
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(255,255,255,0.5);
    backdrop-filter: blur(5px);
    z-index: 2;
    position: relative;
    flex-direction: column;
    margin: auto; /* Force Centering */
}

.preview-text {
    text-align: center;
    font-size: 24px;
    font-weight: 300;
}

/* ── Build Bar ───────────────────────────────────────────────────── */
.build-bar {
    padding: var(--space-lg);
    border-top: 1px solid var(--border-color);
    background: var(--bg);
    z-index: 5;
    margin-top: auto; /* Push to bottom */
}

/* Generate Button */
.stButton button {
    background: var(--ink) !important;
    color: var(--bg) !important;
    border: none !important;
    border-radius: 0 !important;
    padding: var(--space-md) var(--space-xl) !important;
    font-family: inherit !important;
    font-size: 14px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    width: 100%;
    position: relative;
    overflow: hidden;
    transition: all 0.2s !important;
}

.stButton button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.stButton button::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: linear-gradient(45deg, var(--accent-red), var(--accent-blue));
    opacity: 0;
    transition: opacity 0.3s;
    z-index: 1;
}

.stButton button:hover::before {
    opacity: 1;
}

.stButton button > div {
    position: relative;
    z-index: 2;
}

/* ── Noise Overlay ───────────────────────────────────────────────── */
.noise-overlay {
    position: fixed;
    top: 0; left: 0; width: 100%; height: 100%;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)' opacity='0.05'/%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 100;
    opacity: 0.4;
}

/* ── Spacing in Columns ──────────────────────────────────────────── */
[data-testid="stVerticalBlock"] {
    gap: 0 !important; /* Control via element margins */
}

.stElementContainer {
    margin: 0 0 var(--space-md) 0 !important; /* Consistent bottom spacing */
}

/* Remove bottom margin from the last element to avoid double padding */
.stElementContainer:last-child {
    margin-bottom: 0 !important;
}

/* ── Output Column Alignment ─────────────────────────────────────── */
/* Center EVERYTHING in the 3rd column (Output) */
[data-testid="stColumn"]:nth-child(3) [data-testid="stVerticalBlock"] {
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}

/* Ensure video/images are also centered */
[data-testid="stColumn"]:nth-child(3) .stVideo, 
[data-testid="stColumn"]:nth-child(3) .stImage {
    margin: auto;
    max-width: 100%;
}

[data-testid="stColumn"]:nth-child(3) video {
    max-height: 80vh; /* Prevent overflow */
}
</style>

<!-- ── Functional Components (Restored & Restyled) ────────────────── -->
<style>
.stat-row {
    display: flex;
    gap: 0;
    margin: var(--space-lg);
    border: 1px solid var(--border-color);
}

.stat-item {
    flex: 1;
    text-align: center;
    padding: var(--space-md);
    border-right: 1px solid var(--border-color);
}

.stat-item:last-child {
    border-right: none;
}

.stat-value {
    font-size: 24px;
    font-weight: 300;
}

.stat-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    opacity: 0.5;
    margin-top: 4px;
}

.workflow-steps {
    display: flex;
    margin: 0 var(--space-lg) var(--space-lg);
    border: 1px solid var(--border-color);
}

.workflow-step {
    flex: 1;
    padding: var(--space-sm) var(--space-md);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-right: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    gap: 6px;
    opacity: 0.5;
}

.workflow-step:last-child {
    border-right: none;
}

.workflow-step-active, .workflow-step-done {
    opacity: 1;
    background: #f5f5f5;
}

.workflow-num {
    border: 1px solid currentColor;
    width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-size: 9px;
}

.readiness-bar {
    padding: 0 var(--space-lg) var(--space-lg);
    display: flex;
    gap: var(--space-md);
    flex-wrap: wrap;
}

.segment-card {
    margin: 0 var(--space-lg) var(--space-sm);
    padding: var(--space-md);
    border: 1px solid var(--border-color);
}

.file-status {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 2px 6px;
    border-radius: 2px;
    background: #f5f5f5;
    color: #666;
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

.file-status-ok {
    background: #e6f4ea;
    color: #1e8e3e;
}

.file-status-warn {
    background: #fef7e0;
    color: #b06000;
}

.file-status-error {
    background: #fce8e6;
    color: #c5221f;
}
</style>

<!-- Fixed Sidebar Injection -->
<aside class="custom-sidebar">
    <span>TIKTOK • AUTOMATION • STUDIO</span>
    <span class="version" style="font-size: 14px; margin-top: auto; writing-mode: horizontal-tb; transform: rotate(180deg);">V.01</span>
</aside>
<div class="noise-overlay"></div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# JS-based translation & adjustments
# ---------------------------------------------------------------------------
import streamlit.components.v1 as _components

_components.html(
    """
<script>
(function() {
    var doc = window.parent.document;
    if (!doc) return;
    
    // Translation map
    var T = {
        'Drag and drop file here': 'Drag file or browse \u2197',
        'Drag and drop files here': 'Drag files or browse \u2197',
        'Browse files': 'browse', 
        'Limit 200MB per file': 'Max 400MB'
    };
    
    function updateDOM() {
        // Update file uploader instructions
        doc.querySelectorAll('[data-testid="stFileUploaderDropzoneInstructions"]').forEach(function(el) {
            el.style.display = 'none'; // We hide default text, maybe inject custom?
        });
        
        // We can try to replace text content if visible
    }
    
    // new MutationObserver(function() { requestAnimationFrame(updateDOM); })
    //    .observe(doc.body, {childList: true, subtree: true});
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
# Three-column layout: Assets | Settings | Output
# ---------------------------------------------------------------------------
col_assets, col_settings, col_output = st.columns([1, 1, 2])

# ---------------------------------------------------------------------------
# Left column — Assets
# ---------------------------------------------------------------------------
with col_assets:
    st.markdown(
        '<header class="section-header">'
        "<h2>Assets</h2>"
        '<span class="diamonds">◆◆◆</span></header>',
        unsafe_allow_html=True,
    )

    # .01 Script
    st.markdown(
        '<div class="upload-item">'
        '<div class="upload-header">'
        '<span class="upload-title"><span class="num-index">.01</span>Скрипт</span>'
        '<span class="file-status">REQUIRED</span></div>'
        '<div class="label">Markdown (.md) • Max 400MB</div>'
        '<p style="font-size: 11px; margin-bottom: 8px; color: #666; line-height: 1.4;">Загрузите сценарий с таймкодами и озвучкой.</p>'
        '</div>',
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
        '<div class="upload-item">'
        '<div class="upload-header">'
        '<span class="upload-title"><span class="num-index">.02</span>Аватар</span>'
        '<span class="file-status">REQUIRED</span></div>'
        '<div class="label">Source Video (.mp4) • Max 400MB</div>'
        '<p style="font-size: 11px; margin-bottom: 8px; color: #666; line-height: 1.4;">Видео с AI-аватаром, по одному на клип.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    avatar_files = st.file_uploader(
        "Аватары",
        type=["mp4"],
        accept_multiple_files=True,
        help=(
            "Видео с AI-аватарами (Higgsfield, HeyGen и т.д.). "
            "По одному файлу на каждый клип в скрипте. "
            "Порядок определяется по имени файла."
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
        '<div class="upload-item">'
        '<div class="upload-header">'
        '<span class="upload-title"><span class="num-index">.03</span>Скринкаст</span>'
        '<span class="file-status" style="opacity: 0.5;">OPTIONAL</span></div>'
        '<div class="label">B-Roll / Demo (.mp4) • Max 400MB</div>'
        '<p style="font-size: 11px; margin-bottom: 8px; color: #666; line-height: 1.4;">Запись экрана для наложения на видео.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    screencast_files = st.file_uploader(
        "Скринкасты",
        type=["mp4"],
        accept_multiple_files=True,
        help=(
            "Записи экрана приложения для наложения на видео. "
            "Имя файла должно совпадать с тегом [screencast: ...] в скрипте."
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

    # .04 Audio
    st.markdown(
        '<div class="upload-item" style="border-bottom: none;">'
        '<div class="upload-header">'
        '<span class="upload-title"><span class="num-index">.04</span>Музыка</span>'
        '<span class="file-status" style="opacity: 0.5;">OPTIONAL</span></div>'
        '<div class="label">Background Track (.mp3, .wav) • Max 400MB</div>'
        '<p style="font-size: 11px; margin-bottom: 8px; color: #666; line-height: 1.4;">Фоновый трек, зацикленный на длину видео.</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    music_file_upload = st.file_uploader(
        "Музыка",
        type=["mp3", "wav", "m4a", "ogg"],
        help="Фоновый музыкальный трек (MP3, WAV, M4A, OGG).",
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

if script_files and not all_scripts:
    with col_assets:
        st.error(
            "Загруженные файлы не содержат скриптов в формате UGCKit. "
            'Проверьте формат: ### Script A1: "Название"'
        )

cfg = load_config()

music_path = None
if music_file_upload:
    music_path = TMP / music_file_upload.name
    music_path.write_bytes(music_file_upload.getbuffer())

# ---------------------------------------------------------------------------
# Middle column — Settings
# ---------------------------------------------------------------------------
with col_settings:
    st.markdown(
        '<header class="section-header">'
        "<h2>Settings</h2>"
        '<span class="diamonds">◆◆◆</span></header>',
        unsafe_allow_html=True,
    )

    # Composition mode
    st.markdown(
        '<div class="control-group" style="padding-bottom: 0; border-bottom: none;"><div class="label">Режим композиции</div></div>',
        unsafe_allow_html=True,
    )
    comp_mode = st.radio(
        "Режим композиции",
        list(MODE_MAP.keys()),
        horizontal=True,
        help=(
            "Оверлей: аватар на весь экран, скринкаст в углу. "
            "PiP: скринкаст на весь экран, голова аватара в углу. "
            "Сплит: аватар и скринкаст рядом. "
            "Хромакей: фон аватара удаляется."
        ),
        label_visibility="collapsed",
    )
    selected_mode = MODE_MAP[comp_mode]
    st.markdown(
        f'<div class="control-group" style="padding-top: 0;"><p style="font-size: 11px; margin-top: 8px; color: #666; line-height: 1.4;">'
        f"{MODE_DESCRIPTIONS[comp_mode]}</p></div>",
        unsafe_allow_html=True,
    )

    # Mode-specific settings
    if selected_mode == CompositionMode.OVERLAY:
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
        overlay_position = _pos_selectbox(
            "Позиция скринкаста",
            cfg.composition.overlay.position.value,
            "Угол экрана для размещения скринкаста.",
        )
        cfg.composition.overlay.position = Position(overlay_position)
        overlay_margin = st.number_input(
            "Отступ (пкс.)",
            0,
            200,
            cfg.composition.overlay.margin,
            help="Расстояние от края кадра. 30–70 рекомендуемо.",
        )
        cfg.composition.overlay.margin = overlay_margin

    elif selected_mode == CompositionMode.PIP:
        pip_head_scale = st.slider(
            "Размер головы",
            10,
            50,
            int(cfg.composition.pip.head_scale * 100),
            5,
            format="%d%%",
            help="Размер круглой вырезки головы аватара.",
        )
        cfg.composition.pip.head_scale = pip_head_scale / 100
        pip_head_position = _pos_selectbox(
            "Позиция головы",
            cfg.composition.pip.head_position.value,
            "Угол экрана для головы аватара.",
        )
        cfg.composition.pip.head_position = Position(pip_head_position)

    elif selected_mode == CompositionMode.SPLIT:
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
            help="На какой стороне экрана будет аватар.",
        )
        cfg.composition.split.avatar_side = side_values[side_options.index(side_display)]
        split_ratio = st.slider(
            "Пропорция разделения",
            30,
            70,
            50,
            5,
            format="%d%%",
            help="Доля ширины для аватара. 50% = пополам.",
        )
        cfg.composition.split.split_ratio = split_ratio / 100

    elif selected_mode == CompositionMode.GREENSCREEN:
        gs_avatar_scale = st.slider(
            "Масштаб аватара",
            30,
            100,
            80,
            5,
            format="%d%%",
            help="Размер прозрачного аватара. Требует rembg.",
        )
        cfg.composition.greenscreen.avatar_scale = gs_avatar_scale / 100
        gs_avatar_position = _pos_selectbox(
            "Позиция аватара",
            "bottom-right",
            "Угол экрана для аватара поверх скринкаста.",
        )
        cfg.composition.greenscreen.avatar_position = Position(gs_avatar_position)

    # Video quality
    st.markdown(
        '<div class="control-group" style="padding-bottom: 0; border-bottom: none;"><div class="label">Качество видео (CRF)</div></div>',
        unsafe_allow_html=True,
    )
    crf = st.slider(
        "Качество видео",
        15,
        35,
        cfg.output.crf,
        help="Чем ниже — тем лучше качество. 18–23 оптимально для соцсетей.",
        label_visibility="collapsed",
    )
    st.markdown('<div class="control-group" style="padding-top: 0;"></div>', unsafe_allow_html=True)

    # Output format
    st.markdown(
        '<div class="control-group" style="padding-bottom: 0; border-bottom: none;"><div class="label">Формат видео</div></div>',
        unsafe_allow_html=True,
    )
    codec_options = ["H.264 (MP4) — Fast encoding", "H.265 (HEVC) — Smaller file size"]
    codec_values = ["libx264", "libx265"]
    codec_idx = 0 if cfg.output.codec == "libx264" else 1
    codec_display = st.selectbox(
        "Формат видео",
        codec_options,
        index=codec_idx,
        help="H.264 — быстрее, H.265 — компактнее.",
        label_visibility="collapsed",
    )
    codec = codec_values[codec_options.index(codec_display)]
    st.markdown(
        '<div class="control-group" style="padding-top: 0;"><p style="font-size: 11px; margin-top: 8px; color: #666; line-height: 1.4;">'
        "H.264 — быстрое кодирование и широкая совместимость.</p></div>",
        unsafe_allow_html=True,
    )

    # Audio target volume
    st.markdown(
        '<div class="control-group" style="padding-bottom: 0; border-bottom: none;"><div class="label">Целевая громкость (LUFS)</div></div>',
        unsafe_allow_html=True,
    )
    normalize_audio = st.checkbox(
        "Нормализация громкости",
        value=cfg.audio.normalize,
        help="Выравнивание громкости по стандарту LUFS.",
    )
    if normalize_audio:
        target_loudness = st.slider(
            "Целевая громкость",
            -24,
            -8,
            cfg.audio.target_loudness,
            help="Стандарт для соцсетей: -14 LUFS.",
            label_visibility="collapsed",
        )
    else:
        target_loudness = cfg.audio.target_loudness
    st.markdown('<div class="control-group" style="padding-top: 0;"></div>', unsafe_allow_html=True)

    if music_path:
        st.markdown(
            '<div class="control-group" style="padding-bottom: 0; border-bottom: none;"><div class="label">Фоновая музыка</div></div>',
            unsafe_allow_html=True,
        )
        music_volume = st.slider(
            "Громкость музыки",
            0,
            100,
            15,
            5,
            format="%d%%",
            help="Уровень музыки относительно озвучки. 15% — фон.",
            label_visibility="collapsed",
        )
        music_fade_out = st.slider(
            "Затухание (сек.)",
            0.0,
            10.0,
            2.0,
            0.5,
            help="Длительность затухания музыки в конце.",
            label_visibility="collapsed",
        )
        st.markdown('<div class="control-group" style="padding-top: 0;"></div>', unsafe_allow_html=True)
    else:
        music_volume = 15
        music_fade_out = 2.0

    # Smart Subtitles (toggle style like mockup)
    st.markdown(
        '<div class="control-group" style="border-bottom: none; padding-bottom: 0;">',
        unsafe_allow_html=True,
    )
    enable_subtitles = st.checkbox(
        "Smart Subtitles",
        value=False,
        help="Караоке-субтитры на основе Whisper.",
    )
    st.markdown(
        '<p style="font-size: 11px; margin-top: 8px; color: #666; line-height: 1.4;">'
        "Авто-синхронизация субтитров с речью.</p></div>",
        unsafe_allow_html=True,
    )
    if enable_subtitles:
        subtitle_font_size = st.slider(
            "Размер шрифта субтитров",
            24,
            96,
            48,
            help="48 — стандарт для 1080x1920.",
            label_visibility="collapsed",
        )
    else:
        subtitle_font_size = 48

    # Smart Sync (toggle style)
    st.markdown(
        '<div class="control-group" style="border-bottom: none; padding-bottom: 0;">',
        unsafe_allow_html=True,
    )
    enable_sync = st.checkbox(
        "Smart Sync",
        value=False,
        help="Тайминг скринкастов по ключевым словам в речи.",
    )
    st.markdown(
        '<p style="font-size: 11px; margin-top: 8px; color: #666; line-height: 1.4;">'
        "Авто-определение тайминга скринкастов по ключевым словам.</p></div>",
        unsafe_allow_html=True,
    )

    if enable_sync or enable_subtitles:
        st.markdown(
            '<div class="control-group"><div class="label">МОДЕЛЬ WHISPER</div></div>',
            unsafe_allow_html=True,
        )
        whisper_model = st.selectbox(
            "Модель Whisper",
            ["tiny", "base", "small", "medium", "large"],
            index=1,
            help="base — баланс скорости и качества.",
            label_visibility="collapsed",
        )
        st.markdown('<div class="control-group" style="padding-top: 0;"></div>', unsafe_allow_html=True)
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
# Right column — Output
# ---------------------------------------------------------------------------
with col_output:
    if not all_scripts:
        st.markdown(
            '<div class="gradient-orb"></div>'
            '<svg class="wireframe-svg" viewBox="0 0 500 800">'
            '<ellipse cx="250" cy="400" rx="300" ry="200" fill="none" stroke="black" '
            'stroke-width="0.5" transform="rotate(-30 250 400)"/>'
            '<ellipse cx="250" cy="400" rx="300" ry="200" fill="none" stroke="black" '
            'stroke-width="0.5" transform="rotate(30 250 400)"/>'
            "</svg>"
            '<header class="section-header" style="background:transparent; border-bottom:none;">'
            "<h2>Output</h2>"
            '<span class="diamonds">◆◆◆</span></header>'
            '<div class="preview-canvas">'
            '<div class="preview-placeholder">'
            '<div class="preview-text">'
            '<span style="display:block; font-size:11px; margin-bottom:8px; letter-spacing:0.05em;">ПРЕВЬЮ</span>'
            'Ожидание файлов'
            "</div></div></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="build-bar">'
            '<div style="display:flex; flex-direction:column;">'
            '<span class="status-text">ПРИМ. РЕНДЕР: ~45С</span>'
            '<span class="status-text" style="opacity:0.5">ОЧЕРЕДЬ: ПУСТО</span></div>'
            '</div>',
            unsafe_allow_html=True,
        )
        # Button follows build-bar div visually or we place it?
        # In empty state, no button usually, or just a dummy?
        # The design shows "Generate Video" button even in empty "Wait for Input"?
        # Let's add a disabled mock button if needed, or just leave it.
    else:
        st.markdown(
            '<header class="section-header" style="background:transparent; border-bottom:none;">'
            "<h2>Output</h2>"
            '<span class="diamonds">◆◆◆</span></header>',
            unsafe_allow_html=True,
        )

        # Script selector
        script_options = {f"{s.script_id}: {s.title}": s for s in all_scripts}
        selected_label = st.selectbox(
            "Скрипт",
            list(script_options.keys()),
            help="Выберите сценарий для сборки.",
        )
        selected_script = script_options[selected_label]

        # Stats
        total_segments = sum(len(s.segments) for s in all_scripts)
        total_duration = sum(s.total_duration for s in all_scripts)
        st.markdown(
            f'<div class="stat-row">'
            f'<div class="stat-item"><div class="stat-value">{len(all_scripts)}</div>'
            f'<div class="stat-label">Скриптов</div></div>'
            f'<div class="stat-item"><div class="stat-value">{total_segments}</div>'
            f'<div class="stat-label">Сегментов</div></div>'
            f'<div class="stat-item"><div class="stat-value">{total_duration:.0f}с</div>'
            f'<div class="stat-label">Длительность</div></div></div>',
            unsafe_allow_html=True,
        )

        # Dynamic workflow steps
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
            f'<div class="{_step_cls(step1_done)}"><div class="workflow-num">{"&#9670;" if step1_done else "1"}</div>Скрипт</div>'
            f'<div class="{_step_cls(step2_done)}"><div class="workflow-num">{"&#9670;" if step2_done else "2"}</div>Аватары ({avs_count}/{segs_count})</div>'
            f'<div class="{_step_cls(False, step3_active)}"><div class="workflow-num">3</div>Таймлайн</div>'
            f'<div class="{_step_cls(False)}"><div class="workflow-num">4</div>Сборка</div></div>',
            unsafe_allow_html=True,
        )

        # Readiness indicator
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

        # Avatar binding
        sid = selected_script.script_id.upper()
        prefix_matched = sorted([f for f in available_avatars if f.stem.upper().startswith(sid)])
        matched_avatars = prefix_matched if prefix_matched else available_avatars

        if matched_avatars:
            binding_title = (
                f"Привязка аватаров ({min(len(matched_avatars), segs_count)}/{segs_count})"
            )
            with st.expander(binding_title, expanded=False):
                for i, seg in enumerate(selected_script.segments):
                    if i < len(matched_avatars):
                        st.markdown(
                            f'<div style="display:flex; align-items:center; gap:.5rem; '
                            f'padding:.4rem 0; font-size:.82rem;">'
                            f'<div class="segment-badge">{seg.id}</div>'
                            f'<span style="color:var(--text-secondary);">\u2192</span>'
                            f"<span>{matched_avatars[i].name}</span></div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.warning(
                            f"Сегмент {seg.id} — нет аватара. "
                            f"Загрузите файл {sid}_clip{seg.id}.mp4."
                        )

            if avs_count > segs_count:
                st.info(f"Будут использованы первые {segs_count} из {avs_count} аватаров.")

        # Auto timeline preview
        if step3_active and matched_avatars:
            if selected_mode != CompositionMode.OVERLAY:
                for seg in selected_script.segments:
                    for sc in seg.screencasts:
                        sc.mode = selected_mode

            script_to_use = selected_script
            if enable_sync:
                with st.spinner(f"Whisper ({whisper_model}) синхронизация..."):
                    synced = apply_sync(selected_script, matched_avatars, whisper_model)
                    if synced is not selected_script:
                        script_to_use = synced
                    else:
                        st.warning("Синхронизация не удалась.")

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

        # Compose button
        st.markdown("")
        can_compose = step3_active and matched_avatars and timeline is not None

        if st.button(
            "Собрать видео",
            type="primary",
            use_container_width=True,
            disabled=not can_compose,
        ):
            try:
                head_videos = None
                transparent_avatars = None

                if selected_mode == CompositionMode.PIP:
                    with st.spinner("Генерация вырезки головы для PiP..."):
                        head_videos = prepare_pip_videos(matched_avatars, cfg) or None
                    if not head_videos:
                        st.warning("PiP обработка не удалась.")

                elif selected_mode == CompositionMode.GREENSCREEN:
                    with st.spinner("Удаление фона аватаров..."):
                        transparent_avatars = (
                            prepare_greenscreen_videos(matched_avatars, cfg) or None
                        )
                    if not transparent_avatars:
                        st.warning("Удаление фона не удалось.")

                subtitle_file = None
                if cfg.subtitles.enabled:
                    with st.spinner("Генерация субтитров..."):
                        subtitle_file = generate_subtitles(timeline, matched_avatars, cfg)
                    if not subtitle_file:
                        st.warning("Субтитры не удалось сгенерировать.")

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

                st.session_state["last_output"] = result_path
                file_size_mb = result_path.stat().st_size / 1024 / 1024
                st.success(f"Готово! {result_path.name} ({file_size_mb:.1f} МБ)")
            except (ValueError, FFmpegError) as e:
                st.error(str(e))

        # Show last result
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
            st.markdown(
                '<div class="preview-canvas">'
                '<div class="gradient-orb"></div>'
                '<svg class="wireframe-svg" viewBox="0 0 500 800">'
                '<ellipse cx="250" cy="400" rx="300" ry="200" fill="none" stroke="black" '
                'stroke-width="0.5" transform="rotate(-30 250 400)"/>'
                '<ellipse cx="250" cy="400" rx="300" ry="200" fill="none" stroke="black" '
                'stroke-width="0.5" transform="rotate(30 250 400)"/>'
                "</svg>"
                '<div class="preview-placeholder">'
                '<div style="text-align:center;">'
                '<span class="preview-label" style="display:block;">ПРЕВЬЮ</span>'
                '<span class="preview-text">Ожидание файлов</span>'
                "</div></div></div>",
                unsafe_allow_html=True,
            )

        # Build bar
        est_render = f"~{int(selected_script.total_duration * 1.5)}С"
        st.markdown(
            f'<div class="build-bar">'
            f'<div><div class="status-text">ПРИМ. РЕНДЕР: {est_render}</div>'
            f'<div class="status-text" style="opacity:.5">ОЧЕРЕДЬ: ПУСТО</div></div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        # Batch compose
        st.markdown("---")
        with st.expander("Пакетная сборка всех скриптов"):
            st.markdown(
                '<div style="font-size:.85rem; color:var(--text-secondary); margin-bottom:.75rem;">'
                "Соберёт все загруженные скрипты. Аватары привязываются автоматически "
                "по префиксу. Используются текущие настройки.</div>",
                unsafe_allow_html=True,
            )
            confirm_batch = st.checkbox(
                "Подтверждаю пакетную сборку",
                help="Поставьте галочку и нажмите кнопку ниже.",
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
