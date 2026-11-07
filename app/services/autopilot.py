"""Mode automàtic: d'una tria (tema, entorn, duració) a un vídeo publicat.

Cada execució passa per estos passos, un darrere de l'altre:
fons → efectes i música → renderitzat → publicació a YouTube.
Només s'executa una execució alhora; la resta esperen en cua.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
import random
import subprocess
import threading
from time import sleep

from app.config import settings
from app.database import SessionLocal
from app.models import AUTO_ACTIVE_STEPS, AUTO_STEPS, AutoRun, Project, PublicationMetadata, RenderConfig, YouTubePublication
from app.services.autopilot_plan import (
    DIM_AFTER_SECONDS, ENVIRONMENTS, FORMATS, MUSIC_LEVELS, MUSIC_STYLES, music_style, NOISE_LOUDNESS, PRIMARY_AMBIENCE_LOUDNESS, NOISE_COLORS, YOUTUBE_CATEGORIES, plain_chapters, build_credits, build_music_mix_command, build_playlist, build_texts,
    CHANNEL_URL, LOFI_FORMATS, VISUAL_STYLES, anime_title, background_style, playlists_for, build_preview_command, choose_ambience, duration_label, find_backgrounds, load_catalog, music_tracks, slugify,
)
from app.services.encoding import EncodingOptions
from app.services.fonts import fonts_for_theme
from app.services.jobs import render_queue
from app.services.power import power
from app.services.metadata import PublicationDraft, create_output_dir, write_metadata
from app.services.breathing import DARKEN as BREATH_DARKEN, OPACITY as BREATH_OPACITY, PATTERNS as BREATH_PATTERNS, ensure_breath_clip, ensure_breath_intro
from app.services.overlays import ensure_overlay, overlay_mode, overlay_opacity, overlay_style
from app.services.encoding import run_encode
from app.services.text_variants import first_comment, short_phrase
from app.services.shorts import FPS as SHORT_FPS, HEIGHT as SHORT_HEIGHT, SECONDS as SHORT_SECONDS, WIDTH as SHORT_WIDTH, build_short_command, channel_short_texts, short_start, short_texts, variant_title
from app.services.renderer import AudioTrack, RenderSpec
from app.services.noise_screen import NOISE_SCREENS, make_noise_background
from app.services.backdrops import short_backdrop, timer_backdrop
from app.services.channel_intro import TIMER_FROM as CHANNEL_INTRO_TIMER_FROM, ensure_channel_intro
from app.services.quality import check_video
from app.services.schedule import label as schedule_label, publish_at as schedule_publish_at
from app.services.meta import facebook_configured, instagram_configured, publish_facebook_reel, publish_instagram_reel, reel_caption
from app.services.thumbnail import fitting_fontsize, generate_thumbnail, make_thumbnail, make_title_card
from app.services.timer import build_chapters, build_timeline, with_lead_in
from app.services.youtube import YouTubeUploadSpec, add_to_playlists, can_comment, can_manage_playlists, post_comment, upload_video
from app.services.translations import localized_short, localized_texts
from app.themes import publication_theme

COUNTDOWN_SECONDS = 10  # compte enrere abans de la primera concentració dels pomodoros
logger = logging.getLogger(__name__)
RESOLUTION = "1920x1080"
FINAL_RENDER_STATUSES = {"COMPLETAT", "ERROR", "CANCEL·LAT"}


class AutopilotError(RuntimeError):
    """Error explicat en valencià perquè es puga mostrar tal qual en la pàgina."""


def youtube_connected() -> bool:
    return settings.youtube_token_file.is_file()


class RunCancelled(Exception):
    """L'usuari ha cancel·lat el vídeo."""


_cancelled: set[int] = set()
_cancel_lock = threading.Lock()


def is_cancelled(run_id: int) -> bool:
    with _cancel_lock:
        return run_id in _cancelled


def _check_cancel(run_id: int) -> None:
    if is_cancelled(run_id):
        raise RunCancelled()


def _update(run_id: int, **fields) -> None:
    # En passar a un pas nou es comprova si s'ha cancel·lat (un vídeo ja publicat no es pot desfer).
    if fields.get("step") in AUTO_ACTIVE_STEPS:
        _check_cancel(run_id)
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run:
            return
        for key, value in fields.items():
            setattr(run, key, value)
        db.commit()


# --- Pas 1: fons -----------------------------------------------------------

def _backdrop(make, background: Path, output: Path) -> Path:
    """Fons amb l'ombra per al text; si no es pot fer, el fons original."""
    try:
        return make(background, output)
    except Exception:
        logger.warning("No s'ha pogut preparar l'ombra del text; s'usa el fons original", exc_info=True)
        return background


def noise_background(noise: str, screen: str, *, with_name: bool = True) -> Path:
    """Fons generat per al soroll de color (es guarda i es reutilitza)."""
    width, height = (int(n) for n in RESOLUTION.split("x"))
    name = f"soroll-{noise}-{screen}{'-nom' if with_name else ''}-v1-{width}x{height}.png"
    path = settings.overlays_dir / name
    if not path.is_file():
        text = f"{NOISE_COLORS[noise][1]} Noise" if with_name and screen == "color" else None
        make_noise_background(noise, screen, path, width=width, height=height, text=text)
    return path


def choose_background(theme: str, environment: str, rng: random.Random, fmt: str = "pomodoro", *, chosen: str | None = None, recent: set[str] | None = None,
                      visual_style: str | None = None) -> tuple[Path, str]:
    """Usa el fons triat a mà o, si no se n'ha triat cap, un de la biblioteca a l'atzar (de l'estil demanat, si n'hi ha)."""
    library = find_backgrounds(settings.assets_dir / "backgrounds", theme)
    style_note = None
    if visual_style in VISUAL_STYLES and not chosen:
        same = [path for path in library if background_style(path) == visual_style]
        if same:
            library = same
        elif library:
            style_note = f"No hi ha fons {VISUAL_STYLES[visual_style].lower()} de «{theme}»; se n'ha usat un altre"
    if chosen:
        for path in library:
            if path.name == chosen:
                return path, "Fons triat a mà"
    if not library:
        raise AutopilotError(
            f"No hi ha cap fons de «{theme}» en la biblioteca. "
            f"Afig-ne en «Biblioteca de fons» o copia una imatge en assets/backgrounds amb un nom que comence per «{slugify(theme)}»."
        )
    fresh = [path for path in library if path.name not in (recent or set())] or library
    note = style_note or ("Fons de la biblioteca" if not chosen else "El fons triat ja no existeix; se n'ha usat un altre de la biblioteca")
    return rng.choice(best_matches(fresh, environment, fmt)), note


def _background_tags(path: Path) -> tuple[str | None, str | None]:
    """Format i entorn per als quals es va fer el fons (de la seua fitxa .json)."""
    try:
        data = json.loads(path.with_suffix(path.suffix + ".json").read_text(encoding="utf-8"))
        generation = data.get("generation") or {}
        return generation.get("format"), generation.get("environment")
    except (OSError, ValueError, AttributeError):
        return None, None


def best_matches(paths: list[Path], environment: str, fmt: str) -> list[Path]:
    """Prioritza els fons fets per al mateix format i entorn; si no n'hi ha, qualsevol del tema."""
    tags = {path: _background_tags(path) for path in paths}
    for wanted in (lambda f, e: f == fmt and e == environment, lambda f, e: f == fmt, lambda f, e: e == environment):
        chosen = [path for path, (f, e) in tags.items() if wanted(f, e)]
        if chosen:
            return chosen
    return paths


def recent_backgrounds(theme: str, limit: int = 5) -> set[str]:
    """Fons usats en els últims vídeos del mateix tema, per no repetir-los."""
    with SessionLocal() as db:
        rows = db.query(AutoRun.background).filter(AutoRun.theme == theme, AutoRun.background.isnot(None)).order_by(AutoRun.id.desc()).limit(limit).all()
    return {row[0] for row in rows}


# --- Pas 2: àudio ------------------------------------------------------------

def prepare_music(playlist: list[Path], folder: Path, level: int = 0) -> Path:
    output = folder / "music-mix.m4a"
    result = subprocess.run(build_music_mix_command(playlist, output, level=level), capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output.is_file():
        raise AutopilotError("No s'ha pogut preparar la llista musical: " + (result.stderr or "")[-500:])
    return output


# --- Execució ----------------------------------------------------------------

def _wait_for_render(project_id: int) -> None:
    while True:
        job = render_queue.jobs.get(project_id)
        if job and is_cancelled_project(project_id):
            render_queue.cancel(project_id)
        if job and job.status in FINAL_RENDER_STATUSES:
            if job.status == "CANCEL·LAT":
                raise RunCancelled()
            if job.status != "COMPLETAT":
                raise AutopilotError("El renderitzat ha fallat: " + (job.error or job.status))
            return
        sleep(2)


def execute(run_id: int, *, rng: random.Random | None = None) -> None:
    rng = rng or random.Random()
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run:
            return
        theme, environment, duration = run.theme, run.environment, run.duration_minutes
        focus, pause, privacy, publish = run.focus_minutes, run.break_minutes, run.privacy, bool(run.publish)
        with_music, with_chime = bool(run.music), bool(run.chime)
        level = run.ambience_level if run.ambience_level is not None else 0
        music_level = run.music_level if run.music_level in MUSIC_LEVELS else 0
        preferred = [name for name in (run.ambience_files or "").split(",") if name]
        fmt = run.format if run.format in FORMATS else "pomodoro"
        run_noise = run.noise
        with_motion = bool(run.motion)
        chosen_background = run.background
        wanted_style = run.visual_style if run.visual_style in VISUAL_STYLES else None
        breath = run.breath
        run_music_style = run.music_style
        style = run.music_style if run.music_style in MUSIC_STYLES else music_style(fmt, run.environment, run.theme)
        noise_color = NOISE_COLORS[run.noise][0] if fmt == "soroll" and run.noise in NOISE_COLORS else None
        dim_after = DIM_AFTER_SECONDS if run.dim and fmt in {"dormir", "soroll"} else None
        noise_screen = run.noise_screen if run.noise_screen in NOISE_SCREENS else "color"
        noise_pulse = bool(run.noise_pulse) and noise_screen == "color"
        with_intro = bool(run.intro) and fmt not in {"respiracio", "short"}
        if fmt != "pomodoro":
            # Sense comptador: una sola «sessió» de tota la duració.
            focus, pause, with_chime = duration, 0, False
        project = Project(theme=theme, focus_minutes=focus, break_minutes=pause, duration_minutes=duration, resolution=RESOLUTION)
        db.add(project)
        db.commit()
        project_id = project.id
        run.project_id = project_id
        db.commit()

    notes: list[str] = []
    folder: Path | None = None
    try:
        _update(run_id, step="BACKGROUND", message="Preparant el fons…")
        if fmt == "soroll":
            if noise_color is None:
                raise AutopilotError("Falta el color del soroll")
            background = noise_background(run_noise, noise_screen)
            notes.append(NOISE_SCREENS[noise_screen])
        else:
            background, note = choose_background(theme, environment, rng, fmt, chosen=chosen_background, recent=recent_backgrounds(theme) - {chosen_background},
                                                 visual_style=wanted_style)
            _update(run_id, background=background.name, visual_style=background_style(background))
            if background_style(background) == "anime" and run_music_style not in MUSIC_STYLES and fmt in LOFI_FORMATS:
                style = "lofi"  # els vídeos anime per a estudiar i llegir, amb lo-fi
            notes.append(note)
        if fmt == "short":
            _execute_channel_short(run_id, project_id, theme, environment, rng, background, level=level, music_level=music_level, preferred=preferred,
                                   with_music=with_music, style=style, with_motion=with_motion, privacy=privacy, publish=publish, notes=notes)
            return

        _update(run_id, step="AUDIO", message="Triant efectes i preparant la música…")
        timeline = build_timeline(focus, pause, duration)
        if fmt == "pomodoro":
            # 10 segons de compte enrere quan apareix el comptador (després de la intro, si n'hi ha).
            timeline = with_lead_in(timeline, COUNTDOWN_SECONDS + (round(CHANNEL_INTRO_TIMER_FROM) if with_intro else 0))
        catalog = load_catalog(settings.audio_catalog)
        playlist: list[Path] = []
        if fmt == "soroll":
            if noise_color is None:
                raise AutopilotError("Falta el color del soroll")
            env, ambience = None, []
        else:
            env = ENVIRONMENTS[environment]
            ambience = choose_ambience(settings.assets_dir / "ambience", environment, rng, level=level, preferred=preferred)
            if env.noise:
                noise_color = env.noise
        if fmt == "ambient" and env is not None and not env.layers and not env.noise:
            raise AutopilotError("El so ambiental necessita un entorn amb sons (no «Només música»)")
        if env is not None and env.music and fmt != "ambient" and (with_music or not env.layers):
            try:
                try:
                    playlist = build_playlist(settings.assets_dir / "music", timeline.total_seconds, rng, catalog, style)
                except ValueError:
                    if style == "calma":
                        raise
                    notes.append(f"Encara no tens música {MUSIC_STYLES[style][0].lower()} (executa scripts/descarregar-sons.py); s'ha usat música tranquil·la")
                    style = "calma"
                    playlist = build_playlist(settings.assets_dir / "music", timeline.total_seconds, rng, catalog, style)
            except ValueError:
                if not ambience:
                    raise AutopilotError("No hi ha música en assets/music ni sons per a este entorn") from None
                notes.append("Sense música: assets/music està buida")
        if not ambience and not playlist and not noise_color:
            raise AutopilotError("No hi ha cap so disponible per a este vídeo")

        folder = create_output_dir(project_id, theme)
        music_track = None
        if playlist:
            music_track = AudioTrack(prepare_music(playlist, folder, music_level), 1.0)
        ambience_tracks = [AudioTrack(layer.path, 1.0, layer.loudness) for layer in ambience]

        public_theme = publication_theme(theme)
        chapters = build_chapters(timeline, language="en") if fmt == "pomodoro" else plain_chapters(timeline.total_seconds, dim_after)
        ambience_paths = [layer.path for layer in ambience]
        texts = build_texts(
            public_theme=public_theme, environment=environment, duration=duration, focus=focus, pause=pause,
            chapters=chapters,
            credits=build_credits(playlist, ambience_paths, catalog),
            compact_credits=build_credits(playlist, ambience_paths, catalog, compact=True),
            music=bool(playlist), chime=with_chime, style=style, breath=breath,
            fmt=fmt, noise=run_noise, dim=dim_after is not None, screen=noise_screen, seed=project_id,
            anime=fmt != "soroll" and background_style(background) == "anime",
        )
        draft = PublicationDraft(texts.title, texts.description, chapters, texts.tags, "en")
        write_metadata(folder, theme=theme, focus=focus, pause=pause, duration=duration, resolution=RESOLUTION, timeline=timeline, draft=draft)
        fonts = fonts_for_theme(theme, anime=fmt != "soroll" and background_style(background) == "anime")
        thumbnail_background = noise_background(run_noise, "color", with_name=False) if fmt == "soroll" else background
        thumb_title, thumb_subtitle = thumbnail_lines(fmt, public_theme, environment, duration, focus, pause, run_noise, breath)
        make_thumbnail(thumbnail_background, folder / "thumbnail.jpg", thumb_title, thumb_subtitle, title_font=fonts.label, text_font=fonts.digits)
        title_card = None
        if fmt not in {"soroll", "respiracio"}:  # estos ja tenen el seu text o la seua preparació a l'inici
            try:
                width, height = (int(v) for v in RESOLUTION.split("x"))
                title_card = make_title_card(folder / "titol-inicial.png", thumb_title, thumb_subtitle, width=width, height=height,
                                             title_font=fonts.label, text_font=fonts.digits)
            except Exception:  # sense títol inicial, el vídeo es fa igual
                logger.exception("No s'ha pogut fer el títol inicial")

        with SessionLocal() as db:
            saved = db.get(Project, project_id)
            saved.output_path = str(folder)
            saved.status = "QUEUED"
            db.add(RenderConfig(project_id=project_id, engine="auto", quality="balanced"))
            db.add(PublicationMetadata(project_id=project_id, title=draft.title, description=draft.description, chapters=draft.chapters, tags=draft.tags, language=draft.language))
            db.commit()

        overlay, opacity, darken, overlay_intro = None, 0.0, 0.0, None
        layer_style = overlay_style(theme, environment, background) if with_motion and fmt not in {"respiracio", "soroll"} else None
        if fmt == "respiracio":
            overlay = ensure_breath_clip(breath, cache_dir=settings.overlays_dir, width=int(RESOLUTION.split("x")[0]),
                                         height=int(RESOLUTION.split("x")[1]), fps=RenderSpec.fps, font=fonts.label)
            overlay_intro = ensure_breath_intro(cache_dir=settings.overlays_dir, width=int(RESOLUTION.split("x")[0]),
                                                height=int(RESOLUTION.split("x")[1]), fps=RenderSpec.fps, font=fonts.label)
            opacity, darken = BREATH_OPACITY, BREATH_DARKEN
        elif layer_style:
            try:
                overlay = ensure_overlay(layer_style, cache_dir=settings.overlays_dir, custom_dir=settings.assets_dir / "overlays",
                                         width=int(RESOLUTION.split("x")[0]), height=int(RESOLUTION.split("x")[1]), fps=RenderSpec.fps)
                opacity = overlay_opacity(layer_style)
            except Exception as exc:  # sense capa, el vídeo es fa igual
                logger.exception("No s'ha pogut preparar la capa de moviment")
                notes.append(f"Sense efectes de moviment: {exc}"[:200])

        _update(run_id, step="RENDERING", message="Renderitzant el vídeo…")
        render_background = _backdrop(timer_backdrop, background, folder / "fons-video.png") if fmt == "pomodoro" else background
        channel_intro = None
        if with_intro:
            try:
                font = settings.assets_dir / "fonts" / "cinzel" / "Cinzel-SemiBold.ttf"
                channel_intro = ensure_channel_intro(cache_dir=settings.overlays_dir, width=int(RESOLUTION.split("x")[0]),
                                                     height=int(RESOLUTION.split("x")[1]), fps=RenderSpec.fps, font=font if font.is_file() else None)
            except Exception as exc:  # sense intro, el vídeo es fa igual
                logger.exception("No s'ha pogut fer la intro del canal")
                notes.append(f"Sense intro: {exc}"[:200])
        render_queue.enqueue(project_id, RenderSpec(
            render_background, folder / "video.mp4", RESOLUTION, timeline,
            ambience=ambience_tracks, music=music_track, encoding=EncodingOptions("auto", "balanced"), timer_language="en", fonts=fonts, chime=with_chime,
            show_timer=fmt == "pomodoro", dim_after=dim_after, noise=noise_color,
            noise_loudness=(NOISE_LOUDNESS if fmt == "soroll" else PRIMARY_AMBIENCE_LOUDNESS) + level,
            overlay=overlay, overlay_opacity=opacity, darken=darken, overlay_intro=overlay_intro,
            overlay_mode=overlay_mode(layer_style) if layer_style and overlay is not None and fmt != "respiracio" else "screen",
            pulse=fmt == "soroll" and noise_pulse,
            channel_intro=channel_intro, title_card=title_card,
            intro_text=f"{NOISE_COLORS[run_noise][1]} Noise" if fmt == "soroll" and noise_screen == "negre" else None,
        ))
        _wait_for_render(project_id)
        if music_track:
            music_track.path.unlink(missing_ok=True)

        _update(run_id, message="Comprovant el vídeo (duració, so i imatge)…")
        try:
            problems = check_video(folder / "video.mp4", timeline.total_seconds, dark_after=dim_after,
                                   black_screen=fmt == "soroll" and noise_screen == "negre")
        except Exception as exc:  # si la comprovació mateixa falla, no es bloqueja el vídeo
            logger.exception("No s'ha pogut comprovar el vídeo")
            notes.append(f"No s'ha pogut comprovar el vídeo: {exc}"[:200])
            problems = []
        if problems and publish:
            _update(run_id, step="FAILED", message="; ".join(notes) or None,
                    error="Comprovació: " + "; ".join(problems) + ". Mira el vídeo i, si està bé, prem «Publicar igualment».")
            return
        if problems:
            notes.append("Comprovació: " + "; ".join(problems))
        elif not notes or not notes[-1].startswith("No s'ha pogut comprovar"):
            notes.append("Vídeo comprovat")

        if not publish:
            _update(run_id, step="DONE_LOCAL", message="; ".join(notes + ["Vídeo fet; no s'ha demanat publicar-lo"]))
            return
        if not youtube_connected():
            _update(run_id, step="DONE_LOCAL", message="; ".join(notes + ["Vídeo fet, però YouTube no està connectat. Connecta'l i prem «Publicar ara»"]))
            return
        publish_project(run_id, project_id, privacy, notes)
    except RunCancelled:
        _finish_cancelled(run_id, project_id, notes)
    except Exception as exc:
        logger.exception("Execució automàtica %s fallida", run_id)
        message = str(exc) if isinstance(exc, (AutopilotError, ValueError)) else f"Error inesperat: {exc}"
        _update(run_id, step="FAILED", error=message[:2000], message="; ".join(notes) or None)
        with SessionLocal() as db:
            project = db.get(Project, project_id)
            if project and project.status not in {"COMPLETED"}:
                project.status = "FAILED"
                db.commit()


def _finish_cancelled(run_id: int, project_id: int | None, notes: list[str] | None = None) -> None:
    with _cancel_lock:
        _cancelled.discard(run_id)
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if run:
            run.step, run.error = "CANCELLED", None
            run.message = "; ".join([*(notes or []), "Cancel·lat per tu"])
        project = db.get(Project, project_id) if project_id else None
        if project and project.status != "COMPLETED":
            project.status = "CANCELLED"
        db.commit()


def is_cancelled_project(project_id: int) -> bool:
    with SessionLocal() as db:
        run = db.query(AutoRun).filter(AutoRun.project_id == project_id).first()
    return bool(run and is_cancelled(run.id))


def thumbnail_lines(fmt: str, public_theme: str, environment: str, duration: int, focus: int, pause: int,
                    noise: str | None = None, breath: str | None = None) -> tuple[str, str]:
    """Nom gran i línia petita de la miniatura."""
    label = duration_label(duration)
    sound = ENVIRONMENTS[environment].public_label if environment in ENVIRONMENTS else ""
    if fmt == "soroll" and noise in NOISE_COLORS:
        return f"{NOISE_COLORS[noise][1]} Noise", f"{label} · Sleep & Focus"
    if fmt == "respiracio" and breath in BREATH_PATTERNS:
        return BREATH_PATTERNS[breath].public, f"{duration} Min · {sound}" if sound else f"{duration} Min"
    purpose = {"pomodoro": f"Pomodoro {focus}/{pause}" if (focus, pause) in {(25, 5), (50, 10)} else f"Deep Work {focus}/{pause}",
               "dormir": "Sleep", "llegir": "Reading", "rol": "Tabletop RPG"}.get(fmt)
    return public_theme, " · ".join(part for part in (label, sound, purpose) if part)


def _localizations(run: AutoRun, description: str) -> dict[str, dict[str, str]]:
    """Títol i descripció en castellà, portugués, alemany i francés (si falla, el vídeo es puja igual)."""
    try:
        env = ENVIRONMENTS.get(run.environment)
        texts = localized_texts(
            fmt=run.format or "pomodoro", public_theme=publication_theme(run.theme), sound=env.public_label if env else "",
            duration_minutes=run.duration_minutes, english_description=description, focus=run.focus_minutes, pause=run.break_minutes,
            music=bool(run.music), noise=NOISE_COLORS[run.noise][1] if run.noise in NOISE_COLORS else None,
            breath=BREATH_PATTERNS[run.breath].public if run.breath in BREATH_PATTERNS else None, dim=bool(run.dim),
        )
        if run.visual_style == "anime" and run.format != "soroll":
            for value in texts.values():
                value["title"] = anime_title(value["title"])
        return texts
    except Exception:  # les traduccions són un extra
        logger.exception("No s'han pogut preparar les traduccions")
        return {}


def _add_to_playlists(run_id: int, video_id: str) -> str | None:
    """Afig el vídeo a les llistes del canal. Torna una nota per a l'usuari."""
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        wanted = playlists_for(run.format or "pomodoro", run.theme, run.environment, run.visual_style == "anime") if run else []
    if not wanted:
        return None
    if not can_manage_playlists():
        return "Per a afegir els vídeos a les llistes, torna a connectar YouTube"
    try:
        added = add_to_playlists(video_id, wanted)
    except Exception as exc:
        logger.exception("No s'ha pogut afegir el vídeo a les llistes")
        return f"Les llistes han fallat: {exc}"[:200]
    return f"Afegit a les llistes: {', '.join(added)}" if added else None


def publish_project(run_id: int, project_id: int, privacy: str, notes: list[str] | None = None) -> None:
    notes = list(notes or [])
    _update(run_id, step="PUBLISHING", message="Pujant el vídeo a YouTube…", error=None)
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        meta = db.query(PublicationMetadata).filter(PublicationMetadata.project_id == project_id).first()
        if not project or not project.output_path or not meta:
            raise AutopilotError("No es troba el vídeo per a publicar")
        root = Path(project.output_path)
        run = db.get(AutoRun, run_id)
        category = YOUTUBE_CATEGORIES.get(run.format if run else "pomodoro", "27")
        record = db.query(YouTubePublication).filter(YouTubePublication.project_id == project_id).first() or YouTubePublication(project_id=project_id)
        db.add(record)
        record.privacy, record.category_id, record.status, record.error = privacy, category, "UPLOADING", None
        db.commit()
        spec = YouTubeUploadSpec(
            root / "video.mp4", meta.title, meta.description,
            [t.strip() for t in meta.tags.split(",") if t.strip()], category, meta.language, privacy,
            (root / "thumbnail.jpg") if (root / "thumbnail.jpg").is_file() else None,
            _localizations(run, meta.description) if run else {},
            schedule_publish_at(run.scheduled_for, datetime.utcnow()) if run and privacy == "public" else None,
        )
    try:
        video_id = upload_video(spec)
    except Exception as exc:
        with SessionLocal() as db:
            record = db.query(YouTubePublication).filter(YouTubePublication.project_id == project_id).first()
            record.status, record.error = "FAILED", str(exc)[:2000]
            db.commit()
        raise AutopilotError(f"El vídeo està fet, però YouTube ha fallat: {exc}") from exc
    with SessionLocal() as db:
        record = db.query(YouTubePublication).filter(YouTubePublication.project_id == project_id).first()
        record.status, record.video_id, record.error = "PUBLISHED", video_id, None
        db.commit()
    playlist_note = _add_to_playlists(run_id, video_id)
    if privacy == "public":
        _want_comment(run_id)
    if playlist_note:
        notes.append(playlist_note)
    if spec.publish_at:
        with SessionLocal() as db:
            when = db.get(AutoRun, run_id).scheduled_for
        notes.append(f"Programat: es farà públic el {schedule_label(when, settings.timezone)}")
    _update(run_id, step="DONE", video_id=video_id, message="; ".join(notes) or None, published_at=datetime.utcnow())
    comment_note = post_first_comment(run_id)  # només si ja és públic; si està programat, es fa el dia que toca
    if comment_note:
        notes.append(comment_note)
    try:
        short_note = publish_short(run_id, root, spec, video_id)
    except Exception as exc:  # el vídeo llarg ja està publicat: el Short és un extra
        logger.exception("No s'ha pogut publicar el Short")
        short_note = f"El Short ha fallat: {exc}"[:300]
    if short_note:
        _update(run_id, message="; ".join([*notes, short_note]))


def _execute_channel_short(run_id: int, project_id: int, theme: str, environment: str, rng: random.Random, background: Path, *,
                           level: int, music_level: int = 0, preferred: list[str], with_music: bool, style: str, with_motion: bool, privacy: str, publish: bool, notes: list[str]) -> None:
    """Short independent de 45 s que porta al canal: sense vídeo llarg."""
    _update(run_id, step="AUDIO", message="Preparant els sons del Short…")
    env = ENVIRONMENTS[environment]
    catalog = load_catalog(settings.audio_catalog)
    ambience = choose_ambience(settings.assets_dir / "ambience", environment, rng, level=level, preferred=preferred)
    track = None
    if env.music and (with_music or not env.layers):
        tracks = music_tracks(settings.assets_dir / "music", style, catalog) or music_tracks(settings.assets_dir / "music", "calma", catalog)
        track = rng.choice(tracks) if tracks else None
    if not ambience and track is None and not env.noise:
        raise AutopilotError("No hi ha cap so disponible per a este Short")
    folder = create_output_dir(project_id, theme)
    audio = folder / "short-audio.mp3"
    result = subprocess.run(build_preview_command(ambience, track, False, audio, seconds=SHORT_SECONDS + 2, noise=env.noise, music_level=music_level,
                                                  noise_loudness=PRIMARY_AMBIENCE_LOUDNESS + level), capture_output=True, text=True, check=False)
    if result.returncode != 0 or not audio.is_file():
        raise AutopilotError(f"No s'ha pogut preparar l'àudio del Short: {(result.stderr or '')[-300:]}")

    _update(run_id, step="RENDERING", message="Fent el Short…")
    fonts = fonts_for_theme(theme, anime=background_style(background) == "anime")
    overlay, opacity = None, 0.0
    layer_style = overlay_style(theme, environment, background) if with_motion else None
    if layer_style:
        try:
            overlay = ensure_overlay(layer_style, cache_dir=settings.overlays_dir, custom_dir=settings.assets_dir / "overlays", width=SHORT_WIDTH, height=SHORT_HEIGHT, fps=SHORT_FPS)
            opacity = overlay_opacity(layer_style)
        except Exception as exc:
            notes.append(f"Sense efectes de moviment: {exc}"[:200])
    public_theme = publication_theme(theme)
    output = folder / "short.mp4"
    command = build_short_command(_backdrop(short_backdrop, background, folder / "fons-short.png"), audio, output, title=public_theme, subtitle=env.public_label, start=0,
                                  label_font=fonts.label, text_font=fonts.digits, overlay=overlay, overlay_opacity=opacity,
                                  footer="More cozy ambience on the channel",
                                  overlay_mode=overlay_mode(layer_style) if layer_style and overlay is not None else "screen")
    result = run_encode(command)
    audio.unlink(missing_ok=True)
    if result.returncode != 0 or not output.is_file():
        raise AutopilotError(f"No s'ha pogut fer el Short: {(result.stderr or '')[-300:]}")
    music_text = MUSIC_STYLES.get(style, MUSIC_STYLES["calma"])[1] if track else None
    title, description, tags = channel_short_texts(public_theme, env.public_label, CHANNEL_URL, music_text)
    if track:
        description += "\n\n" + build_credits([track], [], catalog, compact=True)
    make_thumbnail(background, folder / "thumbnail.jpg", public_theme, f"{env.public_label} Ambience", title_font=fonts.label, text_font=fonts.digits)
    with SessionLocal() as db:
        saved = db.get(Project, project_id)
        saved.output_path, saved.status = str(folder), "COMPLETED"
        db.add(PublicationMetadata(project_id=project_id, title=title, description=description, chapters="", tags=", ".join(tags), language="en"))
        db.commit()
    if not publish:
        _update(run_id, step="DONE_LOCAL", message="; ".join(notes + ["Short fet; no s'ha demanat publicar-lo"]))
        return
    if not youtube_connected():
        _update(run_id, step="DONE_LOCAL", message="; ".join(notes + ["Short fet, però YouTube no està connectat"]))
        return
    _update(run_id, step="PUBLISHING", message="Pujant el Short a YouTube…")
    try:
        short_id = upload_video(YouTubeUploadSpec(output, title, description, tags, YOUTUBE_CATEGORIES["short"], "en", privacy, None))
    except Exception as exc:
        raise AutopilotError(f"El Short està fet, però YouTube ha fallat: {exc}") from exc
    _update(run_id, step="DONE", video_id=short_id, short_video_id=short_id, message="; ".join(notes) or None, published_at=datetime.utcnow())
    reel_notes = share_reels(run_id)
    _update(run_id, message="; ".join(notes + reel_notes) or None)


def _short_subtitle(run: AutoRun) -> str:
    if run.format == "respiracio" and run.breath in BREATH_PATTERNS:
        return f"{BREATH_PATTERNS[run.breath].public} · {run.duration_minutes} min"
    label = duration_label(run.duration_minutes)
    if run.format == "soroll" and run.noise in NOISE_COLORS:
        return f"{label} · Sleep & Focus"
    env = ENVIRONMENTS.get(run.environment)
    return f"{label} · {env.public_label}" if env else label


def publish_short(run_id: int, folder: Path, main: YouTubeUploadSpec, video_id: str) -> str | None:
    """Fa i puja el Short vertical que enllaça amb el vídeo. Torna una nota per a l'usuari, o None."""
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        # Abans, el Short podia quedar-se amb l'ID del vídeo llarg (no s'arribava a pujar): es torna a fer.
        if not run or not run.shorts or (run.short_video_id and run.short_video_id != run.video_id):
            return None
        theme, environment, fmt, breath, background_name = run.theme, run.environment, run.format, run.breath, run.background
        subtitle, with_motion = _short_subtitle(run), bool(run.motion)
        total = run.duration_minutes * 60
        noise = run.noise if run.format == "soroll" and run.noise in NOISE_COLORS else None
        count = run.shorts
    if noise:
        # El Short del soroll sempre va amb el fons de color (en negre no es veuria res).
        background, with_motion = noise_background(noise, "color", with_name=False), False
    else:
        background = settings.assets_dir / "backgrounds" / (background_name or "")
        if not background_name or not background.is_file():
            return "Short no fet: no es troba el fons"
    fonts = fonts_for_theme(theme, anime=not noise and background_style(background) == "anime")
    overlay, opacity, darken, mode = None, 0.0, 0.0, "screen"
    if fmt == "respiracio" and breath in BREATH_PATTERNS:
        overlay = ensure_breath_clip(breath, cache_dir=settings.overlays_dir, width=SHORT_WIDTH, height=SHORT_HEIGHT, fps=SHORT_FPS, font=fonts.label)
        opacity, darken = BREATH_OPACITY, BREATH_DARKEN
    else:
        style = overlay_style(theme, environment, background) if with_motion else None
        if style:
            overlay = ensure_overlay(style, cache_dir=settings.overlays_dir, custom_dir=settings.assets_dir / "overlays", width=SHORT_WIDTH, height=SHORT_HEIGHT, fps=SHORT_FPS)
            opacity, mode = overlay_opacity(style), overlay_mode(style)
    output = folder / "short.mp4"
    title = f"{NOISE_COLORS[noise][1]} Noise" if noise else publication_theme(theme)
    background = _backdrop(short_backdrop, background, folder / "fons-short.png")
    command = build_short_command(background, main.video, output, title=title, subtitle=subtitle,
                                  start=short_start(total), label_font=fonts.label, text_font=fonts.digits,
                                  overlay=overlay, overlay_opacity=opacity, darken=darken, overlay_mode=mode)
    result = run_encode(command)
    if result.returncode != 0 or not output.is_file():
        return f"Short no fet: {(result.stderr or '')[-200:]}"
    title, description, tags = short_texts(main.title, main.description, main.tags, video_id)
    localized = localized_short(main.localizations, video_id) if main.localizations else {}
    short_id = upload_video(YouTubeUploadSpec(output, title, description, tags, main.category_id, main.language, main.privacy, None, localized,
                                              main.publish_at))
    _update(run_id, short_video_id=short_id)
    # Els reels es publiquen quan el vídeo ja és públic: ara mateix si no està programat, o el dia programat.
    notes = [] if main.publish_at else share_reels(run_id)
    if main.publish_at and (instagram_configured() or facebook_configured()):
        notes.append("Els reels es publicaran quan el vídeo siga públic (cal que Pomodoro estiga obert)")
    start_time = datetime.fromisoformat(main.publish_at.rstrip("Z")) if main.publish_at else datetime.utcnow()
    if count >= 3:
        # Shorts 2 i 3: altres moments del vídeo i altres frases, programats per a demà i passat demà.
        made: list[str] = []
        public_name = f"{NOISE_COLORS[noise][1]} Noise" if noise else publication_theme(theme)
        sound = (ENVIRONMENTS[environment].public_label if environment in ENVIRONMENTS else "")
        for part in (2, 3):
            extra = folder / f"short-{part}.mp4"
            try:
                command = build_short_command(background, main.video, extra, title=public_name, subtitle=short_phrase(run_id, part),
                                              start=short_start(total, part=part), label_font=fonts.label, text_font=fonts.digits,
                                              overlay=overlay, overlay_opacity=opacity, darken=darken, overlay_mode=mode)
                result = run_encode(command)
                if result.returncode != 0 or not extra.is_file():
                    raise AutopilotError((result.stderr or "")[-200:])
                when = (start_time + timedelta(days=part - 1)).replace(microsecond=0).isoformat() + "Z" if main.privacy == "public" else None
                made.append(upload_video(YouTubeUploadSpec(extra, variant_title(short_phrase(run_id, part), public_name, sound or "Ambience"), description, tags,
                                                           main.category_id, main.language, main.privacy, None, localized, when)))
                _update(run_id, extra_short_ids=",".join(made))
            except Exception as exc:
                logger.exception("No s'ha pogut fer el Short %s", part)
                notes.append(f"Short {part} no fet: {exc}"[:200])
        if made and main.privacy == "public":
            notes.append(f"{len(made)} Shorts més programats per als pròxims dies")
    return "; ".join(notes) or None


def _reel_names(run: AutoRun) -> tuple[str, str]:
    """Nom públic i subtítol del reel (els mateixos que porta el Short)."""
    if run.format == "soroll" and run.noise in NOISE_COLORS:
        return f"{NOISE_COLORS[run.noise][1]} Noise", _short_subtitle(run)
    if run.format == "short":
        env = ENVIRONMENTS.get(run.environment)
        return publication_theme(run.theme), f"{env.public_label} Ambience" if env else "Ambience"
    return publication_theme(run.theme), _short_subtitle(run)


REEL_FILES = ("short.mp4", "short-2.mp4", "short-3.mp4")
MAX_REEL_ATTEMPTS = 3


def _reel_state(run: AutoRun) -> dict:
    """Estat dels reels de cada Short: {"short.mp4": {"ig": id, "fb": id, "ig_errors": n, ...}, "skip_ig": bool, ...}."""
    try:
        state = json.loads(run.reels_json) if run.reels_json else {}
    except ValueError:
        state = {}
    first = state.setdefault("short.mp4", {})
    if run.instagram_media_id:
        first.setdefault("ig", run.instagram_media_id)
    if run.facebook_video_id:
        first.setdefault("fb", run.facebook_video_id)
    return state


def _save_reel_state(run_id: int, state: dict) -> None:
    first = state.get("short.mp4", {})
    _update(run_id, reels_json=json.dumps(state), instagram_media_id=first.get("ig"), facebook_video_id=first.get("fb"))


def _reel_due(run: AutoRun, filename: str) -> datetime | None:
    """Quan es pot publicar el reel: quan el vídeo (o eixe Short) ja és públic a YouTube."""
    base = run.scheduled_for or run.published_at
    return base + timedelta(days=REEL_FILES.index(filename)) if base else None


def _short_folder(run: AutoRun) -> Path | None:
    with SessionLocal() as db:
        project = db.get(Project, run.project_id) if run.project_id else None
        return Path(project.output_path) if project and project.output_path else None


def _short_file(run: AutoRun) -> Path | None:
    folder = _short_folder(run)
    return folder / "short.mp4" if folder else None


def pending_reels(run: AutoRun, now: datetime | None = None) -> dict[str, set[str]]:
    """Shorts d'este vídeo que ja tocaria tindre a Instagram o Facebook i encara no hi són: {fitxer: {"ig", "fb"}}."""
    now = now or datetime.utcnow()
    if run.step != "DONE" or not run.short_video_id or (run.short_video_id == run.video_id and run.format != "short"):
        return {}
    networks = {name for name, ok in (("ig", instagram_configured()), ("fb", facebook_configured())) if ok}
    if not networks:
        return {}
    state = _reel_state(run)
    networks -= {n for n in networks if state.get(f"skip_{n}")}
    folder = _short_folder(run)
    result: dict[str, set[str]] = {}
    for filename in REEL_FILES:
        due = _reel_due(run, filename)
        if not folder or not (folder / filename).is_file() or due is None or due > now:
            continue
        info = state.get(filename, {})
        missing = {n for n in networks if not info.get(n) and info.get(f"{n}_errors", 0) < MAX_REEL_ATTEMPTS}
        if missing:
            result[filename] = missing
    return result


MAX_COMMENT_ATTEMPTS = 3


def _want_comment(run_id: int) -> None:
    """Marca que este vídeo ha de rebre el primer comentari del canal quan siga públic."""
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run or run.format == "short":
            return
        state = _reel_state(run)
    state["comment_wanted"] = True
    _save_reel_state(run_id, state)


def comment_due(run: AutoRun, now: datetime | None = None) -> bool:
    """El vídeo ja és públic i encara no té el comentari del canal (YouTube no deixa comentar vídeos privats)."""
    if run.step != "DONE" or not run.video_id or not can_comment():
        return False
    state = _reel_state(run)
    base = run.scheduled_for or run.published_at
    return bool(state.get("comment_wanted") and not state.get("comment_id") and state.get("comment_errors", 0) < MAX_COMMENT_ATTEMPTS
                and base and base <= (now or datetime.utcnow()))


def post_first_comment(run_id: int) -> str | None:
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run or not comment_due(run):
            return None
        state, video_id, fmt = _reel_state(run), run.video_id, run.format or "pomodoro"
    try:
        state["comment_id"] = post_comment(video_id, first_comment(fmt, run_id))
        note = "Comentari publicat a YouTube (fixa'l des de YouTube Studio si vols)"
    except Exception as exc:  # el vídeo ja està publicat: el comentari és un extra
        logger.exception("No s'ha pogut escriure el comentari")
        state["comment_errors"] = state.get("comment_errors", 0) + 1
        note = f"El comentari de YouTube ha fallat: {exc}"[:300]
    _save_reel_state(run_id, state)
    return note


def runs_with_pending_reels(now: datetime | None = None) -> list[int]:
    """Vídeos amb reels o amb el comentari del canal pendents."""
    with SessionLocal() as db:
        runs = db.query(AutoRun).filter(AutoRun.step == "DONE", AutoRun.video_id.isnot(None)).all()
        return [run.id for run in runs if (run.short_video_id and pending_reels(run, now)) or comment_due(run, now)]


def share_reels(run_id: int, video: Path | None = None, *, every: bool = False) -> list[str]:
    """Publica com a reels els Shorts d'este vídeo que ja toquen (a Instagram i a Facebook, si estan configurats).

    Torna notes per a l'usuari. Si una xarxa falla, la resta continua publicada i es torna a provar més tard
    (com a molt 3 vegades). `video` i `every` es mantenen per compatibilitat.
    """
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run:
            return []
        todo = pending_reels(run)
        state = _reel_state(run)
        public, subtitle = _reel_names(run)
        theme, fmt = run.theme, run.format or "pomodoro"
    folder = _short_folder(run)
    notes: list[str] = []
    labels = {"ig": "Instagram", "fb": "Facebook"}
    for filename, networks in todo.items():
        path = folder / filename
        info = state.setdefault(filename, {})
        part = "" if filename == "short.mp4" else f" ({REEL_FILES.index(filename) + 1}r Short)"
        for network in sorted(networks):
            _update(run_id, message=f"Publicant el reel a {labels[network]}{part}…")
            try:
                # Cada vídeo, cada Short i cada xarxa porten un text diferent.
                seed = run_id * 10 + REEL_FILES.index(filename) * 2 + (1 if network == "fb" else 0) if filename in REEL_FILES else run_id
                if network == "ig":
                    info["ig"] = publish_instagram_reel(path, reel_caption(public, subtitle, theme=theme, fmt=fmt, seed=seed))
                else:
                    info["fb"] = publish_facebook_reel(path, reel_caption(public, subtitle, theme=theme, fmt=fmt, channel_url=CHANNEL_URL, facebook=True, seed=seed))
                notes.append(f"Reel publicat a {labels[network]}{part}")
            except Exception as exc:  # el vídeo i el Short ja estan publicats
                logger.exception("No s'ha pogut publicar el reel a %s", labels[network])
                info[f"{network}_errors"] = info.get(f"{network}_errors", 0) + 1
                notes.append(f"{labels[network]} ha fallat{part}: {exc}"[:300])
            _save_reel_state(run_id, state)
    return notes


def reel_missing(run: AutoRun) -> bool:
    """Hi ha algun Short publicat que ja tocaria tindre a Instagram o Facebook i no hi és."""
    return bool(pending_reels(run))


def _make_missing_reel(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run:
            return
        previous = run.message
    notes = share_reels(run_id)
    comment = post_first_comment(run_id)
    if comment:
        notes.append(comment)
    if notes:
        _update(run_id, message="; ".join(([previous] if previous else []) + notes))


class AutopilotRunner:
    """Executa les tasques automàtiques d'una en una en un fil en segon pla."""

    def __init__(self) -> None:
        self._queue: list[tuple[str, int]] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._current: int | None = None

    def cancel(self, run_id: int) -> bool:
        """Cancel·la un vídeo en cua o en marxa. No es pot cancel·lar mentre es puja a YouTube."""
        with SessionLocal() as db:
            run = db.get(AutoRun, run_id)
            if not run or run.step not in AUTO_ACTIVE_STEPS or run.step == "PUBLISHING":
                return False
            project_id = run.project_id
        with self._lock:
            queued = [item for item in self._queue if item[1] == run_id]
            for item in queued:
                self._queue.remove(item)
            running = self._current == run_id
        if queued or not running:
            # En cua (o d'una execució anterior que ja no està en marxa): es tanca ara mateix.
            _finish_cancelled(run_id, project_id)
            return True
        with _cancel_lock:
            _cancelled.add(run_id)
        if project_id:
            render_queue.cancel(project_id)
        return True

    def submit(self, run_id: int) -> None:
        self._push(("run", run_id))

    def submit_publish(self, run_id: int) -> None:
        self._push(("publish", run_id))

    def submit_short(self, run_id: int) -> None:
        self._push(("short", run_id))

    def submit_reel(self, run_id: int) -> None:
        self._push(("reel", run_id))

    def submit_pending_reels(self) -> None:
        """Posa en cua els reels que falten (també els dels vídeos programats que ja s'han fet públics)."""
        for run_id in runs_with_pending_reels():
            with self._lock:
                if ("reel", run_id) in self._queue or self._current == run_id:
                    continue
            self._push(("reel", run_id), keep_shutdown=True)

    submit_due_reels = submit_pending_reels

    def _push(self, item: tuple[str, int], *, keep_shutdown: bool = False) -> None:
        # Si hi havia una apagada pendent i es demana més faena, ja no toca apagar.
        if not keep_shutdown:
            power.cancel()
        with self._lock:
            self._queue.append(item)
            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._loop, daemon=True)
                self._worker.start()

    def _loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                kind, run_id = self._queue.pop(0)
                self._current = run_id
            try:
                if kind == "run":
                    execute(run_id)
                elif kind == "short":
                    _make_missing_short(run_id)
                elif kind == "reel":
                    _make_missing_reel(run_id)
                else:
                    _publish_existing(run_id)
            except RunCancelled:
                _finish_cancelled(run_id, None)
            except Exception:
                logger.exception("Tasca automàtica %s fallida", run_id)
            finally:
                with self._lock:
                    self._current = None
            try:
                cleanup_published_videos()
            except Exception:
                logger.exception("Ha fallat la neteja de vídeos publicats")
            with self._lock:
                last = not self._queue
            if last:
                maybe_schedule_shutdown(run_id)


def should_shut_down(run: AutoRun | None) -> bool:
    """Només s'apaga si s'ha demanat i el vídeo ha acabat bé."""
    if not run or not run.shutdown:
        return False
    return run.step == "DONE" or (run.step == "DONE_LOCAL" and not run.publish)


def maybe_schedule_shutdown(run_id: int) -> bool:
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not should_shut_down(run):
            return False
        label = f"#{run.id} · {run.theme}"
    power.schedule(f"Vídeo {label} acabat")
    return True


def _publish_existing(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run or not run.project_id:
            return
        project_id, privacy = run.project_id, run.privacy
    try:
        publish_project(run_id, project_id, privacy)
    except Exception as exc:
        _update(run_id, step="FAILED", error=str(exc)[:2000])


def short_missing(run: AutoRun) -> bool:
    """El vídeo està publicat, es va demanar Short i no n'hi ha (o es va quedar amb l'ID del vídeo llarg)."""
    return bool(run.format != "short" and run.step == "DONE" and run.video_id and run.shorts
                and (not run.short_video_id or run.short_video_id == run.video_id))


def _make_missing_short(run_id: int) -> None:
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run or not short_missing(run):
            return
        project = db.get(Project, run.project_id)
        meta = db.query(PublicationMetadata).filter(PublicationMetadata.project_id == run.project_id).first()
        if not project or not project.output_path or not meta:
            _update(run_id, message="Short no fet: no es troba el vídeo")
            return
        root = Path(project.output_path)
        spec = YouTubeUploadSpec(root / "video.mp4", meta.title, meta.description, [t.strip() for t in meta.tags.split(",") if t.strip()],
                                 YOUTUBE_CATEGORIES.get(run.format or "pomodoro", "27"), meta.language, run.privacy, None)
        video_id, previous = run.video_id, run.message
    if not spec.video.is_file():
        _update(run_id, message="Short no fet: el vídeo ja s'ha esborrat de l'ordinador")
        return
    try:
        note = publish_short(run_id, root, spec, video_id)
    except Exception as exc:
        logger.exception("No s'ha pogut fer el Short")
        note = f"El Short ha fallat: {exc}"[:300]
    if note and (note.startswith("Short no fet") or note.startswith("El Short ha fallat")):
        _update(run_id, message=note)
    else:
        _update(run_id, message="; ".join(([previous] if previous else []) + ["Short publicat"] + ([note] if note else [])))


def _video_path(project_id: int | None) -> Path | None:
    if not project_id:
        return None
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        return Path(project.output_path) / "video.mp4" if project and project.output_path else None


def _video_available(run: AutoRun) -> bool:
    path = _video_path(run.project_id)
    return bool(path and path.is_file())


def _thumbnail_url(run: AutoRun) -> str | None:
    path = _video_path(run.project_id)
    return f"/projects/{run.project_id}/files/thumbnail.jpg" if path and (path.parent / "thumbnail.jpg").is_file() else None


def _delete_after_date(run: AutoRun) -> datetime | None:
    """Quan es pot esborrar el vídeo: uns dies després que l'últim Short ja siga públic (i tinga el seu reel)."""
    if not (run.delete_after and run.published_at and run.step == "DONE"):
        return None
    last_public = max(run.published_at, run.scheduled_for or run.published_at) + timedelta(days=len(REEL_FILES) - 1 if run.shorts and run.shorts >= 3 else 0)
    return last_public + timedelta(days=settings.keep_published_days)


def _delete_on(run: AutoRun) -> str | None:
    when = _delete_after_date(run)
    return when.date().isoformat() if when else None


def cleanup_published_videos(now: datetime | None = None) -> int:
    """Esborra els vídeos publicats fa més de KEEP_PUBLISHED_DAYS dies (si s'ha demanat).

    Només s'esborra video.mp4 (i el paquet ZIP); la miniatura i els textos es conserven.
    """
    now = now or datetime.utcnow()
    limit = now - timedelta(days=settings.keep_published_days)
    removed = 0
    with SessionLocal() as db:
        runs = db.query(AutoRun).filter(
            AutoRun.delete_after == 1, AutoRun.step == "DONE", AutoRun.video_id.isnot(None),
            AutoRun.published_at.isnot(None), AutoRun.published_at <= limit,
        ).all()
        for run in runs:
            when = _delete_after_date(run)
            if when is None or when > now or pending_reels(run, now):
                continue  # encara s'ha de fer públic algun Short o falta algun reel
            project = db.get(Project, run.project_id) if run.project_id else None
            if not project or not project.output_path:
                continue
            folder = Path(project.output_path)
            video = folder / "video.mp4"
            if not video.is_file():
                continue
            try:
                video.unlink()
                (folder / "publication-package.zip").unlink(missing_ok=True)
                for name in REEL_FILES:
                    (folder / name).unlink(missing_ok=True)
            except OSError:
                logger.exception("No s'ha pogut esborrar %s", video)
                continue
            removed += 1
            note = f"Vídeo esborrat de l'ordinador el {now:%d/%m/%Y} (ja estava publicat)"
            run.message = f"{run.message}; {note}" if run.message else note
        db.commit()
    if removed:
        logger.info("S'han esborrat %s vídeos publicats", removed)
    return removed


def _environment_label(run: AutoRun) -> str:
    if run.format == "soroll":
        return f"Soroll {NOISE_COLORS[run.noise][2].lower()}" if run.noise in NOISE_COLORS else "Soroll"
    return ENVIRONMENTS[run.environment].label if run.environment in ENVIRONMENTS else run.environment


def _step_label(run: AutoRun) -> str:
    if run.step == "DONE" and run.scheduled_for and run.scheduled_for > datetime.utcnow():
        return f"Programat · {schedule_label(run.scheduled_for, settings.timezone)}"
    return AUTO_STEPS.get(run.step, run.step)


def run_summary(run: AutoRun) -> dict:
    data = {
        "id": run.id, "theme": run.theme, "environment": run.environment,
        "environment_label": _environment_label(run),
        "duration_minutes": run.duration_minutes,
        "pomodoro": f"{run.focus_minutes}/{run.break_minutes}" if (run.format or "pomodoro") == "pomodoro" else FORMATS.get(run.format, run.format),
        "format": run.format or "pomodoro",
        "privacy": run.privacy, "step": run.step, "step_label": _step_label(run),
        "message": run.message, "error": run.error, "project_id": run.project_id, "video_id": run.video_id,
        "video_url": f"https://youtu.be/{run.video_id}" if run.video_id else None,
        "video_available": _video_available(run),
        "short_missing": short_missing(run),
        "reel_missing": reel_missing(run),
        "thumbnail_url": _thumbnail_url(run),
        "published_at": run.published_at.date().isoformat() if run.published_at else None,
        "instagram_media_id": run.instagram_media_id, "facebook_video_id": run.facebook_video_id,
        "delete_on": _delete_on(run),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "progress": None, "eta": None,
    }
    if run.step == "RENDERING" and run.project_id:
        job = render_queue.jobs.get(run.project_id)
        if job:
            data["progress"] = round(job.progress, 1)
            data["eta"] = round(job.eta) if job.eta is not None else None
    return data


autopilot = AutopilotRunner()
