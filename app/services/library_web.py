"""Pàgina i API de la Biblioteca de fons."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services import background_library as lib
from app.services.autopilot_plan import AUTO_THEMES, ENVIRONMENTS, FORMATS

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin.rstrip("/") != str(request.base_url).rstrip("/")):
        raise HTTPException(403, "Origen no admés")


@router.get("/fons", response_class=HTMLResponse)
def library_page(request: Request, error: str = "", ok: str = ""):
    return templates.TemplateResponse(request, "fons.html", {
        "themes": AUTO_THEMES,
        "licenses": lib.IMPORT_LICENSES,
        "environments": {key: env.label for key, env in ENVIRONMENTS.items()},
        "formats": FORMATS,
        "library": lib.library(),
        "error": error[:300],
        "ok": ok[:300],
    })


@router.post("/fons/{name}/eliminar")
def delete(name: str, request: Request):
    _same_origin(request)
    try:
        lib.delete_background(name)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    return RedirectResponse("/fons#biblioteca", 303)


@router.post("/fons/importar")
async def import_image(request: Request, image: UploadFile = File(...), theme: str = Form(...), license: str = Form(...), source_url: str = Form(""), author: str = Form(""), format: str = Form(""), environment: str = Form("")):
    _same_origin(request)
    data = await image.read(40 * 1024 * 1024 + 1)
    try:
        path = lib.import_uploaded(data, image.filename or "", theme, license, source_url, author, format, environment)
    except ValueError as exc:
        return RedirectResponse("/fons?error=" + _quote(str(exc)) + "#importar", 303)
    return RedirectResponse("/fons?ok=" + _quote(f"Imatge guardada com {path.name}") + "#biblioteca", 303)


def _quote(text: str) -> str:
    from urllib.parse import quote
    return quote(text)
