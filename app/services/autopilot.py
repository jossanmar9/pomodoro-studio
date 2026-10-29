"""Mode automàtic: d'una tria (tema, entorn, duració) a un vídeo publicat.

Cada execució passa per estos passos, un darrere de l'altre:
fons → efectes i música → renderitzat → publicació a YouTube.
Només s'executa una execució alhora; la resta esperen en cua.
"""
from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import random
import subprocess
import threading
from time import sleep

from app.config import settings
from app.database import SessionLocal
from app.models import AUTO_STEPS, AutoRun, Project, PublicationMetadata, RenderConfig, YouTubePublication
from app.services.ambience_assets import AssetProvenance, import_background
from app.services.ambience_prompt import build_prompt
from app.services.autopilot_plan import (
    ENVIRONMENTS, build_credits, build_music_mix_command, build_playlist, build_texts,
    choose_ambience, find_backgrounds, load_catalog, prompt_spec, slugify,
)
from app.services.encoding import EncodingOptions
from app.services.image_providers import available_providers, generate_image
from app.services.jobs import render_queue
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


def forge_ready() -> bool:
    return "a1111" in available_providers()


def _update(run_id: int, **fields) -> None:
    with SessionLocal() as db:
        run = db.get(AutoRun, run_id)
        if not run:
            return
        for key, value in fields.items():
            setattr(run, key, value)
        db.commit()


# --- Pas 1: fons -----------------------------------------------------------

def _generate_background(theme: str, environment: str) -> Path:
    prompt = build_prompt(prompt_spec(theme, environment))
    try:
        result = generate_image("a1111", prompt, hires_scale=settings.auto_hires_scale)
    except Exception:
        if settings.auto_hires_scale <= 1:
            raise
        logger.warning("Forge ha fallat amb hires fix; es reintenta sense escalar", exc_info=True)
        result = generate_image("a1111", prompt)
    name = f"{slugify(theme)}-{environment}-{datetime.now():%Y%m%d-%H%M%S}"
    provenance = AssetProvenance(
        prompt=prompt.positive, negative_prompt=prompt.negative, provider=result.provider, model=result.model,
        license="Generat localment amb A1111/Forge per al mode automàtic",
        source_notes=result.notes,
        generation={"hires_scale": settings.auto_hires_scale},
    )
    image, _ = import_background(result.path, settings.assets_dir / "backgrounds", name, provenance)
    result.path.unlink(missing_ok=True)
    return image


def choose_background(theme: str, environment: str, rng: random.Random) -> tuple[Path, str]:
    """Genera un fons nou amb Forge; si no està obert, reutilitza un de l'ambientació."""
    if forge_ready():
        try:
            return _generate_background(theme, environment), "Fons nou generat amb Forge"
        except Exception as exc:  # Forge pot fallar per memòria GPU, model, etc.
            logger.exception("No s'ha pogut generar el fons amb Forge")
            fallback_reason = f"Forge ha fallat ({exc}); "
    else:
        fallback_reason = "Forge no està obert; "
    existing = find_backgrounds(settings.assets_dir / "backgrounds", theme)
    if not existing:
        raise AutopilotError(
            f"{fallback_reason}no hi ha cap fons de «{theme}» en assets/backgrounds. "
            f"Obri Forge o afig una imatge el nom de la qual continga «{slugify(theme)}»."
        )
    return rng.choice(existing), fallback_reason + "s'ha reutilitzat un fons existent"


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
        project = Project(theme=theme, focus_minutes=focus, break_minutes=pause, duration_minutes=duration, resolution=RESOLUTION)
        db.add(project)
        db.commit()
        project_id = project.id
        run.project_id = project_id
        db.commit()

    notes: list[str] = []
    folder: Path | None = None
    try:
        _update(run_id, step="BACKGROUND", message="Creant el fons…")
        background, note = choose_background(theme, environment, rng)
        notes.append(note)

        _update(run_id, step="AUDIO", message="Triant efectes i preparant la música…")
        timeline = build_timeline(focus, pause, duration)
        env = ENVIRONMENTS[environment]
        ambience = choose_ambience(settings.assets_dir / "ambience", environment, rng)
        catalog = load_catalog(settings.audio_catalog)
        playlist: list[Path] = []
        if env.music:
            try:
                playlist = build_playlist(settings.assets_dir / "music", timeline.total_seconds, rng, catalog)
            except ValueError:
                if not ambience:
                    raise AutopilotError("No hi ha música en assets/music ni sons per a este entorn") from None
                notes.append("Sense música: assets/music està buida")
        if not ambience and not playlist:
            raise AutopilotError("No hi ha cap so disponible per a este vídeo")

        folder = create_output_dir(project_id, theme)
        music_track = None
        if playlist:
            music_track = AudioTrack(prepare_music(playlist, folder), 1.0)
        ambience_tracks = [AudioTrack(layer.path, 1.0, layer.loudness) for layer in ambience]

        public_theme = publication_theme(theme)
        chapters = build_chapters(timeline, language="en")
        ambience_paths = [layer.path for layer in ambience]
        texts = build_texts(
            public_theme=public_theme, environment=environment, duration=duration, focus=focus, pause=pause,
            chapters=chapters,
            credits=build_credits(playlist, ambience_paths, catalog),
            compact_credits=build_credits(playlist, ambience_paths, catalog, compact=True),
        )
        draft = PublicationDraft(texts.title, texts.description, chapters, texts.tags, "en")
        write_metadata(folder, theme=theme, focus=focus, pause=pause, duration=duration, resolution=RESOLUTION, timeline=timeline, draft=draft)
        generate_thumbnail(background, folder / "thumbnail.jpg", texts.thumbnail_text, fitting_fontsize(texts.thumbnail_text))

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
            ambience=ambience_tracks, music=music_track, encoding=EncodingOptions("auto", "balanced"), timer_language="en",
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
        record = db.query(YouTubePublication).filter(YouTubePublication.project_id == project_id).first() or YouTubePublication(project_id=project_id)
        db.add(record)
        record.privacy, record.category_id, record.status, record.error = privacy, "27", "UPLOADING", None
        db.commit()
        spec = YouTubeUploadSpec(
            root / "video.mp4", meta.title, meta.description,
            [t.strip() for t in meta.tags.split(",") if t.strip()], "27", meta.language, privacy,
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
    _update(run_id, step="DONE", video_id=video_id, message="; ".join(notes) or None)


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


def run_summary(run: AutoRun) -> dict:
    data = {
        "id": run.id, "theme": run.theme, "environment": run.environment,
        "environment_label": ENVIRONMENTS[run.environment].label if run.environment in ENVIRONMENTS else run.environment,
        "duration_minutes": run.duration_minutes, "pomodoro": f"{run.focus_minutes}/{run.break_minutes}",
        "privacy": run.privacy, "step": run.step, "step_label": AUTO_STEPS.get(run.step, run.step),
        "message": run.message, "error": run.error, "project_id": run.project_id, "video_id": run.video_id,
        "video_url": f"https://youtu.be/{run.video_id}" if run.video_id else None,
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
