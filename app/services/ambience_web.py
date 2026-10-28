"""Project-scoped staging: only explicit acceptance creates an asset."""
from dataclasses import asdict
import json
from pathlib import Path
import re
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict

from app.config import settings
from app.database import SessionLocal
from app.models import Project
from app.services.ambience_prompt import AmbiencePromptSpec, build_prompt
from app.services.ambience_assets import AssetProvenance, import_background
from app.services.image_providers import generate_image, provider_names

router = APIRouter(prefix="/api/projects/{project_id}/ambience")
_accept_lock = Lock()


class Generation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(max_length=80)
    spec: dict[str, str] = Field(max_length=12)
    width: int = Field(default=1344, ge=256, le=2048)
    height: int = Field(default=768, ge=256, le=2048)
    steps: int = Field(default=28, ge=1, le=100)
    cfg_scale: float = Field(default=6.5, ge=1, le=30)


class Acceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    license: str = Field(default="", max_length=1000)
    source_notes: str = Field(default="", max_length=2000)


def project_exists(project_id):
    with SessionLocal() as db:
        if not db.get(Project, project_id):
            raise HTTPException(404, "Projecte no trobat")


def same_origin(request):
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin.rstrip("/") != str(request.base_url).rstrip("/")):
        raise HTTPException(403, "Origen no admés")


def staged(project_id, token):
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        raise HTTPException(404, "Previsualització no disponible")
    root = settings.image_generation_dir.resolve()
    record = root / f"preview-{token}.json"
    try:
        if record.is_symlink():
            raise ValueError()
        data = json.loads(record.read_text())
        path = root / data["file"]
        if data["project_id"] != project_id or path.is_symlink() or path.resolve().parent != root or not path.is_file():
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(404, "Previsualització no disponible") from None
    return record, path, data


@router.get("/providers")
def providers(project_id: int):
    project_exists(project_id)
    return {"providers": provider_names()}


@router.post("/generate", status_code=201)
def generate(project_id: int, body: Generation, request: Request):
    same_origin(request)
    project_exists(project_id)
    try:
        if any(len(v) > 240 for v in body.spec.values()):
            raise ValueError("Els camps del prompt admeten fins a 240 caràcters")
        prompt = build_prompt(AmbiencePromptSpec(**body.spec))
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from None
    try:
        result = generate_image(body.provider, prompt, width=body.width, height=body.height, steps=body.steps, cfg_scale=body.cfg_scale)
    except ValueError:
        raise HTTPException(400, "Proveïdor o paràmetres no vàlids") from None
    except Exception:
        raise HTTPException(502, "No s'ha pogut generar la imatge. Comprova la connexió A1111/Forge, el model i la memòria GPU; pots continuar en mode manual.") from None
    root = settings.image_generation_dir.resolve()
    path = result.path
    if path.is_symlink() or path.resolve().parent != root or not path.is_file():
        raise HTTPException(502, "El proveïdor ha retornat un resultat no vàlid")
    token = uuid4().hex
    data = {"project_id": project_id, "file": path.name, "provenance": asdict(AssetProvenance(prompt=prompt.positive, negative_prompt=prompt.negative, provider=result.provider, model=result.model, source_notes=result.notes)), "generation": {"width": body.width, "height": body.height, "steps": body.steps, "cfg_scale": body.cfg_scale}}
    with (root / f"preview-{token}.json").open("x") as f:
        json.dump(data, f)
    return {"id": token, "preview_url": f"/api/projects/{project_id}/ambience/{token}/preview"}


@router.get("/{token}/preview")
def preview(project_id: int, token: str):
    project_exists(project_id)
    _, path, _ = staged(project_id, token)
    return FileResponse(path, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/{token}/accept", status_code=201)
def accept(project_id: int, token: str, body: Acceptance, request: Request):
    same_origin(request)
    project_exists(project_id)
    with _accept_lock:
        record, path, data = staged(project_id, token)
        provenance = data["provenance"]
        provenance["license"] = body.license
        provenance["source_notes"] += "\n" + body.source_notes
        provenance["generation"] = data["generation"]
        try:
            image, _ = import_background(path, settings.assets_dir / "backgrounds", body.name, AssetProvenance(**provenance))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        record.unlink()
        path.unlink(missing_ok=True)
    return {"asset": image.name}


@router.delete("/{token}", status_code=204)
def discard(project_id: int, token: str, request: Request):
    same_origin(request)
    project_exists(project_id)
    with _accept_lock:
        record, path, _ = staged(project_id, token)
        record.unlink()
        path.unlink(missing_ok=True)
