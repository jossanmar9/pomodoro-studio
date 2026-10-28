from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Project
from app.services.timer import build_chapters, build_timeline, format_timestamp


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

THEMES = [
    "Biblioteca medieval",
    "Biblioteca màgica",
    "Biblioteca èlfica",
    "Taverna medieval",
    "Torre de l'alquimista",
    "Castell gòtic",
    "Cabana amb pluja",
    "Biblioteca victoriana",
    "Vaixell pirata",
    "Roma antiga",
    "Grècia antiga",
    "Japó feudal",
    "Nau espacial",
    "Búnquer postapocalíptic",
    "Bosc",
    "Observatori",
    "Cafeteria acollidora",
]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with SessionLocal() as db:
        projects = db.query(Project).order_by(Project.id.desc()).limit(10).all()
    return templates.TemplateResponse(request, "index.html", {"themes": THEMES, "projects": projects})


@app.post("/projects", response_class=HTMLResponse)
def create_project(
    request: Request,
    theme: str = Form(...),
    focus_minutes: int = Form(25),
    break_minutes: int = Form(5),
    duration_minutes: int = Form(120),
    resolution: str = Form("1920x1080"),
):
    timeline = build_timeline(focus_minutes, break_minutes, duration_minutes)
    with SessionLocal() as db:
        project = Project(
            theme=theme,
            focus_minutes=focus_minutes,
            break_minutes=break_minutes,
            duration_minutes=duration_minutes,
            resolution=resolution,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

    return templates.TemplateResponse(request, "project.html", {
        "project": project,
        "timeline": timeline,
        "chapters": build_chapters(timeline),
        "duration": format_timestamp(timeline.total_seconds),
        "focus_total": timeline.focus_seconds // 60,
        "break_total": timeline.break_seconds // 60,
    })
