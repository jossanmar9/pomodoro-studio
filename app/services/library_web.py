"""Pàgina i API de la Biblioteca de fons."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services import background_library as lib
from app.services.autopilot_plan import AUTO_THEMES, ENVIRONMENTS, FORMATS
from app.services.image_providers import MODEL_PROFILES, forge_profile

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin.rstrip("/") != str(request.base_url).rstrip("/")):
        raise HTTPException(403, "Origen no admés")


def _status() -> dict:
    ready = lib.forge_ready()
    profile = forge_profile() if ready else None
    return {
        "forge_ready": ready,
        "profile": profile.label if profile else None,
        "is_flux": bool(profile and profile.name.startswith("flux")),
        "jobs": [vars(job) for job in lib.candidate_generator.jobs.values()][-5:],
        "candidates": lib.list_candidates(),
    }


@router.get("/fons", response_class=HTMLResponse)
def library_page(request: Request, error: str = "", ok: str = ""):
    return templates.TemplateResponse(request, "fons.html", {
        "themes": AUTO_THEMES,
        "environments": [{"key": key, "label": env.label} for key, env in ENVIRONMENTS.items()],
        "formats": FORMATS,
        "licenses": lib.IMPORT_LICENSES,
        "library": lib.library(),
        "status": _status(),
        "profiles": MODEL_PROFILES,
        "error": error[:300],
        "ok": ok[:300],
    })


@router.get("/api/fons")
def library_status():
    return _status()


@router.post("/api/fons/generar", status_code=202)
def generate(request: Request, theme: str = Form(...), environment: str = Form(...), format: str = Form("pomodoro"), count: int = Form(4)):
    _same_origin(request)
    if not lib.forge_ready():
        raise HTTPException(409, "Forge no està obert")
    try:
        job = lib.candidate_generator.submit(theme, environment, format, count)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"job": job.id}


@router.get("/api/fons/opcions/{candidate_id}/imatge")
def candidate_image(candidate_id: str):
    try:
        path = lib.candidate_image(candidate_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    return FileResponse(path, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/api/fons/opcions/{candidate_id}/guardar", status_code=201)
def approve(candidate_id: str, request: Request):
    _same_origin(request)
    try:
        path = lib.approve_candidate(candidate_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    return {"name": path.name}


@router.post("/api/fons/opcions/{candidate_id}/descartar", status_code=204)
def discard(candidate_id: str, request: Request):
    _same_origin(request)
    try:
        lib.discard_candidate(candidate_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


@router.post("/fons/{name}/eliminar")
def delete(name: str, request: Request):
    _same_origin(request)
    try:
        lib.delete_background(name)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    return RedirectResponse("/fons#biblioteca", 303)


@router.post("/fons/importar")
async def import_image(request: Request, image: UploadFile = File(...), theme: str = Form(...), license: str = Form(...), source_url: str = Form(""), author: str = Form("")):
    _same_origin(request)
    data = await image.read(40 * 1024 * 1024 + 1)
    try:
        path = lib.import_uploaded(data, image.filename or "", theme, license, source_url, author)
    except ValueError as exc:
        return RedirectResponse("/fons?error=" + _quote(str(exc)) + "#importar", 303)
    return RedirectResponse("/fons?ok=" + _quote(f"Imatge guardada com {path.name}") + "#biblioteca", 303)


def _quote(text: str) -> str:
    from urllib.parse import quote
    return quote(text)
