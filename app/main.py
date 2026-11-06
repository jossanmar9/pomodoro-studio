from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
import random
import re
import json
import logging
import shutil
import subprocess
import time
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
from app.services.backup import backup_in_background
from app.services.youtube import YouTubeUnavailable, YouTubeUploadSpec, can_manage_playlists, credentials, has_all_permissions, forget_upload, reconnect as reconnect_youtube, upload_video, view_counts, youtube_configured
from app.services.suggestions import build_suggestions, cached_views, refresh_views_in_background
from app.services.schedule import from_local, label as schedule_label, local_day, next_slot
from app.services.power import power
from app.services.autopilot import cleanup_published_videos, autopilot, reel_missing, run_summary, short_missing, youtube_connected
from app.services.meta import facebook_configured, instagram_configured
from app.services.background_library import library as background_library
from app.services.breathing import DURATIONS as BREATH_DURATIONS, PATTERNS as BREATH_PATTERNS
from app.services.noise_screen import NOISE_SCREENS
from app.services.autopilot_plan import VISUAL_STYLES, MUSIC_LEVELS, NOISE_THEME, environments_by_label, group_themes, grouped_themes, music_advice, MUSIC_STYLES, music_style as music_style_for, music_tracks, AMBIENCE_LEVELS, AUTO_THEMES, FORMATS, NOISE_COLORS, NOISE_ENVIRONMENT, NOISE_LOUDNESS, PRIMARY_AMBIENCE_LOUDNESS, DURATION_CHOICES, ENVIRONMENTS, POMODORO_CHOICES, PRIVACY_CHOICES, build_preview_command, choose_ambience, find_backgrounds, load_catalog
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
    # En obrir Pomodoro: es publiquen els reels que falten (els dels vídeos programats, quan ja són públics).
    try: autopilot.submit_pending_reels()
    except Exception: logging.getLogger(__name__).exception("No s'han pogut revisar els reels pendents")
    backup_in_background()  # una vegada a la setmana: base de dades, .env i claus
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


from app.services.library_web import router as library_router  # noqa: E402
app.include_router(library_router)


# --- Mode automàtic: una pàgina, un botó ------------------------------------

def _recent_runs(limit:int=60)->list[dict]:
    with SessionLocal() as db:
        return [run_summary(r) for r in db.query(AutoRun).order_by(AutoRun.id.desc()).limit(limit).all()]


def _music_counts()->dict[str,int]:
    names=load_catalog(settings.audio_catalog)
    return {k:len(music_tracks(settings.assets_dir/"music",k,names)) for k in MUSIC_STYLES}


def _published_ids()->list[str]:
    """Identificadors de YouTube dels vídeos i Shorts publicats."""
    with SessionLocal() as db:
        rows=db.query(AutoRun).filter(AutoRun.step=="DONE",AutoRun.video_id.isnot(None)).all()
        ids=[]
        for r in rows:
            ids+=[r.video_id]+([r.short_video_id] if r.short_video_id and r.short_video_id!=r.video_id else [])+[i for i in (r.extra_short_ids or "").split(",") if i]
    return list(dict.fromkeys(ids))


def _stats()->dict:
    """Visualitzacions per tema, per format i per vídeo (de les dades guardades)."""
    views=cached_views(settings.youtube_stats_file)
    with SessionLocal() as db:
        rows=db.query(AutoRun).filter(AutoRun.step=="DONE",AutoRun.video_id.isnot(None)).order_by(AutoRun.id.desc()).all()
        videos=[]
        for r in rows:
            shorts=[i for i in ([r.short_video_id] if r.short_video_id and r.short_video_id!=r.video_id else [])+(r.extra_short_ids or "").split(",") if i]
            videos.append({"id":r.id,"theme":r.theme,"format":FORMATS.get(r.format or "pomodoro",r.format),"environment":ENVIRONMENTS[r.environment].label if r.environment in ENVIRONMENTS else r.environment,
                           "hours":r.duration_minutes/60,"url":f"https://youtu.be/{r.video_id}","views":views.get(r.video_id),
                           "short_views":sum(views.get(i,0) for i in shorts),"style":VISUAL_STYLES.get(r.visual_style or "realista","Realista"),"date":(r.published_at or r.created_at).strftime("%d/%m/%Y"),"is_short":r.format=="short"})
    def group(key):
        out={}
        for v in videos:
            if v["is_short"]: continue
            g=out.setdefault(v[key],{"name":v[key],"videos":0,"views":0,"short_views":0})
            g["videos"]+=1; g["views"]+=v["views"] or 0; g["short_views"]+=v["short_views"]
        for g in out.values(): g["average"]=round(g["views"]/g["videos"]) if g["videos"] else 0
        return sorted(out.values(),key=lambda g:(-g["average"],g["name"]))
    long_videos=[v for v in videos if not v["is_short"]]
    try: fetched=json.loads(settings.youtube_stats_file.read_text(encoding="utf-8")).get("fetched")
    except (OSError,ValueError): fetched=None
    return {"styles":group("style"),"themes":group("theme"),"formats":group("format"),"environments":group("environment"),
            "top":sorted([v for v in long_videos if v["views"] is not None],key=lambda v:-v["views"])[:10],
            "total_videos":len(long_videos),"total_views":sum(v["views"] or 0 for v in long_videos),
            "total_short_views":sum(v["short_views"] for v in videos)+sum(v["views"] or 0 for v in videos if v["is_short"]),
            "fetched":fetched,"has_views":bool(views)}


@app.get("/estadistiques",response_class=HTMLResponse)
def stats_page(request:Request,error:str=Query("")):
    return templates.TemplateResponse(request,"stats.html",{"stats":_stats(),"error":error[:300],"can_read":youtube_connected() and can_manage_playlists()})


@app.post("/estadistiques/actualitzar")
def stats_refresh():
    """Llig ara mateix les visualitzacions de YouTube."""
    try:
        counts=view_counts(_published_ids())
        settings.youtube_stats_file.parent.mkdir(parents=True,exist_ok=True)
        settings.youtube_stats_file.write_text(json.dumps({"fetched":datetime.utcnow().isoformat(timespec="seconds"),"views":counts}),encoding="utf-8")
    except Exception as exc:
        return RedirectResponse("/estadistiques?error="+quote(f"No s'han pogut llegir les dades de YouTube: {exc}"),303)
    return RedirectResponse("/estadistiques",303)


def _skip_reels(instagram:str,facebook:str,publish:str)->str|None:
    """Recorda les xarxes on NO es vol el reel (si estan configurades i s'ha desmarcat la casella)."""
    skip={}
    if publish and instagram_configured() and not instagram: skip["skip_ig"]=True
    if publish and facebook_configured() and not facebook: skip["skip_fb"]=True
    return json.dumps(skip) if skip else None


def _scheduled_for(schedule:str,publish_date:str,publish_time:str):
    """Quan es publica: «» en acabar, «next» (o «1») el pròxim dia lliure, «date» el dia i l'hora triats."""
    if schedule in {"next","1"}:
        return next_slot(datetime.utcnow(),_taken_slots(),hour=settings.publish_hour,zone=settings.timezone)
    if schedule=="date":
        try: when=from_local(publish_date,publish_time or f"{settings.publish_hour:02d}:00",settings.timezone)
        except ValueError: raise HTTPException(400,"Dia o hora de publicació no vàlids") from None
        if when<datetime.utcnow(): raise HTTPException(400,"El dia de publicació ja ha passat")
        return when
    return None


# Duració per defecte de cada format quan Pomodoro tria els vídeos de la setmana.
BATCH_DURATIONS={"pomodoro":120,"dormir":480,"llegir":180,"ambient":180}
BATCH_FORMATS=["pomodoro","dormir","llegir","pomodoro","ambient","dormir","llegir"]


def _guess_environment(name:str)->str|None:
    """Entorn d'un fons pel nom del fitxer (per als que no el tenen guardat en la fitxa)."""
    stem="-"+Path(name).stem+"-"
    found=[k for k in ENVIRONMENTS if f"-{k}-" in stem]
    return max(found,key=len) if found else None


def plan_batch(count:int,first_day_utc:datetime,rng:random.Random|None=None,themes:list[str]|None=None,visual_style:str|None=None)->list[dict]:
    """Tria vídeos variats per a publicar un cada dia.

    Sense `themes`, temes diferents cada dia; amb una temàtica (p. ex. Nadal), fons diferents
    d'eixa temàtica. Els formats s'alternen (pomodoro, dormir, llegir, so ambiental).
    """
    rng=rng or random.Random()
    items=[]
    for g in background_library():
        if g["theme"] not in AUTO_THEMES or (themes and g["theme"] not in themes): continue
        for item in g["items"]:
            if visual_style in VISUAL_STYLES and item.get("style")!=visual_style: continue
            env=item.get("environment") if item.get("environment") in ENVIRONMENTS else _guess_environment(item["name"])
            if env: items.append({**item,"theme":g["theme"],"environment":env})
    with SessionLocal() as db:
        recent_rows=db.query(AutoRun.theme,AutoRun.background).order_by(AutoRun.id.desc()).limit(15).all()
    recent_themes={r[0] for r in recent_rows}; recent_bgs={r[1] for r in recent_rows}
    rng.shuffle(items)
    items.sort(key=lambda i:(i["name"] in recent_bgs,i["theme"] in recent_themes))  # primer el que fa temps que no es fa
    distinct_themes=len({i["theme"] for i in items})>=count
    chosen,used=[],set()
    for n in range(count):
        wanted=BATCH_FORMATS[n%len(BATCH_FORMATS)]
        key=(lambda i:i["theme"]) if distinct_themes else (lambda i:i["name"])
        fresh=[i for i in items if key(i) not in used] or items
        pick=next((i for i in fresh if i.get("format")==wanted),None) or (fresh[0] if fresh else None)
        if pick is None: break
        used.add(key(pick))
        fmt=pick.get("format") if pick.get("format") in BATCH_DURATIONS and pick.get("format")==wanted else wanted
        chosen.append({"theme":pick["theme"],"environment":pick["environment"],"format":fmt,"background":pick["name"],
                       "duration_minutes":BATCH_DURATIONS[fmt],"scheduled_for":first_day_utc+timedelta(days=n)})
    return chosen


@app.post("/auto/setmana")
def auto_batch(count:int=Form(7),first_day:str=Form(...),publish_time:str=Form(""),theme:str=Form(""),ambience_level:int=Form(0),music_mode:str=Form("auto"),music_level:int=Form(0),visual_style:str=Form("")):
    """Prepara diversos vídeos d'una vegada: es fan i es pugen seguits i es publica un cada dia."""
    if not 1<=count<=7: raise HTTPException(400,"Han de ser d'1 a 7 vídeos")
    if ambience_level not in AMBIENCE_LEVELS: raise HTTPException(400,"Volum d'ambient no vàlid")
    if music_level not in MUSIC_LEVELS: raise HTTPException(400,"Volum de música no vàlid")
    if music_mode not in {"auto","si","no"}: raise HTTPException(400,"Opció de música no vàlida")
    try: first=from_local(first_day,publish_time or f"{settings.publish_hour:02d}:00",settings.timezone)
    except ValueError: raise HTTPException(400,"Dia o hora no vàlids") from None
    if first<datetime.utcnow(): raise HTTPException(400,"El primer dia ja ha passat")
    chosen_themes=None
    if theme:
        chosen_themes=group_themes(theme) if theme.startswith("grup:") else ([theme] if theme in AUTO_THEMES else None)
        if not chosen_themes: raise HTTPException(400,"Temàtica no vàlida")
    style=visual_style if visual_style in VISUAL_STYLES else None
    plan=plan_batch(count,first,themes=chosen_themes,visual_style=style)
    if not plan: raise HTTPException(409,"No hi ha fons guardats d'eixa temàtica"+(f" d'estil {VISUAL_STYLES[style].lower()}" if style else "")+" per a triar els vídeos")
    ids=[]
    with SessionLocal() as db:
        for p in plan:
            fmt=p["format"]
            advice=music_advice(fmt,p["environment"],p["theme"])
            run=AutoRun(theme=p["theme"],environment=p["environment"],duration_minutes=p["duration_minutes"],focus_minutes=25,break_minutes=5,privacy="public",publish=1,
                        music=(1 if advice.get("recommended") else 0) if music_mode=="auto" else (1 if music_mode=="si" and fmt!="ambient" else 0),
                        music_level=music_level,chime=1 if fmt=="pomodoro" else 0,ambience_level=ambience_level,format=fmt,dim=1 if fmt=="dormir" else 0,
                        motion=1,shorts=3,background=p["background"],delete_after=1,intro=1,scheduled_for=p["scheduled_for"],
                        instagram=1 if instagram_configured() else 0,facebook=1 if facebook_configured() else 0,visual_style=style)
            db.add(run); db.commit(); ids.append(run.id)
    for run_id in ids: autopilot.submit(run_id)
    return RedirectResponse("/",303)


def _taken_slots()->list:
    """Hores ja reservades en el calendari (vídeos programats que no han fallat)."""
    with SessionLocal() as db:
        rows=db.query(AutoRun.scheduled_for).filter(AutoRun.scheduled_for.isnot(None),AutoRun.scheduled_for>=datetime.utcnow()-timedelta(days=1),
                                                    AutoRun.step.notin_(["FAILED","CANCELLED"])).all()
    return [r[0] for r in rows]


def _calendar()->list[dict]:
    now=datetime.utcnow()
    with SessionLocal() as db:
        rows=db.query(AutoRun).filter(AutoRun.scheduled_for.isnot(None),AutoRun.scheduled_for>now,AutoRun.step.notin_(["FAILED","CANCELLED"])).order_by(AutoRun.scheduled_for).all()
        return [{"when":schedule_label(r.scheduled_for,settings.timezone),"theme":r.theme,"ready":r.step=="DONE"} for r in rows]


def _suggestions(available:set[str])->list:
    """Què toca fer ara: temporada, el que fa temps que no es fa i el que més funciona."""
    try:
        with SessionLocal() as db:
            rows=db.query(AutoRun).filter(AutoRun.step=="DONE",AutoRun.video_id.isnot(None)).all()
            history=[(r.theme,r.environment,r.format or "pomodoro",r.published_at or r.created_at,r.video_id) for r in rows if r.format!="short"]
        ids=_published_ids()
        if youtube_connected() and can_manage_playlists():
            refresh_views_in_background(settings.youtube_stats_file,ids,view_counts)
        return build_suggestions(date.today(),history,cached_views(settings.youtube_stats_file),THEMES,available)
    except Exception:
        logging.getLogger(__name__).exception("No s'han pogut preparar els suggeriments")
        return []


@app.get("/",response_class=HTMLResponse)
def auto_home(request:Request,error:str=Query("")):
    try: cleanup_published_videos()
    except Exception: logging.getLogger(__name__).exception("Ha fallat la neteja de vídeos publicats")
    gallery={group["theme"]:[{k:item[k] for k in ("name","url","format","environment","style")} for item in group["items"]] for group in background_library()}
    style_counts={s:sum(1 for items in gallery.values() for i in items if i["style"]==s) for s in VISUAL_STYLES}
    themes=[{"name":t,"backgrounds":len(gallery.get(t,[]))} for t in AUTO_THEMES]
    theme_groups=[{"name":g,"icon":icon,"direct":ts==[g],"backgrounds":sum(len(gallery.get(t,[])) for t in ts),"themes":[{"name":t,"backgrounds":len(gallery.get(t,[]))} for t in ts]} for g,icon,ts in grouped_themes()]
    environments=[{"key":k,"label":e.label} for k,e in environments_by_label()]
    counts={"ambience":len(catalog().ambience),"music":len(catalog().music)}
    tips=_suggestions({t["name"] for t in themes if t["backgrounds"]})
    slot=next_slot(datetime.utcnow(),_taken_slots(),hour=settings.publish_hour,zone=settings.timezone)
    return templates.TemplateResponse(request,"auto.html",{"suggestions":tips,"calendar":_calendar(),"next_slot":schedule_label(slot,settings.timezone),"next_slot_day":local_day(slot,settings.timezone),"publish_hour":f"{settings.publish_hour:02d}:00",
        "themes":themes,"theme_groups":theme_groups,"environments":environments,"durations":DURATION_CHOICES,"pomodoros":list(POMODORO_CHOICES),
        "privacy_choices":PRIVACY_CHOICES,"default_privacy":settings.auto_default_privacy if settings.auto_default_privacy in PRIVACY_CHOICES else "private",
        "youtube_configured":youtube_configured(),"youtube_connected":youtube_connected(),"backgrounds":gallery,
        "counts":counts,"runs":_recent_runs(),"error":error[:300],"music_default":settings.auto_music_default,"levels":AMBIENCE_LEVELS,"music_levels":MUSIC_LEVELS,
        "keep_days":settings.keep_published_days,"breath_patterns":{k:v.label for k,v in BREATH_PATTERNS.items()},"breath_durations":BREATH_DURATIONS,"music_styles":{k:v[0] for k,v in MUSIC_STYLES.items()},"music_counts":_music_counts(),"formats":FORMATS,"noise_colors":{k:v[2] for k,v in NOISE_COLORS.items()},"noise_screens":NOISE_SCREENS,
        "visual_styles":VISUAL_STYLES,"style_counts":style_counts,"instagram_ready":instagram_configured(),"youtube_playlists":has_all_permissions(),"facebook_ready":facebook_configured(),
    })


@app.post("/auto")
def auto_create(theme:str=Form(""),environment:str=Form(""),duration_minutes:int=Form(...),pomodoro:str=Form("25/5"),privacy:str=Form("public"),publish:str=Form(""),music:str=Form(""),music_style:str=Form(""),music_level:int=Form(0),chime:str=Form(""),ambience_level:int=Form(0),ambience_files:str=Form(""),format:str=Form("pomodoro"),noise:str=Form(""),dim:str=Form(""),motion:str=Form(""),breath:str=Form(""),shorts:str=Form(""),background:str=Form(""),shutdown:str=Form(""),delete_after:str=Form(""),noise_screen:str=Form("color"),noise_pulse:str=Form(""),instagram:str=Form(""),facebook:str=Form(""),schedule:str=Form(""),intro:str=Form(""),publish_date:str=Form(""),publish_time:str=Form(""),visual_style:str=Form("")):
    if format not in FORMATS: raise HTTPException(400,"Format no vàlid")
    if format=="soroll":
        # El soroll de color no usa cap tema ni foto: el fons es genera del color del soroll.
        if noise_screen not in NOISE_SCREENS: raise HTTPException(400,"Pantalla no vàlida")
        theme,background,motion=NOISE_THEME,"",""
        if noise_screen=="negre": noise_pulse=""
    else: noise_screen,noise_pulse="",""
    choices=group_themes(theme)
    if choices is not None:
        # «Qualsevol» d'un quadre: un tema a l'atzar, millor si ja té fons.
        if not choices: raise HTTPException(400,"Ambientació no vàlida")
        ready=[t for t in choices if find_backgrounds(settings.assets_dir/"backgrounds",t)]
        theme,background=random.choice(ready or choices),""
    if theme not in AUTO_THEMES and theme!=NOISE_THEME: raise HTTPException(400,"Ambientació no vàlida")
    if format=="soroll":
        if noise not in NOISE_COLORS: raise HTTPException(400,"Color de soroll no vàlid")
        environment,music,ambience_files=NOISE_ENVIRONMENT,"",""
    elif environment not in ENVIRONMENTS: raise HTTPException(400,"Entorn no vàlid")
    else: noise=""
    if format=="ambient":
        if not ENVIRONMENTS[environment].layers and not ENVIRONMENTS[environment].noise: raise HTTPException(400,"El so ambiental necessita un entorn amb sons")
        music,music_style="",""
    if format!="pomodoro": chime=""
    if format not in {"dormir","soroll"}: dim=""
    if background and background not in {p.name for p in find_backgrounds(settings.assets_dir/"backgrounds",theme)}: raise HTTPException(400,"Fons no vàlid")
    if format=="short":
        if not ENVIRONMENTS[environment].layers and not ENVIRONMENTS[environment].noise and not ENVIRONMENTS[environment].music: raise HTTPException(400,"Entorn no vàlid")
        breath,shorts,duration_minutes="", "", 1
    elif format=="respiracio":
        if breath not in BREATH_PATTERNS: raise HTTPException(400,"Respiració no vàlida")
        if duration_minutes not in BREATH_DURATIONS: raise HTTPException(400,"Duració no vàlida")
    else:
        breath=""
        if duration_minutes not in DURATION_CHOICES: raise HTTPException(400,"Duració no vàlida")
    if pomodoro not in POMODORO_CHOICES: raise HTTPException(400,"Pomodoro no vàlid")
    if privacy not in PRIVACY_CHOICES: raise HTTPException(400,"Privacitat no vàlida")
    if ambience_level not in AMBIENCE_LEVELS: raise HTTPException(400,"Volum d'ambient no vàlid")
    if music_level not in MUSIC_LEVELS: raise HTTPException(400,"Volum de música no vàlid")
    if music_style and music_style not in MUSIC_STYLES: raise HTTPException(400,"Estil de música no vàlid")
    files=[n for n in ambience_files.split(",") if n and Path(n).name==n and len(n)<=120][:4]
    shorts_count=int(shorts) if shorts in {"1","3"} and publish else 0
    scheduled_for=_scheduled_for(schedule,publish_date,publish_time) if publish and privacy=="public" else None
    focus,pause=POMODORO_CHOICES[pomodoro]
    with SessionLocal() as db:
        run=AutoRun(theme=theme,environment=environment,duration_minutes=duration_minutes,focus_minutes=focus,break_minutes=pause,privacy=privacy,publish=1 if publish else 0,music=1 if music else 0,music_style=music_style or None,music_level=music_level,chime=1 if chime else 0,ambience_level=ambience_level,ambience_files=",".join(files) or None,format=format,noise=noise or None,dim=1 if dim else 0,motion=1 if motion else 0,breath=breath or None,shorts=shorts_count,background=background or None,shutdown=1 if shutdown else 0,delete_after=1 if delete_after else 0,noise_screen=noise_screen or None,noise_pulse=1 if noise_pulse else 0,scheduled_for=scheduled_for,reels_json=_skip_reels(instagram,facebook,publish),intro=1 if intro and format not in {"respiracio","short"} else 0,visual_style=visual_style if visual_style in VISUAL_STYLES else None,
                 instagram=1 if instagram and publish and (shorts_count or format=="short") and instagram_configured() else 0,
                 facebook=1 if facebook and publish and (shorts_count or format=="short") and facebook_configured() else 0)
        db.add(run); db.commit(); run_id=run.id
    autopilot.submit(run_id)
    return RedirectResponse("/",303)


_last_reel_check=0.0


@app.get("/api/auto")
def auto_status():
    global _last_reel_check
    if time.monotonic()-_last_reel_check>600:  # com a molt cada 10 minuts
        _last_reel_check=time.monotonic()
        try: autopilot.submit_pending_reels()
        except Exception: logging.getLogger(__name__).exception("No s'han pogut revisar els reels pendents")
    return {"runs":_recent_runs(),"youtube_connected":youtube_connected(),"shutdown":power.status()}


def _advice_theme(theme:str)->str:
    """Per a la recomanació i la mostra, un grup es tracta com el seu primer tema."""
    choices=group_themes(theme)
    return choices[0] if choices else theme


@app.get("/api/auto/music-advice")
def auto_music_advice(format:str=Query("pomodoro"),environment:str=Query(""),theme:str=Query("")):
    if format not in FORMATS: raise HTTPException(400,"Format no vàlid")
    return music_advice(format,environment,_advice_theme(theme))


@app.post("/auto/{run_id}/short")
def auto_short(run_id:int):
    with SessionLocal() as db:
        run=db.get(AutoRun,run_id)
        if not run or not short_missing(run): raise HTTPException(409,"Este vídeo ja té Short o no se'n pot fer")
    autopilot.submit_short(run_id)
    return RedirectResponse("/",303)


@app.post("/auto/{run_id}/reel")
def auto_reel(run_id:int):
    with SessionLocal() as db:
        run=db.get(AutoRun,run_id)
        if not run or not reel_missing(run): raise HTTPException(409,"Este vídeo ja té reel o no se'n pot fer")
    autopilot.submit_reel(run_id)
    return RedirectResponse("/",303)


@app.post("/auto/{run_id}/cancel")
def auto_cancel(run_id:int):
    if not autopilot.cancel(run_id): raise HTTPException(409,"Este vídeo ja no es pot cancel·lar")
    return {"cancelled":True}


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


@app.post("/youtube/reconnect")
def youtube_reconnect():
    """Torna a autoritzar el canal amb el permís de llistes de reproducció."""
    try: reconnect_youtube()
    except Exception as exc: return RedirectResponse("/?error="+quote(f"No s'ha pogut connectar YouTube: {exc}"),303)
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
def auto_preview(theme:str=Form(""),environment:str=Form(""),ambience_level:int=Form(0),music_level:int=Form(0),music:str=Form(""),music_style:str=Form(""),chime:str=Form(""),ambience_files:str=Form(""),format:str=Form("pomodoro"),noise:str=Form(""),music_file:str=Form("")):
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
        if env.noise: noise_color=env.noise
    if env is not None and env.music and format!="ambient" and (music or not env.layers):
        names=load_catalog(settings.audio_catalog)
        style=music_style if music_style in MUSIC_STYLES else music_style_for(format,environment,_advice_theme(theme))
        tracks=music_tracks(settings.assets_dir/"music",style,names) or music_tracks(settings.assets_dir/"music","calma",names)
        # En canviar només un volum es manté la mateixa peça, per a poder comparar.
        same=[t for t in tracks if t.name==music_file]
        if same or tracks: track=same[0] if same else rng.choice(tracks)
    folder=_preview_dir()
    for old in sorted(folder.glob("preview-*.mp3"),key=lambda p:p.stat().st_mtime)[:-5]: old.unlink(missing_ok=True)
    output=folder/f"preview-{uuid4().hex}.mp3"
    try: command=build_preview_command(layers,track,bool(chime),output,noise=noise_color,noise_loudness=(NOISE_LOUDNESS if format=="soroll" else PRIMARY_AMBIENCE_LOUDNESS)+ambience_level,music_level=music_level if music_level in MUSIC_LEVELS else 0,music_start=_music_start(track))
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    result=subprocess.run(command,capture_output=True,text=True,timeout=120,check=False)
    if result.returncode!=0 or not output.is_file(): raise HTTPException(500,"No s'ha pogut preparar la mostra: "+(result.stderr or "")[-300:])
    names=load_catalog(settings.audio_catalog)
    sounds=([f"Soroll {NOISE_COLORS[noise][2].lower()}" if noise in NOISE_COLORS else "Brunzit de cabina"] if noise_color else [])+[(names.get(l.path.name) or {}).get("title") or l.path.stem for l in layers]+([f"Música: {(names.get(track.name) or {}).get('title') or track.stem}"] if track else [])
    return {"url":f"/api/auto/preview/{output.name}","files":[l.path.name for l in layers],"sounds":sounds,"music":track.name if track else None}


def _music_start(track:Path|None)->int:
    """La mostra agafa la música de dins de la peça (no de l'entrada, que sol ser molt fluixa)."""
    if track is None: return 0
    try:
        out=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(track)],capture_output=True,text=True,timeout=20,check=False).stdout
        return int(min(90,max(0,float(out)*0.2)))
    except (ValueError,OSError,subprocess.SubprocessError): return 0


@app.get("/api/auto/preview/{name}")
def auto_preview_file(name:str):
    if not PREVIEW_NAME.fullmatch(name): raise HTTPException(404,"Mostra no disponible")
    path=_preview_dir()/name
    if not path.is_file(): raise HTTPException(404,"Mostra no disponible")
    return FileResponse(path,media_type="audio/mpeg",headers={"Cache-Control":"no-store"})
