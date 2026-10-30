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
from app.models import AUTO_STEPS, AutoRun, Project, PublicationMetadata, RenderConfig, YouTubePublication
from app.services.autopilot_plan import (
    DIM_AFTER_SECONDS, ENVIRONMENTS, FORMATS, PRIMARY_AMBIENCE_LOUDNESS, NOISE_COLORS, YOUTUBE_CATEGORIES, has_fire, plain_chapters, build_credits, build_music_mix_command, build_playlist, build_texts,
    choose_ambience, find_backgrounds, load_catalog, slugify,
)
from app.services.encoding import EncodingOptions
from app.services.fonts import fonts_for_theme
from app.services.jobs import render_queue
from app.services.power import power
from app.services.metadata import PublicationDraft, create_output_dir, write_metadata
from app.services.renderer import AudioTrack, RenderSpec
from app.services.thumbnail import fitting_fontsize, generate_thumbnail
from app.services.timer import build_chapters, build_timeline
from app.services.youtube import YouTubeUploadSpec, upload_video
from app.themes import publication_theme

logger = logging.getLogger(__name__)
RESOLUTION = "1920x1080"
FINAL_RENDER_STATUSES = {"COMPLETAT", "ERROR", "CANCEL·LAT"}


class AutopilotError(RuntimeError):
    """Error explicat en valencià perquè es puga mostrar tal qual en la pàgina."""


def youtube_connected() -> bool:
    return settings.youtube_token_file.is_file()


def _update(run_id: int, **fields) -> None:
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run:
            return
        for key, value in fields.items():
            setattr(run, key, value)
        db.commit()


# --- Pas 1: fons -----------------------------------------------------------

def choose_background(theme: str, environment: str, rng: random.Random, fmt: str = "pomodoro", *, chosen: str | None = None, recent: set[str] | None = None) -> tuple[Path, str]:
    """Usa el fons triat a mà o, si no se n'ha triat cap, un de la biblioteca a l'atzar."""
    library = find_backgrounds(settings.assets_dir / "backgrounds", theme)
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
    note = "Fons de la biblioteca" if not chosen else "El fons triat ja no existeix; se n'ha usat un altre de la biblioteca"
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

def prepare_music(playlist: list[Path], folder: Path) -> Path:
    output = folder / "music-mix.m4a"
    result = subprocess.run(build_music_mix_command(playlist, output), capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output.is_file():
        raise AutopilotError("No s'ha pogut preparar la llista musical: " + (result.stderr or "")[-500:])
    return output


# --- Execució ----------------------------------------------------------------

def _wait_for_render(project_id: int) -> None:
    while True:
        job = render_queue.jobs.get(project_id)
        if job and job.status in FINAL_RENDER_STATUSES:
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
        preferred = [name for name in (run.ambience_files or "").split(",") if name]
        fmt = run.format if run.format in FORMATS else "pomodoro"
        run_noise = run.noise
        with_motion = bool(run.motion)
        chosen_background = run.background
        noise_color = NOISE_COLORS[run.noise][0] if fmt == "soroll" and run.noise in NOISE_COLORS else None
        dim_after = DIM_AFTER_SECONDS if run.dim and fmt in {"dormir", "soroll"} else None
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
        background, note = choose_background(theme, environment, rng, fmt, chosen=chosen_background, recent=recent_backgrounds(theme) - {chosen_background})
        _update(run_id, background=background.name)
        notes.append(note)

        _update(run_id, step="AUDIO", message="Triant efectes i preparant la música…")
        timeline = build_timeline(focus, pause, duration)
        catalog = load_catalog(settings.audio_catalog)
        playlist: list[Path] = []
        if fmt == "soroll":
            if noise_color is None:
                raise AutopilotError("Falta el color del soroll")
            env, ambience = None, []
        else:
            env = ENVIRONMENTS[environment]
            ambience = choose_ambience(settings.assets_dir / "ambience", environment, rng, level=level, preferred=preferred)
        if env is not None and env.music and (with_music or not env.layers):
            try:
                playlist = build_playlist(settings.assets_dir / "music", timeline.total_seconds, rng, catalog)
            except ValueError:
                if not ambience:
                    raise AutopilotError("No hi ha música en assets/music ni sons per a este entorn") from None
                notes.append("Sense música: assets/music està buida")
        if not ambience and not playlist and not noise_color:
            raise AutopilotError("No hi ha cap so disponible per a este vídeo")

        folder = create_output_dir(project_id, theme)
        music_track = None
        if playlist:
            music_track = AudioTrack(prepare_music(playlist, folder), 1.0)
        ambience_tracks = [AudioTrack(layer.path, 1.0, layer.loudness) for layer in ambience]

        public_theme = publication_theme(theme)
        chapters = build_chapters(timeline, language="en") if fmt == "pomodoro" else plain_chapters(timeline.total_seconds, dim_after)
        ambience_paths = [layer.path for layer in ambience]
        texts = build_texts(
            public_theme=public_theme, environment=environment, duration=duration, focus=focus, pause=pause,
            chapters=chapters,
            credits=build_credits(playlist, ambience_paths, catalog),
            compact_credits=build_credits(playlist, ambience_paths, catalog, compact=True),
            music=bool(playlist), chime=with_chime,
            fmt=fmt, noise=run_noise, dim=dim_after is not None,
        )
        draft = PublicationDraft(texts.title, texts.description, chapters, texts.tags, "en")
        write_metadata(folder, theme=theme, focus=focus, pause=pause, duration=duration, resolution=RESOLUTION, timeline=timeline, draft=draft)
        fonts = fonts_for_theme(theme)
        thumbnail_text = texts.thumbnail_text.replace(" · ", fonts.separator)
        thumbnail_font = fonts.label if fonts.uppercase_labels else fonts.digits
        generate_thumbnail(background, folder / "thumbnail.jpg", thumbnail_text, fitting_fontsize(thumbnail_text), thumbnail_font)

        with SessionLocal() as db:
            saved = db.get(Project, project_id)
            saved.output_path = str(folder)
            saved.status = "QUEUED"
            db.add(RenderConfig(project_id=project_id, engine="auto", quality="balanced"))
            db.add(PublicationMetadata(project_id=project_id, title=draft.title, description=draft.description, chapters=draft.chapters, tags=draft.tags, language=draft.language))
            db.commit()

        _update(run_id, step="RENDERING", message="Renderitzant el vídeo…")
        render_queue.enqueue(project_id, RenderSpec(
            background, folder / "video.mp4", RESOLUTION, timeline,
            ambience=ambience_tracks, music=music_track, encoding=EncodingOptions("auto", "balanced"), timer_language="en", fonts=fonts, chime=with_chime,
            show_timer=fmt == "pomodoro", dim_after=dim_after, noise=noise_color,
            noise_loudness=PRIMARY_AMBIENCE_LOUDNESS + level,
            motion=with_motion, flicker=with_motion and has_fire(ambience),
        ))
        _wait_for_render(project_id)
        if music_track:
            music_track.path.unlink(missing_ok=True)

        if not publish:
            _update(run_id, step="DONE_LOCAL", message="; ".join(notes + ["Vídeo fet; no s'ha demanat publicar-lo"]))
            return
        if not youtube_connected():
            _update(run_id, step="DONE_LOCAL", message="; ".join(notes + ["Vídeo fet, però YouTube no està connectat. Connecta'l i prem «Publicar ara»"]))
            return
        publish_project(run_id, project_id, privacy, notes)
    except Exception as exc:
        logger.exception("Execució automàtica %s fallida", run_id)
        message = str(exc) if isinstance(exc, (AutopilotError, ValueError)) else f"Error inesperat: {exc}"
        _update(run_id, step="FAILED", error=message[:2000], message="; ".join(notes) or None)
        with SessionLocal() as db:
            project = db.get(Project, project_id)
            if project and project.status not in {"COMPLETED"}:
                project.status = "FAILED"
                db.commit()


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
    _update(run_id, step="DONE", video_id=video_id, message="; ".join(notes) or None, published_at=datetime.utcnow())


class AutopilotRunner:
    """Executa les tasques automàtiques d'una en una en un fil en segon pla."""

    def __init__(self) -> None:
        self._queue: list[tuple[str, int]] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def submit(self, run_id: int) -> None:
        self._push(("run", run_id))

    def submit_publish(self, run_id: int) -> None:
        self._push(("publish", run_id))

    def _push(self, item: tuple[str, int]) -> None:
        # Si hi havia una apagada pendent i es demana més faena, ja no toca apagar.
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
            try:
                if kind == "run":
                    execute(run_id)
                else:
                    _publish_existing(run_id)
            except Exception:
                logger.exception("Tasca automàtica %s fallida", run_id)
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


def _video_path(project_id: int | None) -> Path | None:
    if not project_id:
        return None
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        return Path(project.output_path) / "video.mp4" if project and project.output_path else None


def _video_available(run: AutoRun) -> bool:
    path = _video_path(run.project_id)
    return bool(path and path.is_file())


def _delete_on(run: AutoRun) -> str | None:
    if not (run.delete_after and run.published_at and run.step == "DONE"):
        return None
    return (run.published_at + timedelta(days=settings.keep_published_days)).date().isoformat()


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


def run_summary(run: AutoRun) -> dict:
    data = {
        "id": run.id, "theme": run.theme, "environment": run.environment,
        "environment_label": _environment_label(run),
        "duration_minutes": run.duration_minutes,
        "pomodoro": f"{run.focus_minutes}/{run.break_minutes}" if (run.format or "pomodoro") == "pomodoro" else FORMATS.get(run.format, run.format),
        "format": run.format or "pomodoro",
        "privacy": run.privacy, "step": run.step, "step_label": AUTO_STEPS.get(run.step, run.step),
        "message": run.message, "error": run.error, "project_id": run.project_id, "video_id": run.video_id,
        "video_url": f"https://youtu.be/{run.video_id}" if run.video_id else None,
        "video_available": _video_available(run),
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
