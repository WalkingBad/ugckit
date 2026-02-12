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
from ugckit.models import Position
from ugckit.parser import parse_scripts_directory

st.set_page_config(page_title="UGCKit", page_icon="🎬", layout="wide")

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
# Sidebar: file uploads
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Upload Files")

    script_files = st.file_uploader("Scripts (.md)", type=["md"], accept_multiple_files=True)
    if script_files:
        save_uploads(script_files, SCRIPTS_DIR)

    avatar_files = st.file_uploader("Avatars (.mp4)", type=["mp4"], accept_multiple_files=True)
    if avatar_files:
        save_uploads(avatar_files, AVATARS_DIR)

    screencast_files = st.file_uploader(
        "Screencasts (.mp4)", type=["mp4"], accept_multiple_files=True
    )
    if screencast_files:
        save_uploads(screencast_files, SCREENCASTS_DIR)

    st.divider()
    st.caption("Scripts and avatars on disk are also detected.")

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
    st.subheader("Composition Settings")
    cfg = load_config()

    col1, col2 = st.columns(2)
    with col1:
        overlay_scale = st.slider("Overlay scale", 0.1, 0.8, cfg.composition.overlay.scale, 0.05)
        overlay_position = st.selectbox(
            "Overlay position",
            [p.value for p in Position],
            index=[p.value for p in Position].index(cfg.composition.overlay.position.value),
        )
        overlay_margin = st.number_input(
            "Overlay margin (px)", 0, 200, cfg.composition.overlay.margin
        )

    with col2:
        crf = st.slider("CRF (quality)", 15, 35, cfg.output.crf)
        codec = st.selectbox(
            "Codec", ["libx264", "libx265"], index=0 if cfg.output.codec == "libx264" else 1
        )
        normalize_audio = st.checkbox("Normalize audio", value=cfg.audio.normalize)
        target_loudness = st.slider("Target loudness (LUFS)", -24, -8, cfg.audio.target_loudness)

    # Apply settings to config
    cfg.composition.overlay.scale = overlay_scale
    cfg.composition.overlay.position = Position(overlay_position)
    cfg.composition.overlay.margin = overlay_margin
    cfg.output.crf = crf
    cfg.output.codec = codec
    cfg.audio.normalize = normalize_audio
    cfg.audio.target_loudness = target_loudness

# ---------------------------------------------------------------------------
# Scripts tab
# ---------------------------------------------------------------------------
with tab_scripts:
    st.subheader("Parsed Scripts")

    if not all_scripts:
        st.info("Upload script .md files in the sidebar to get started.")
    else:
        for script in all_scripts:
            with st.expander(
                f"{script.script_id}: {script.title}  "
                f"({len(script.segments)} segments, ~{script.total_duration:.0f}s)"
            ):
                for seg in script.segments:
                    st.markdown(f"**Clip {seg.id}** ({seg.duration:.0f}s)")
                    st.text(seg.text)
                    for sc in seg.screencasts:
                        st.caption(
                            f"  screencast: {sc.file} @ {sc.start}s-{sc.end}s ({sc.mode.value})"
                        )

# ---------------------------------------------------------------------------
# Compose tab
# ---------------------------------------------------------------------------
with tab_compose:
    st.subheader("Compose Video")

    if not all_scripts:
        st.info("Upload scripts first.")
    else:
        script_options = {f"{s.script_id}: {s.title}": s for s in all_scripts}
        selected_label = st.selectbox("Select script", list(script_options.keys()))
        selected_script = script_options[selected_label]

        # Avatar mapping
        available_avatars = sorted(AVATARS_DIR.glob("*.mp4"))
        st.markdown(
            f"**Segments:** {len(selected_script.segments)}  |  "
            f"**Available avatars:** {len(available_avatars)}"
        )

        # Auto-match: try prefix match, else assign in order
        sid = selected_script.script_id.upper()
        prefix_matched = sorted([f for f in available_avatars if f.stem.upper().startswith(sid)])
        if prefix_matched:
            matched_avatars = prefix_matched
        else:
            matched_avatars = available_avatars

        if matched_avatars:
            with st.expander("Avatar mapping", expanded=False):
                for i, seg in enumerate(selected_script.segments):
                    if i < len(matched_avatars):
                        st.text(f"Segment {seg.id} -> {matched_avatars[i].name}")
                    else:
                        st.warning(f"Segment {seg.id} -> (no avatar)")

        col_preview, col_compose = st.columns(2)

        # Preview timeline
        with col_preview:
            if st.button("Preview Timeline", use_container_width=True):
                if not matched_avatars:
                    st.error("No avatar files available.")
                else:
                    output_path = OUTPUT_DIR / f"{selected_script.script_id}.mp4"
                    try:
                        timeline = build_timeline(
                            script=selected_script,
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
            if st.button("Compose Video", type="primary", use_container_width=True):
                if not matched_avatars:
                    st.error("No avatar files available.")
                else:
                    output_path = OUTPUT_DIR / f"{selected_script.script_id}.mp4"
                    try:
                        timeline = build_timeline(
                            script=selected_script,
                            avatar_clips=matched_avatars,
                            screencasts_dir=SCREENCASTS_DIR,
                            output_path=output_path,
                        )
                        progress_bar = st.progress(0.0, text="Rendering...")
                        result_path = compose_video_with_progress(
                            timeline,
                            cfg,
                            progress_callback=lambda p: progress_bar.progress(
                                p, text=f"Rendering... {p:.0%}"
                            ),
                        )
                        st.success(f"Done! {result_path.name}")

                        with open(result_path, "rb") as vf:
                            st.download_button(
                                "Download Video",
                                data=vf,
                                file_name=result_path.name,
                                mime="video/mp4",
                                use_container_width=True,
                            )
                    except (ValueError, FFmpegError) as e:
                        st.error(str(e))

        # Batch compose
        st.divider()
        if st.button("Compose All Scripts"):
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
                    st.success(f"[{script.script_id}] Done!")
                    with open(result_path, "rb") as vf:
                        st.download_button(
                            f"Download {result_path.name}",
                            data=vf,
                            file_name=result_path.name,
                            mime="video/mp4",
                        )
                except (ValueError, FFmpegError) as e:
                    st.error(f"[{script.script_id}] {e}")
