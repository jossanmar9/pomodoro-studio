from contextlib import asynccontextmanager
import shutil
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Project
from app.services.assets import catalog, resolve_asset
from app.services.jobs import render_queue
from app.services.metadata import create_output_dir, write_metadata
from app.services.renderer import AudioTrack, RenderSpec
from app.services.thumbnail import generate_thumbnail
from app.services.timer import build_chapters, build_timeline, format_timestamp

@asynccontextmanager
async def lifespan(_:FastAPI): init_db(); yield
app=FastAPI(title=settings.app_name,lifespan=lifespan); app.mount("/static",StaticFiles(directory="app/static"),name="static"); templates=Jinja2Templates(directory="app/templates")
THEMES=["Biblioteca medieval","Biblioteca màgica","Biblioteca èlfica","Taverna medieval","Torre de l'alquimista","Castell gòtic","Cabana amb pluja","Biblioteca victoriana","Vaixell pirata","Roma antiga","Grècia antiga","Japó feudal","Nau espacial","Búnquer postapocalíptic","Bosc","Observatori","Cafeteria acollidora"]
@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/",response_class=HTMLResponse)
def home(request:Request):
    with SessionLocal() as db: projects=db.query(Project).order_by(Project.id.desc()).limit(10).all()
    return templates.TemplateResponse(request,"index.html",{"themes":THEMES,"projects":projects})
@app.post("/projects")
def create_project(theme:str=Form(...),focus_minutes:int=Form(25),break_minutes:int=Form(5),duration_minutes:int=Form(120),resolution:str=Form("1920x1080")):
    if theme not in THEMES: raise HTTPException(400,"Ambientació no vàlida")
    if resolution not in {"1920x1080","2560x1440"}: raise HTTPException(400,"Resolució no vàlida")
    if not 1<=focus_minutes<=180 or not 0<=break_minutes<=60 or not 1<=duration_minutes<=720: raise HTTPException(400,"Configuració Pomodoro fora dels límits admesos")
    build_timeline(focus_minutes,break_minutes,duration_minutes)
    with SessionLocal() as db: project=Project(theme=theme,focus_minutes=focus_minutes,break_minutes=break_minutes,duration_minutes=duration_minutes,resolution=resolution); db.add(project); db.commit(); db.refresh(project); project_id=project.id
    return RedirectResponse(f"/projects/{project_id}",status_code=303)
@app.get("/projects/{project_id}",response_class=HTMLResponse)
def project_view(project_id:int,request:Request):
    with SessionLocal() as db: project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Projecte no trobat")
    timeline=build_timeline(project.focus_minutes,project.break_minutes,project.duration_minutes)
    return templates.TemplateResponse(request,"project.html",{"project":project,"timeline":timeline,"chapters":build_chapters(timeline),"duration":format_timestamp(timeline.total_seconds),"focus_total":timeline.focus_seconds//60,"break_total":timeline.break_seconds//60,"assets":catalog(),"job":render_queue.jobs.get(project_id)})
@app.post("/projects/{project_id}/render")
def start_render(project_id:int,background:str=Form(...),ambience:list[str]=Form(default=[]),music:str=Form(""),ambience_volume:float=Form(.25),music_volume:float=Form(.12)):
    current=render_queue.jobs.get(project_id)
    if current and current.status in {"EN_CUA","GENERANT"}: return RedirectResponse(f"/projects/{project_id}",status_code=303)
    if not 0<=ambience_volume<=1 or not 0<=music_volume<=1: raise HTTPException(400,"Els volums han d'estar entre 0 i 1")
    with SessionLocal() as db: project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Projecte no trobat")
    try: bg=resolve_asset("backgrounds",background); amb=[AudioTrack(resolve_asset("ambience",name),ambience_volume) for name in ambience]; mus=AudioTrack(resolve_asset("music",music),music_volume) if music else None
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    timeline=build_timeline(project.focus_minutes,project.break_minutes,project.duration_minutes); folder=create_output_dir(project.id,project.theme)
    try: write_metadata(folder,theme=project.theme,focus=project.focus_minutes,pause=project.break_minutes,duration=project.duration_minutes,resolution=project.resolution,timeline=timeline); generate_thumbnail(bg,folder/"thumbnail.jpg",f"{project.theme.upper()} - {project.duration_minutes} MIN - {project.focus_minutes}/{project.break_minutes}")
    except Exception as exc: shutil.rmtree(folder,ignore_errors=True); raise HTTPException(500,f"No s'ha pogut preparar el renderitzat: {exc}") from exc
    render_queue.enqueue(project.id,RenderSpec(bg,folder/"video.mp4",project.resolution,timeline,ambience=amb,music=mus))
    with SessionLocal() as db: saved=db.get(Project,project_id); saved.status="QUEUED"; saved.output_path=str(folder); db.commit()
    return RedirectResponse(f"/projects/{project_id}",status_code=303)
@app.get("/api/projects/{project_id}/render")
def render_status(project_id:int):
    job=render_queue.jobs.get(project_id)
    if not job: return {"status":"SENSE_RENDER","progress":0}
    mapped={"EN_CUA":"QUEUED","GENERANT":"GENERATING","COMPLETAT":"COMPLETED","ERROR":"FAILED","CANCEL·LAT":"CANCELLED"}
    if job.status in mapped:
        with SessionLocal() as db:
            project=db.get(Project,project_id)
            if project and project.status!=mapped[job.status]: project.status=mapped[job.status]; db.commit()
    return {"status":job.status,"progress":round(job.progress,1),"elapsed":round(job.elapsed),"eta":round(job.eta) if job.eta is not None else None,"error":job.error,"output":job.output}
@app.post("/projects/{project_id}/cancel")
def cancel_render(project_id:int): render_queue.cancel(project_id); return RedirectResponse(f"/projects/{project_id}",status_code=303)
