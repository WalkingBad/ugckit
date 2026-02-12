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

st.set_page_config(page_title="UGCKit - Сборка UGC видео", page_icon="🎬", layout="wide")

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
    st.header("Загрузка файлов")
    st.caption("Загрузите файлы для сборки видео")

    script_files = st.file_uploader(
        "Скрипты (.md)",
        type=["md"],
        accept_multiple_files=True,
        help='Markdown-файлы со скриптами видео. Формат: ### Script A1: "Название"',
    )
    if script_files:
        save_uploads(script_files, SCRIPTS_DIR)

    avatar_files = st.file_uploader(
        "Аватары (.mp4)",
        type=["mp4"],
        accept_multiple_files=True,
        help="Видео с AI-аватарами (по одному на сегмент). Порядок определяется именем файла.",
    )
    if avatar_files:
        save_uploads(avatar_files, AVATARS_DIR)

    screencast_files = st.file_uploader(
        "Скринкасты (.mp4)",
        type=["mp4"],
        accept_multiple_files=True,
        help="Записи экрана приложения для наложения на видео.",
    )
    if screencast_files:
        save_uploads(screencast_files, SCREENCASTS_DIR)

    st.divider()
    st.caption("Скрипты и аватары с диска также обнаруживаются автоматически.")

# ---------------------------------------------------------------------------
# Parse scripts
# ---------------------------------------------------------------------------
all_scripts = parse_scripts_directory(SCRIPTS_DIR)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_scripts, tab_compose, tab_settings = st.tabs(["Скрипты", "Сборка", "Настройки"])

# ---------------------------------------------------------------------------
# Settings tab (load first so compose uses latest values)
# ---------------------------------------------------------------------------
with tab_settings:
    st.subheader("Настройки композиции")
    cfg = load_config()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Режим наложения (Overlay)**")
        overlay_scale = st.slider(
            "Масштаб скринкаста",
            0.1,
            0.8,
            cfg.composition.overlay.scale,
            0.05,
            help="Размер скринкаста относительно ширины видео",
        )
        overlay_position = st.selectbox(
            "Позиция скринкаста",
            [p.value for p in Position],
            index=[p.value for p in Position].index(cfg.composition.overlay.position.value),
            help="Угол экрана для размещения скринкаста",
        )
        overlay_margin = st.number_input(
            "Отступ от края (пикс.)",
            0,
            200,
            cfg.composition.overlay.margin,
            help="Отступ скринкаста от края видео",
        )

        st.divider()
        st.markdown("**Режим картинка-в-картинке (PiP)**")
        pip_head_scale = st.slider(
            "Размер головы",
            0.1,
            0.5,
            cfg.composition.pip.head_scale,
            0.05,
            help="Размер вырезки головы аватара относительно ширины видео",
        )
        pip_head_position = st.selectbox(
            "Позиция головы",
            [p.value for p in Position],
            index=[p.value for p in Position].index(cfg.composition.pip.head_position.value),
            help="Угол экрана для размещения головы аватара",
        )

    with col2:
        st.markdown("**Выходное видео**")
        crf = st.slider(
            "CRF (качество)",
            15,
            35,
            cfg.output.crf,
            help="Качество видео: меньше = лучше качество, но тяжелее файл",
        )
        codec = st.selectbox(
            "Кодек",
            ["libx264", "libx265"],
            index=0 if cfg.output.codec == "libx264" else 1,
            help="H.264 — быстрее, H.265 — компактнее",
        )

        st.divider()
        st.markdown("**Аудио**")
        normalize_audio = st.checkbox(
            "Нормализация звука",
            value=cfg.audio.normalize,
            help="Выравнивание громкости по стандарту LUFS",
        )
        target_loudness = st.slider(
            "Целевая громкость (LUFS)",
            -24,
            -8,
            cfg.audio.target_loudness,
            help="Стандарт для соцсетей: -14 LUFS",
        )

        st.divider()
        st.markdown("**Smart Sync (Whisper)**")
        enable_sync = st.checkbox(
            "Авто-синхронизация (Whisper)",
            value=False,
            help="Автоматическое определение тайминга скринкастов по ключевым словам в речи",
        )
        sync_model = st.selectbox(
            "Модель Whisper",
            ["tiny", "base", "small", "medium", "large"],
            index=1,
            help="Чем больше модель, тем точнее, но медленнее",
        )

    # Apply settings to config
    cfg.composition.overlay.scale = overlay_scale
    cfg.composition.overlay.position = Position(overlay_position)
    cfg.composition.overlay.margin = overlay_margin
    cfg.composition.pip.head_scale = pip_head_scale
    cfg.composition.pip.head_position = Position(pip_head_position)
    cfg.output.crf = crf
    cfg.output.codec = codec
    cfg.audio.normalize = normalize_audio
    cfg.audio.target_loudness = target_loudness

# ---------------------------------------------------------------------------
# Scripts tab
# ---------------------------------------------------------------------------
with tab_scripts:
    st.subheader("Скрипты")

    st.info(
        "Загрузите .md файлы скриптов в боковую панель слева.\n\n"
        "Формат скрипта:\n"
        "```\n"
        '### Script A1: "Название"\n'
        "**Clip 1 (8s):**\n"
        'Says: "Текст озвучки"\n'
        "[screencast: app @ 1.5-5.0 mode:overlay]\n"
        "```"
    )

    if not all_scripts:
        st.warning("Скрипты не найдены. Загрузите .md файлы в боковую панель.")
    else:
        st.success(f"Найдено скриптов: {len(all_scripts)}")
        for script in all_scripts:
            with st.expander(
                f"{script.script_id}: {script.title}  "
                f"({len(script.segments)} сегм., ~{script.total_duration:.0f}с)"
            ):
                for seg in script.segments:
                    st.markdown(f"**Клип {seg.id}** ({seg.duration:.0f}с)")
                    st.text(seg.text)
                    for sc in seg.screencasts:
                        mode_label = "PiP" if sc.mode == CompositionMode.PIP else "Overlay"
                        if sc.start_keyword:
                            st.caption(
                                f'  скринкаст: {sc.file} @ word:"{sc.start_keyword}"-word:"{sc.end_keyword}" ({mode_label})'
                            )
                        else:
                            st.caption(
                                f"  скринкаст: {sc.file} @ {sc.start}с-{sc.end}с ({mode_label})"
                            )

# ---------------------------------------------------------------------------
# Compose tab
# ---------------------------------------------------------------------------
with tab_compose:
    st.subheader("Сборка видео")

    st.info(
        "**Порядок работы:**\n"
        "1. Загрузите скрипт (.md) в боковую панель\n"
        "2. Загрузите аватары (.mp4) — по одному на сегмент\n"
        "3. Нажмите «Превью» для проверки таймлайна\n"
        "4. Нажмите «Собрать видео» для рендеринга"
    )

    if not all_scripts:
        st.warning("Сначала загрузите скрипты.")
    else:
        script_options = {f"{s.script_id}: {s.title}": s for s in all_scripts}
        selected_label = st.selectbox("Выберите скрипт", list(script_options.keys()))
        selected_script = script_options[selected_label]

        # Composition mode selector
        comp_mode = st.radio(
            "Режим композиции",
            ["Оверлей", "Картинка-в-картинке (PiP)"],
            horizontal=True,
            help="Оверлей: аватар на фоне, скринкаст в углу. PiP: скринкаст на весь экран, голова аватара в углу.",
        )
        use_pip = comp_mode == "Картинка-в-картинке (PiP)"

        # Avatar mapping
        available_avatars = sorted(AVATARS_DIR.glob("*.mp4"))
        st.markdown(
            f"**Сегментов:** {len(selected_script.segments)}  |  "
            f"**Доступно аватаров:** {len(available_avatars)}"
        )

        # Auto-match: try prefix match, else assign in order
        sid = selected_script.script_id.upper()
        prefix_matched = sorted([f for f in available_avatars if f.stem.upper().startswith(sid)])
        if prefix_matched:
            matched_avatars = prefix_matched
        else:
            matched_avatars = available_avatars

        if matched_avatars:
            with st.expander("Привязка аватаров", expanded=False):
                for i, seg in enumerate(selected_script.segments):
                    if i < len(matched_avatars):
                        st.text(f"Сегмент {seg.id} -> {matched_avatars[i].name}")
                    else:
                        st.warning(f"Сегмент {seg.id} -> (нет аватара)")

        col_preview, col_compose = st.columns(2)

        # Preview timeline
        with col_preview:
            if st.button("Превью таймлайна", use_container_width=True):
                if not matched_avatars:
                    st.error("Нет доступных аватаров.")
                else:
                    # Apply PiP mode to screencasts if selected
                    if use_pip:
                        for seg in selected_script.segments:
                            for sc in seg.screencasts:
                                sc.mode = CompositionMode.PIP

                    # Apply sync if enabled
                    script_to_use = selected_script
                    if enable_sync:
                        try:
                            from ugckit.sync import sync_screencast_timing

                            with st.spinner("Запуск Whisper для синхронизации..."):
                                script_to_use = sync_screencast_timing(
                                    selected_script, matched_avatars, sync_model
                                )
                        except Exception as e:
                            st.warning(f"Синхронизация не удалась: {e}")

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
                        with st.expander("Команда FFmpeg"):
                            st.code(format_ffmpeg_cmd(cmd), language="bash")
                    except (ValueError, FFmpegError) as e:
                        st.error(str(e))

        # Compose video
        with col_compose:
            if st.button("Собрать видео", type="primary", use_container_width=True):
                if not matched_avatars:
                    st.error("Нет доступных аватаров.")
                else:
                    # Apply PiP mode
                    if use_pip:
                        for seg in selected_script.segments:
                            for sc in seg.screencasts:
                                sc.mode = CompositionMode.PIP

                    # Apply sync
                    script_to_use = selected_script
                    if enable_sync:
                        try:
                            from ugckit.sync import sync_screencast_timing

                            with st.spinner("Запуск Whisper для синхронизации..."):
                                script_to_use = sync_screencast_timing(
                                    selected_script, matched_avatars, sync_model
                                )
                        except Exception as e:
                            st.warning(f"Синхронизация не удалась: {e}")

                    output_path = OUTPUT_DIR / f"{script_to_use.script_id}.mp4"
                    try:
                        timeline = build_timeline(
                            script=script_to_use,
                            avatar_clips=matched_avatars,
                            screencasts_dir=SCREENCASTS_DIR,
                            output_path=output_path,
                        )

                        # Generate head videos for PiP
                        head_videos = None
                        if use_pip:
                            try:
                                from ugckit.pip_processor import create_head_video

                                head_videos = []
                                with st.spinner("Генерация видео головы для PiP..."):
                                    for i, avatar in enumerate(matched_avatars):
                                        head_out = OUTPUT_DIR / f"head_{i}.webm"
                                        head_path = create_head_video(
                                            avatar, head_out, cfg.composition.pip
                                        )
                                        head_videos.append(head_path)
                            except Exception as e:
                                st.warning(f"PiP: не удалось создать видео головы: {e}")
                                head_videos = None

                        progress_bar = st.progress(0.0, text="Рендеринг...")
                        result_path = compose_video_with_progress(
                            timeline,
                            cfg,
                            progress_callback=lambda p: progress_bar.progress(
                                p, text=f"Рендеринг... {p:.0%}"
                            ),
                            head_videos=head_videos,
                        )
                        st.success(f"Готово! {result_path.name}")

                        with open(result_path, "rb") as vf:
                            st.download_button(
                                "Скачать видео",
                                data=vf,
                                file_name=result_path.name,
                                mime="video/mp4",
                                use_container_width=True,
                            )
                    except (ValueError, FFmpegError) as e:
                        st.error(str(e))

        # Batch compose
        st.divider()
        if st.button("Собрать все скрипты"):
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

                output_path = OUTPUT_DIR / f"{script.script_id}.mp4"
                try:
                    timeline = build_timeline(
                        script=script,
                        avatar_clips=s_avatars,
                        screencasts_dir=SCREENCASTS_DIR,
                        output_path=output_path,
                    )
                    progress_bar = st.progress(0.0, text=f"Рендеринг {script.script_id}...")
                    result_path = compose_video_with_progress(
                        timeline,
                        cfg,
                        progress_callback=lambda p, sid=script.script_id: progress_bar.progress(
                            p, text=f"Рендеринг {sid}... {p:.0%}"
                        ),
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
