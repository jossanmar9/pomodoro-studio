"""Biblioteca de fons: importar imatges, veure-les i eliminar-les.

- Els fons guardats van a assets/backgrounds/ amb el nom del tema i un fitxer
  .json amb la seua procedència (prompt, model o origen i llicència).
- El mode automàtic usa el fons triat a mà o un dels guardats a l'atzar.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile

from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.services.ambience_assets import ALLOWED_IMAGE_EXTENSIONS, AssetProvenance, import_background
from app.services.autopilot_plan import AUTO_THEMES, ENVIRONMENTS, FORMATS, NOISE_ENVIRONMENT, find_backgrounds, slugify

MIN_WIDTH, MIN_HEIGHT = 1920, 1080
# Llicències acceptades en afegir una imatge.
IMPORT_LICENSES = {
    "chatgpt": "Generat amb ChatGPT (OpenAI)",
    "pexels": "Pexels License",
    "unsplash": "Unsplash License",
    "pixabay": "Pixabay Content License",
    "domini-public": "Public domain / CC0",
    "propia": "Own work",
}


def library_dir() -> Path:
    return settings.assets_dir / "backgrounds"


# --- Biblioteca -------------------------------------------------------------------

def library() -> list[dict]:
    """Fons guardats agrupats per tema, en l'ordre de la pàgina."""
    groups = []
    for theme in AUTO_THEMES:
        items = []
        for path in find_backgrounds(library_dir(), theme):
            if path.suffix.casefold() not in ALLOWED_IMAGE_EXTENSIONS:
                continue
            meta = {}
            sidecar = path.with_suffix(path.suffix + ".json")
            if sidecar.is_file():
                try:
                    meta = json.loads(sidecar.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    meta = {}
            generation = meta.get("generation") if isinstance(meta.get("generation"), dict) else {}
            items.append({
                "name": path.name, "url": f"/assets/backgrounds/{path.name}", "license": meta.get("license", ""),
                "model": meta.get("model", ""), "source": meta.get("source_notes", "")[:200],
                "format": generation.get("format") or "", "environment": generation.get("environment") or "",
            })
        groups.append({"theme": theme, "items": items})
    return groups


def delete_background(name: str) -> None:
    if not name or Path(name).name != name:
        raise ValueError("Fons no trobat")
    root = library_dir().resolve()
    path = (root / name).resolve()
    if path.parent != root or path.suffix.casefold() not in ALLOWED_IMAGE_EXTENSIONS or not path.is_file():
        raise ValueError("Fons no trobat")
    path.unlink()
    path.with_suffix(path.suffix + ".json").unlink(missing_ok=True)


# Llicències que no necessiten enllaç d'origen.
NO_SOURCE_LICENSES = {"chatgpt", "propia"}


def import_uploaded(data: bytes, original_name: str, theme: str, license_key: str, source_url: str, author: str, fmt: str = "", environment: str = "") -> Path:
    """Guarda una imatge (feta per tu o lliure) amb el seu origen i, si es diu, el format i l'entorn per als quals és."""
    if theme not in AUTO_THEMES:
        raise ValueError("Ambientació no vàlida")
    if fmt and fmt not in FORMATS:
        raise ValueError("Format no vàlid")
    if environment and environment != NOISE_ENVIRONMENT and environment not in ENVIRONMENTS:
        raise ValueError("Entorn no vàlid")
    if license_key not in IMPORT_LICENSES:
        raise ValueError("Tria la llicència de la imatge")
    if license_key not in NO_SOURCE_LICENSES and not source_url.strip().startswith(("https://", "http://")):
        raise ValueError("Indica l'enllaç d'on has tret la imatge")
    if len(data) > 40 * 1024 * 1024:
        raise ValueError("La imatge pesa massa (màxim 40 MB)")
    suffix = Path(original_name).suffix.casefold()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Format no admés: usa JPG, PNG o WebP")
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"upload{suffix}"
        source.write_bytes(data)
        try:
            with Image.open(source) as image:
                image.verify()
            with Image.open(source) as image:
                width, height = image.size
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
            raise ValueError("El fitxer no és una imatge vàlida") from None
        if width < height:
            raise ValueError("La imatge ha de ser horitzontal")
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            raise ValueError(f"La imatge és massa xicoteta ({width}×{height}); cal com a mínim {MIN_WIDTH}×{MIN_HEIGHT}")
        provenance = AssetProvenance(
            prompt="", provider="import", model="",
            license=IMPORT_LICENSES[license_key],
            source_notes=" · ".join(part for part in (source_url.strip()[:500], f"Author: {author.strip()[:120]}" if author.strip() else "") if part),
            generation={"original_name": Path(original_name).name[:120], "width": width, "height": height, "format": fmt or None, "environment": environment or None},
        )
        parts = [slugify(theme), environment, fmt] if environment or fmt else [slugify(theme), "importat"]
        name = "-".join(part for part in parts if part) + f"-{datetime.now():%Y%m%d-%H%M%S}"
        target, _ = import_background(source, library_dir(), name, provenance)
    return target

