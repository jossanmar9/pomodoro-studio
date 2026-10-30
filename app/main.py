from contextlib import asynccontextmanager
from pathlib import Path
import random
import re
import logging
import shutil
import subprocess
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.services.ambience_web import router as ambience_router
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import AUTO_ACTIVE_STEPS, AutoRun, Preset, Project, PublicationMetadata, RenderConfig, YouTubePublication
from app.services.assets import catalog, resolve_asset
from app.services.encoding import ENGINES, QUALITY_PROFILES, EncodingOptions, nvenc_available
from app.services.jobs import render_queue
from app.services.metadata import PublicationDraft, build_publication_zip, create_output_dir, default_publication, validate_publication, write_metadata
from app.services.renderer import AudioTrack, RenderSpec
from app.services.fonts import fonts_for_theme
from app.services.thumbnail import generate_thumbnail
from app.services.timer import build_chapters, build_timeline, format_timestamp
from app.services.youtube import YouTubeUnavailable, YouTubeUploadSpec, credentials, forget_upload, upload_video, youtube_configured
from app.services.power import power
from app.services.autopilot import cleanup_published_videos, autopilot, run_summary, youtube_connected
from app.services.background_library import library as background_library
from app.services.autopilot_plan import AMBIENCE_LEVELS, AUTO_THEMES, FORMATS, NOISE_COLORS, NOISE_ENVIRONMENT, PRIMARY_AMBIENCE_LOUDNESS, DURATION_CHOICES, ENVIRONMENTS, POMODORO_CHOICES, PRIVACY_CHOICES, build_preview_command, choose_ambience, find_backgrounds, load_catalog
from app.themes import THEMES, publication_theme

RESOLUTIONS={"1920x1080","2560x1440"}; STATUSES={"DRAFT","QUEUED","GENERATING","COMPLETED","FAILED","CANCELLED"}; OUTPUT_FILES={"video.mp4","thumbnail.jpg","title.txt","description.txt","chapters.txt","tags.txt","metadata.json","publication-package.zip"}

def validate_project_config(theme,focus_minutes,break_minutes,duration_minutes,resolution):
    if theme not in THEMES: raise HTTPException(400,"Ambientació no vàlida")
    if resolution not in RESOLUTIONS: raise HTTPException(400,"Resolució no vàlida")
    if not 1<=focus_minutes<=180 or not 0<=break_minutes<=60 or not 1<=duration_minutes<=720: raise HTTPException(400,"Configuració Pomodoro fora dels límits admesos")
    build_timeline(focus_minutes,break_minutes,duration_minutes)
def output_file(project,filename):
    if filename not in OUTPUT_FILES or not project.output_path: raise HTTPException(404,"Fitxer no disponible")
    root=Path(project.output_path).resolve(); path=(root/filename).resolve()
    if path.parent!=root or not path.is_file(): raise HTTPException(404,"Fitxer no disponible")
    return path
def publication_for(project,saved):
    timeline=build_timeline(project.focus_minutes,project.break_minutes,project.duration_minutes)
    return PublicationDraft(saved.title,saved.description,saved.chapters,saved.tags,saved.language) if saved else default_publication(theme=project.theme,focus=project.focus_minutes,pause=project.break_minutes,duration=project.duration_minutes,timeline=timeline)
@asynccontextmanager
async def lifespan(_):
    init_db()
    try: cleanup_published_videos()
    except Exception: logging.getLogger(__name__).exception("Ha fallat la neteja de vídeos publicats")
    yield
app=FastAPI(title=settings.app_name,lifespan=lifespan); app.mount("/static",StaticFiles(directory="app/static"),name="static"); templates=Jinja2Templates(directory="app/templates")
@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/assets/{kind}/{name}")
def asset_file(kind,name):
    try: path=resolve_asset(kind,name)
    except ValueError as exc: raise HTTPException(404,str(exc)) from exc
    return FileResponse(path)
@app.get("/estudi",response_class=HTMLResponse)
def home(request:Request,status:str=Query(""),theme:str=Query("")):
    with SessionLocal() as db:
        query=db.query(Project)
        if status:
            if status not in STATUSES: raise HTTPException(400,"Estat no vàlid")
            query=query.filter(Project.status==status)
        if theme:
            if theme not in THEMES: raise HTTPException(400,"Ambientació no vàlida")
            query=query.filter(Project.theme==theme)
        projects=query.order_by(Project.id.desc()).limit(100).all(); presets=db.query(Preset).order_by(Preset.name.asc()).all()
    return templates.TemplateResponse(request,"index.html",{"themes":list(THEMES),"projects":projects,"presets":presets,"status_filter":status,"theme_filter":theme,"statuses":sorted(STATUSES)})
@app.post("/projects")
def create_project(theme:str=Form(...),focus_minutes:int=Form(25),break_minutes:int=Form(5),duration_minutes:int=Form(120),resolution:str=Form("1920x1080")):
    validate_project_config(theme,focus_minutes,break_minutes,duration_minutes,resolution)
    with SessionLocal() as db: project=Project(theme=theme,focus_minutes=focus_minutes,break_minutes=break_minutes,duration_minutes=duration_minutes,resolution=resolution); db.add(project); db.commit(); db.refresh(project); pid=project.id
    return RedirectResponse(f"/projects/{pid}",303)
@app.post("/projects/{project_id}/edit")
def edit_project(project_id:int,theme:str=Form(...),focus_minutes:int=Form(...),break_minutes:int=Form(...),duration_minutes:int=Form(...),resolution:str=Form(...)):
    validate_project_config(theme,focus_minutes,break_minutes,duration_minutes,resolution)
    with SessionLocal() as db:
        project=db.get(Project,project_id)
        if not project: raise HTTPException(404,"Projecte no trobat")
        current=render_queue.jobs.get(project_id)
        if current and current.status in {"EN_CUA","GENERANT"}: raise HTTPException(409,"No es pot editar mentre hi ha un renderitzat actiu")
        project.theme=theme; project.focus_minutes=focus_minutes; project.break_minutes=break_minutes; project.duration_minutes=duration_minutes; project.resolution=resolution; project.status="DRAFT"; project.output_path=None; db.commit()
    return RedirectResponse(f"/projects/{project_id}",303)
@app.post("/presets")
def create_preset(name:str=Form(...),theme:str=Form(...),focus_minutes:int=Form(25),break_minutes:int=Form(5),duration_minutes:int=Form(120),resolution:str=Form("1920x1080")):
    clean=name.strip()
    if not clean or len(clean)>80: raise HTTPException(400,"El nom del preset ha de tindre entre 1 i 80 caràcters")
    validate_project_config(theme,focus_minutes,break_minutes,duration_minutes,resolution)
    with SessionLocal() as db:
        if db.query(Preset).filter(Preset.name==clean).first(): raise HTTPException(409,"Ja existeix un preset amb este nom")
        db.add(Preset(name=clean,theme=theme,focus_minutes=focus_minutes,break_minutes=break_minutes,duration_minutes=duration_minutes,resolution=resolution)); db.commit()
    return RedirectResponse("/estudi",303)
@app.post("/presets/{preset_id}/delete")
def delete_preset(preset_id:int):
    with SessionLocal() as db:
        preset=db.get(Preset,preset_id)
        if not preset: raise HTTPException(404,"Preset no trobat")
        db.delete(preset); db.commit()
    return RedirectResponse("/estudi",303)
@app.post("/projects/{project_id}/duplicate")
def duplicate_project(project_id:int):
    with SessionLocal() as db:
        source=db.get(Project,project_id)
        if not source: raise HTTPException(404,"Projecte no trobat")
        dup=Project(theme=source.theme,focus_minutes=source.focus_minutes,break_minutes=source.break_minutes,duration_minutes=source.duration_minutes,resolution=source.resolution); db.add(dup); db.commit(); db.refresh(dup)
        cfg=db.query(RenderConfig).filter(RenderConfig.project_id==source.id).first(); meta=db.query(PublicationMetadata).filter(PublicationMetadata.project_id==source.id).first()
        if cfg: db.add(RenderConfig(project_id=dup.id,engine=cfg.engine,quality=cfg.quality))
        if meta: db.add(PublicationMetadata(project_id=dup.id,title=meta.title,description=meta.description,chapters=meta.chapters,tags=meta.tags,language=meta.language))
        db.commit(); did=dup.id
    return RedirectResponse(f"/projects/{did}",303)
@app.get("/projects/{project_id}",response_class=HTMLResponse)
def project_view(project_id:int,request:Request):
    with SessionLocal() as db:
        project=db.get(Project,project_id)
        if not project: raise HTTPException(404,"Projecte no trobat")
        cfg=db.query(RenderConfig).filter(RenderConfig.project_id==project_id).first(); meta=db.query(PublicationMetadata).filter(PublicationMetadata.project_id==project_id).first(); yt=db.query(YouTubePublication).filter(YouTubePublication.project_id==project_id).first(); publication=publication_for(project,meta)
    timeline=build_timeline(project.focus_minutes,project.break_minutes,project.duration_minutes); outputs=[]
    if project.output_path: outputs=[n for n in OUTPUT_FILES if (Path(project.output_path)/n).is_file()]
    return templates.TemplateResponse(request,"project.html",{"project":project,"timeline":timeline,"chapters":build_chapters(timeline),"duration":format_timestamp(timeline.total_seconds),"focus_total":timeline.focus_seconds//60,"break_total":timeline.break_seconds//60,"assets":catalog(),"job":render_queue.jobs.get(project_id),"themes":list(THEMES),"available_outputs":sorted(outputs),"render_config":cfg,"nvenc_available":nvenc_available(),"publication":publication,"publication_errors":validate_publication(publication),"youtube":yt,"youtube_configured":youtube_configured()})
@app.post("/projects/{project_id}/publication")
def save_publication(project_id:int,title:str=Form(...),description:str=Form(""),chapters:str=Form(""),tags:str=Form(""),language:str=Form("en")):
    draft=PublicationDraft(title.strip(),description,chapters,tags,language); errors=validate_publication(draft)
    if errors: raise HTTPException(400,"; ".join(errors))
    with SessionLocal() as db:
        p=db.get(Project,project_id)
        if not p: raise HTTPException(404,"Projecte no trobat")
        saved=db.query(PublicationMetadata).filter(PublicationMetadata.project_id==project_id).first() or PublicationMetadata(project_id=project_id); db.add(saved); saved.title=draft.title; saved.description=draft.description; saved.chapters=draft.chapters; saved.tags=draft.tags; saved.language=draft.language
        vals=(p.output_path,p.theme,p.focus_minutes,p.break_minutes,p.duration_minutes,p.resolution); db.commit()
    if vals[0]:
        tl=build_timeline(vals[2],vals[3],vals[4]); write_metadata(Path(vals[0]),theme=vals[1],focus=vals[2],pause=vals[3],duration=vals[4],resolution=vals[5],timeline=tl,draft=draft)
    return RedirectResponse(f"/projects/{project_id}",303)
@app.post("/projects/{project_id}/publication/regenerate")
def regenerate_publication(project_id:int):
    with SessionLocal() as db:
        p=db.get(Project,project_id)
        if not p or not p.output_path: raise HTTPException(404,"No hi ha cap resultat per regenerar")
        meta=db.query(PublicationMetadata).filter(PublicationMetadata.project_id==project_id).first(); draft=publication_for(p,meta); vals=(p.output_path,p.theme,p.focus_minutes,p.break_minutes,p.duration_minutes,p.resolution)
    tl=build_timeline(vals[2],vals[3],vals[4]); write_metadata(Path(vals[0]),theme=vals[1],focus=vals[2],pause=vals[3],duration=vals[4],resolution=vals[5],timeline=tl,draft=draft); return RedirectResponse(f"/projects/{project_id}",303)
@app.get("/projects/{project_id}/publication/package")
def publication_package(project_id:int):
    with SessionLocal() as db:
        p=db.get(Project,project_id); output=p.output_path if p else None
    if not output or not Path(output).is_dir(): raise HTTPException(404,"Paquet no disponible")
    return FileResponse(build_publication_zip(Path(output).resolve()),filename=f"pomodoro-studio-{project_id}-publication.zip",media_type="application/zip")
@app.get("/projects/{project_id}/files/{filename}")
def project_output(project_id:int,filename:str):
    with SessionLocal() as db: p=db.get(Project,project_id)
    if not p: raise HTTPException(404,"Projecte no trobat")
    path=output_file(p,filename); return FileResponse(path,filename=path.name)
@app.post("/projects/{project_id}/youtube")
def publish_youtube(project_id:int,privacy:str=Form("private"),category_id:str=Form("27")):
    with SessionLocal() as db:
        p=db.get(Project,project_id)
        if not p or not p.output_path: raise HTTPException(409,"Primer has de generar el vídeo")
        meta=db.query(PublicationMetadata).filter(PublicationMetadata.project_id==project_id).first(); draft=publication_for(p,meta); root=Path(p.output_path); record=db.query(YouTubePublication).filter(YouTubePublication.project_id==project_id).first() or YouTubePublication(project_id=project_id); db.add(record); record.privacy=privacy; record.category_id=category_id; record.status="UPLOADING"; record.error=None; db.commit()
    description=draft.description if not draft.chapters.strip() or draft.chapters.strip() in draft.description else draft.description+"\n\n"+draft.chapters
    spec=YouTubeUploadSpec(root/"video.mp4",draft.title,description,[x.strip() for x in draft.tags.split(",") if x.strip()],category_id,draft.language,privacy,(root/"thumbnail.jpg") if (root/"thumbnail.jpg").is_file() else None)
    try: video_id=upload_video(spec)
    except (ValueError,YouTubeUnavailable,Exception) as exc:
        with SessionLocal() as db:
            record=db.query(YouTubePublication).filter(YouTubePublication.project_id==project_id).first(); record.status="FAILED"; record.error=str(exc)[:2000]; db.commit()
        return RedirectResponse(f"/projects/{project_id}",303)
    with SessionLocal() as db:
        record=db.query(YouTubePublication).filter(YouTubePublication.project_id==project_id).first(); record.status="PUBLISHED"; record.video_id=video_id; record.error=None; db.commit()
    return RedirectResponse(f"/projects/{project_id}",303)
@app.post("/projects/{project_id}/render")
def start_render(project_id:int,background:str=Form(...),ambience:list[str]|None=Form(None),music:str=Form(""),ambience_volume:float=Form(.25),music_volume:float=Form(.12),engine:str=Form("auto"),quality:str=Form("balanced")):
    current=render_queue.jobs.get(project_id)
    if current and current.status in {"EN_CUA","GENERANT"}: return RedirectResponse(f"/projects/{project_id}",303)
    if not 0<=ambience_volume<=1 or not 0<=music_volume<=1: raise HTTPException(400,"Els volums han d'estar entre 0 i 1")
    if engine not in ENGINES or quality not in QUALITY_PROFILES: raise HTTPException(400,"Configuració de renderitzat no vàlida")
    with SessionLocal() as db: p=db.get(Project,project_id); meta=db.query(PublicationMetadata).filter(PublicationMetadata.project_id==project_id).first() if p else None; draft=publication_for(p,meta) if p else None
    if not p: raise HTTPException(404,"Projecte no trobat")
    try: bg=resolve_asset("backgrounds",background); amb=[AudioTrack(resolve_asset("ambience",n),ambience_volume) for n in (ambience or [])]; mus=AudioTrack(resolve_asset("music",music),music_volume) if music else None
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    tl=build_timeline(p.focus_minutes,p.break_minutes,p.duration_minutes); folder=create_output_dir(p.id,p.theme)
    try: write_metadata(folder,theme=p.theme,focus=p.focus_minutes,pause=p.break_minutes,duration=p.duration_minutes,resolution=p.resolution,timeline=tl,draft=draft); fonts=fonts_for_theme(p.theme); generate_thumbnail(bg,folder/"thumbnail.jpg",f"{publication_theme(p.theme).upper()} - {p.duration_minutes} MIN - {p.focus_minutes}/{p.break_minutes}",68,fonts.label if fonts.uppercase_labels else fonts.digits)
    except Exception as exc: shutil.rmtree(folder,ignore_errors=True); raise HTTPException(500,f"No s'ha pogut preparar el renderitzat: {exc}") from exc
    with SessionLocal() as db:
        saved=db.get(Project,project_id); cfg=db.query(RenderConfig).filter(RenderConfig.project_id==project_id).first() or RenderConfig(project_id=project_id); db.add(cfg); cfg.engine=engine; cfg.quality=quality; cfg.actual_engine=None; saved.status="QUEUED"; saved.output_path=str(folder); db.commit()
    render_queue.enqueue(p.id,RenderSpec(bg,folder/"video.mp4",p.resolution,tl,ambience=amb,music=mus,encoding=EncodingOptions(engine,quality),fonts=fonts_for_theme(p.theme))); return RedirectResponse(f"/projects/{project_id}",303)
@app.get("/api/projects/{project_id}/render")
def render_status(project_id:int):
    job=render_queue.jobs.get(project_id)
    if not job:
        with SessionLocal() as db: p=db.get(Project,project_id); cfg=db.query(RenderConfig).filter(RenderConfig.project_id==project_id).first()
        if not p: raise HTTPException(404,"Projecte no trobat")
        return {"status":p.status,"progress":100 if p.status=="COMPLETED" else 0,"engine":cfg.actual_engine if cfg else None}
    return {"status":job.status,"progress":round(job.progress,1),"elapsed":round(job.elapsed),"eta":round(job.eta) if job.eta is not None else None,"error":job.error,"output":job.output,"engine":job.engine,"fallback_used":job.fallback_used}
@app.post("/projects/{project_id}/cancel")
def cancel_render(project_id:int):
    if not render_queue.cancel(project_id): raise HTTPException(404,"No hi ha cap renderitzat actiu")
    return RedirectResponse(f"/projects/{project_id}",303)


app.include_router(ambience_router)
from app.services.library_web import router as library_router  # noqa: E402
app.include_router(library_router)


# --- Mode automàtic: una pàgina, un botó ------------------------------------

def _recent_runs(limit:int=12)->list[dict]:
    with SessionLocal() as db:
        return [run_summary(r) for r in db.query(AutoRun).order_by(AutoRun.id.desc()).limit(limit).all()]


@app.get("/",response_class=HTMLResponse)
def auto_home(request:Request,error:str=Query("")):
    try: cleanup_published_videos()
    except Exception: logging.getLogger(__name__).exception("Ha fallat la neteja de vídeos publicats")
    gallery={group["theme"]:[{k:item[k] for k in ("name","url","format","environment")} for item in group["items"]] for group in background_library()}
    themes=[{"name":t,"backgrounds":len(gallery.get(t,[]))} for t in AUTO_THEMES]
    environments=[{"key":k,"label":e.label} for k,e in ENVIRONMENTS.items()]
    counts={"ambience":len(catalog().ambience),"music":len(catalog().music)}
    return templates.TemplateResponse(request,"auto.html",{
        "themes":themes,"environments":environments,"durations":DURATION_CHOICES,"pomodoros":list(POMODORO_CHOICES),
        "privacy_choices":PRIVACY_CHOICES,"default_privacy":settings.auto_default_privacy if settings.auto_default_privacy in PRIVACY_CHOICES else "private",
        "youtube_configured":youtube_configured(),"youtube_connected":youtube_connected(),"backgrounds":gallery,
        "counts":counts,"runs":_recent_runs(),"error":error[:300],"music_default":settings.auto_music_default,"levels":AMBIENCE_LEVELS,
        "keep_days":settings.keep_published_days,"formats":FORMATS,"noise_colors":{k:v[2] for k,v in NOISE_COLORS.items()},
    })


@app.post("/auto")
def auto_create(theme:str=Form(...),environment:str=Form(""),duration_minutes:int=Form(...),pomodoro:str=Form("25/5"),privacy:str=Form("public"),publish:str=Form(""),music:str=Form(""),chime:str=Form(""),ambience_level:int=Form(0),ambience_files:str=Form(""),format:str=Form("pomodoro"),noise:str=Form(""),dim:str=Form(""),motion:str=Form(""),background:str=Form(""),shutdown:str=Form(""),delete_after:str=Form("")):
    if format not in FORMATS: raise HTTPException(400,"Format no vàlid")
    if theme not in AUTO_THEMES: raise HTTPException(400,"Ambientació no vàlida")
    if format=="soroll":
        if noise not in NOISE_COLORS: raise HTTPException(400,"Color de soroll no vàlid")
        environment,music,ambience_files=NOISE_ENVIRONMENT,"",""
    elif environment not in ENVIRONMENTS: raise HTTPException(400,"Entorn no vàlid")
    else: noise=""
    if format!="pomodoro": chime=""
    if format not in {"dormir","soroll"}: dim=""
    if background and background not in {p.name for p in find_backgrounds(settings.assets_dir/"backgrounds",theme)}: raise HTTPException(400,"Fons no vàlid")
    if duration_minutes not in DURATION_CHOICES: raise HTTPException(400,"Duració no vàlida")
    if pomodoro not in POMODORO_CHOICES: raise HTTPException(400,"Pomodoro no vàlid")
    if privacy not in PRIVACY_CHOICES: raise HTTPException(400,"Privacitat no vàlida")
    if ambience_level not in AMBIENCE_LEVELS: raise HTTPException(400,"Volum d'ambient no vàlid")
    files=[n for n in ambience_files.split(",") if n and Path(n).name==n and len(n)<=120][:4]
    focus,pause=POMODORO_CHOICES[pomodoro]
    with SessionLocal() as db:
        run=AutoRun(theme=theme,environment=environment,duration_minutes=duration_minutes,focus_minutes=focus,break_minutes=pause,privacy=privacy,publish=1 if publish else 0,music=1 if music else 0,chime=1 if chime else 0,ambience_level=ambience_level,ambience_files=",".join(files) or None,format=format,noise=noise or None,dim=1 if dim else 0,motion=1 if motion else 0,background=background or None,shutdown=1 if shutdown else 0,delete_after=1 if delete_after else 0)
        db.add(run); db.commit(); run_id=run.id
    autopilot.submit(run_id)
    return RedirectResponse("/",303)


@app.get("/api/auto")
def auto_status():
    return {"runs":_recent_runs(),"youtube_connected":youtube_connected(),"shutdown":power.status()}


@app.post("/api/shutdown/cancel")
def cancel_shutdown():
    return {"cancelled":power.cancel()}


@app.post("/auto/{run_id}/publish")
def auto_publish(run_id:int,again:str=Form("")):
    """Publica un vídeo ja fet. Amb again=1 el torna a pujar encara que ja s'haja pujat."""
    if not youtube_connected(): return RedirectResponse("/?error="+quote("Primer connecta YouTube"),303)
    with SessionLocal() as db:
        run=db.get(AutoRun,run_id)
        if not run or not run.project_id: raise HTTPException(404,"Execució no trobada")
        if run.step in AUTO_ACTIVE_STEPS or (run.video_id and not again): raise HTTPException(409,"Esta execució no es pot publicar ara")
        project=db.get(Project,run.project_id)
        if not project or project.status!="COMPLETED" or not project.output_path: raise HTTPException(409,"El vídeo no està acabat")
        if again:
            forget_upload(Path(project.output_path)/"video.mp4")
            run.video_id=None
            db.commit()
    autopilot.submit_publish(run_id)
    return RedirectResponse("/",303)


@app.post("/youtube/connect")
def youtube_connect():
    """Obri el navegador per autoritzar el canal una sola vegada i guarda el token."""
    try: credentials()
    except Exception as exc: return RedirectResponse("/?error="+quote(f"No s'ha pogut connectar YouTube: {exc}"),303)
    return RedirectResponse("/",303)


PREVIEW_DIR_NAME="previews"
PREVIEW_NAME=re.compile(r"^preview-[a-f0-9]{32}\.mp3$")


def _preview_dir()->Path:
    folder=Path("data")/PREVIEW_DIR_NAME; folder.mkdir(parents=True,exist_ok=True); return folder


@app.post("/api/auto/preview")
def auto_preview(environment:str=Form(""),ambience_level:int=Form(0),music:str=Form(""),chime:str=Form(""),ambience_files:str=Form(""),format:str=Form("pomodoro"),noise:str=Form("")):
    """30 segons amb els sons i el volum que tindrà el vídeo."""
    if format not in FORMATS: raise HTTPException(400,"Format no vàlid")
    if ambience_level not in AMBIENCE_LEVELS: raise HTTPException(400,"Volum d'ambient no vàlid")
    if format!="pomodoro": chime=""
    rng=random.Random(); noise_color=None; layers=[]; env=None; track=None
    if format=="soroll":
        if noise not in NOISE_COLORS: raise HTTPException(400,"Color de soroll no vàlid")
        noise_color=NOISE_COLORS[noise][0]
    else:
        if environment not in ENVIRONMENTS: raise HTTPException(400,"Entorn no vàlid")
        preferred=[n for n in ambience_files.split(",") if n and Path(n).name==n]
        try: layers=choose_ambience(settings.assets_dir/"ambience",environment,rng,level=ambience_level,preferred=preferred)
        except ValueError as exc: raise HTTPException(409,str(exc)) from exc
        env=ENVIRONMENTS[environment]
    if env is not None and env.music and (music or not env.layers):
        tracks=catalog().music
        if tracks: track=settings.assets_dir/"music"/rng.choice(tracks)
    folder=_preview_dir()
    for old in sorted(folder.glob("preview-*.mp3"),key=lambda p:p.stat().st_mtime)[:-5]: old.unlink(missing_ok=True)
    output=folder/f"preview-{uuid4().hex}.mp3"
    try: command=build_preview_command(layers,track,bool(chime),output,noise=noise_color,noise_loudness=PRIMARY_AMBIENCE_LOUDNESS+ambience_level)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    result=subprocess.run(command,capture_output=True,text=True,timeout=120,check=False)
    if result.returncode!=0 or not output.is_file(): raise HTTPException(500,"No s'ha pogut preparar la mostra: "+(result.stderr or "")[-300:])
    names=load_catalog(settings.audio_catalog)
    sounds=([f"Soroll {NOISE_COLORS[noise][2].lower()}"] if noise_color else [])+[(names.get(l.path.name) or {}).get("title") or l.path.stem for l in layers]+([f"Música: {(names.get(track.name) or {}).get('title') or track.stem}"] if track else [])
    return {"url":f"/api/auto/preview/{output.name}","files":[l.path.name for l in layers],"sounds":sounds}


@app.get("/api/auto/preview/{name}")
def auto_preview_file(name:str):
    if not PREVIEW_NAME.fullmatch(name): raise HTTPException(404,"Mostra no disponible")
    path=_preview_dir()/name
    if not path.is_file(): raise HTTPException(404,"Mostra no disponible")
    return FileResponse(path,media_type="audio/mpeg",headers={"Cache-Control":"no-store"})
