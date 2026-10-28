from contextlib import asynccontextmanager
import shutil

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Preset, Project
from app.services.assets import catalog, resolve_asset
from app.services.jobs import render_queue
from app.services.metadata import create_output_dir, write_metadata
from app.services.renderer import AudioTrack, RenderSpec
from app.services.thumbnail import generate_thumbnail
from app.services.timer import build_chapters, build_timeline, format_timestamp
from app.themes import THEMES, publication_theme

RESOLUTIONS = {"1920x1080", "2560x1440"}


def validate_project_config(theme: str, focus_minutes: int, break_minutes: int, duration_minutes: int, resolution: str) -> None:
    if theme not in THEMES:
        raise HTTPException(400, "Ambientació no vàlida")
    if resolution not in RESOLUTIONS:
        raise HTTPException(400, "Resolució no vàlida")
    if not 1 <= focus_minutes <= 180 or not 0 <= break_minutes <= 60 or not 1 <= duration_minutes <= 720:
        raise HTTPException(400, "Configuració Pomodoro fora dels límits admesos")
    build_timeline(focus_minutes, break_minutes, duration_minutes)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/assets/{kind}/{name}")
def asset_file(kind: str, name: str):
    try:
        path = resolve_asset(kind, name)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with SessionLocal() as db:
        projects = db.query(Project).order_by(Project.id.desc()).limit(25).all()
        presets = db.query(Preset).order_by(Preset.name.asc()).all()
    return templates.TemplateResponse(request, "index.html", {"themes": list(THEMES), "projects": projects, "presets": presets})


@app.post("/projects")
def create_project(theme: str = Form(...), focus_minutes: int = Form(25), break_minutes: int = Form(5), duration_minutes: int = Form(120), resolution: str = Form("1920x1080")):
    validate_project_config(theme, focus_minutes, break_minutes, duration_minutes, resolution)
    with SessionLocal() as db:
        project = Project(theme=theme, focus_minutes=focus_minutes, break_minutes=break_minutes, duration_minutes=duration_minutes, resolution=resolution)
        db.add(project)
        db.commit()
        db.refresh(project)
        project_id = project.id
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.post("/presets")
def create_preset(name: str = Form(...), theme: str = Form(...), focus_minutes: int = Form(25), break_minutes: int = Form(5), duration_minutes: int = Form(120), resolution: str = Form("1920x1080")):
    clean_name = name.strip()
    if not clean_name or len(clean_name) > 80:
        raise HTTPException(400, "El nom del preset ha de tindre entre 1 i 80 caràcters")
    validate_project_config(theme, focus_minutes, break_minutes, duration_minutes, resolution)
    with SessionLocal() as db:
        if db.query(Preset).filter(Preset.name == clean_name).first():
            raise HTTPException(409, "Ja existeix un preset amb este nom")
        db.add(Preset(name=clean_name, theme=theme, focus_minutes=focus_minutes, break_minutes=break_minutes, duration_minutes=duration_minutes, resolution=resolution))
        db.commit()
    return RedirectResponse("/", 303)


@app.post("/presets/{preset_id}/delete")
def delete_preset(preset_id: int):
    with SessionLocal() as db:
        preset = db.get(Preset, preset_id)
        if not preset:
            raise HTTPException(404, "Preset no trobat")
        db.delete(preset)
        db.commit()
    return RedirectResponse("/", 303)


@app.post("/projects/{project_id}/duplicate")
def duplicate_project(project_id: int):
    with SessionLocal() as db:
        source = db.get(Project, project_id)
        if not source:
            raise HTTPException(404, "Projecte no trobat")
        duplicate = Project(theme=source.theme, focus_minutes=source.focus_minutes, break_minutes=source.break_minutes, duration_minutes=source.duration_minutes, resolution=source.resolution)
        db.add(duplicate)
        db.commit()
        db.refresh(duplicate)
        duplicate_id = duplicate.id
    return RedirectResponse(f"/projects/{duplicate_id}", 303)


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_view(project_id: int, request: Request):
    with SessionLocal() as db:
        project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projecte no trobat")
    timeline = build_timeline(project.focus_minutes, project.break_minutes, project.duration_minutes)
    return templates.TemplateResponse(request, "project.html", {"project": project, "timeline": timeline, "chapters": build_chapters(timeline), "duration": format_timestamp(timeline.total_seconds), "focus_total": timeline.focus_seconds // 60, "break_total": timeline.break_seconds // 60, "assets": catalog(), "job": render_queue.jobs.get(project_id)})


@app.post("/projects/{project_id}/render")
def start_render(project_id: int, background: str = Form(...), ambience: list[str] | None = Form(None), music: str = Form(""), ambience_volume: float = Form(.25), music_volume: float = Form(.12)):
    current = render_queue.jobs.get(project_id)
    if current and current.status in {"EN_CUA", "GENERANT"}:
        return RedirectResponse(f"/projects/{project_id}", 303)
    if not 0 <= ambience_volume <= 1 or not 0 <= music_volume <= 1:
        raise HTTPException(400, "Els volums han d'estar entre 0 i 1")
    with SessionLocal() as db:
        project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Projecte no trobat")
    try:
        bg = resolve_asset("backgrounds", background)
        amb = [AudioTrack(resolve_asset("ambience", n), ambience_volume) for n in (ambience or [])]
        mus = AudioTrack(resolve_asset("music", music), music_volume) if music else None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    timeline = build_timeline(project.focus_minutes, project.break_minutes, project.duration_minutes)
    folder = create_output_dir(project.id, project.theme)
    try:
        write_metadata(folder, theme=project.theme, focus=project.focus_minutes, pause=project.break_minutes, duration=project.duration_minutes, resolution=project.resolution, timeline=timeline)
        generate_thumbnail(bg, folder / "thumbnail.jpg", f"{publication_theme(project.theme).upper()} - {project.duration_minutes} MIN - {project.focus_minutes}/{project.break_minutes}")
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(500, f"No s'ha pogut preparar el renderitzat: {exc}") from exc
    render_queue.enqueue(project.id, RenderSpec(bg, folder / "video.mp4", project.resolution, timeline, ambience=amb, music=mus))
    with SessionLocal() as db:
        saved = db.get(Project, project_id)
        saved.status = "QUEUED"
        saved.output_path = str(folder)
        db.commit()
    return RedirectResponse(f"/projects/{project_id}", 303)


@app.get("/api/projects/{project_id}/render")
def render_status(project_id: int):
    job = render_queue.jobs.get(project_id)
    if not job:
        with SessionLocal() as db:
            project = db.get(Project, project_id)
        if not project:
            raise HTTPException(404, "Projecte no trobat")
        return {"status": project.status, "progress": 100 if project.status == "COMPLETED" else 0}
    return {"status": job.status, "progress": round(job.progress, 1), "elapsed": round(job.elapsed), "eta": round(job.eta) if job.eta is not None else None, "error": job.error, "output": job.output}


@app.post("/projects/{project_id}/cancel")
def cancel_render(project_id: int):
    if not render_queue.cancel(project_id):
        raise HTTPException(404, "No hi ha cap renderitzat actiu")
    return RedirectResponse(f"/projects/{project_id}", 303)
