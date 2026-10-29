"""Biblioteca de fons: generar opcions amb Forge, revisar-les i guardar les bones.

- Les opcions generades esperen en data/generated-images/candidates/ fins que
  les guardes o les descartes.
- Els fons guardats van a assets/backgrounds/ amb el nom del tema i un fitxer
  .json amb la seua procedència (prompt, model o origen i llicència).
- El mode automàtic només tria entre els fons guardats.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import shutil
import tempfile
import threading
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.services.ambience_assets import ALLOWED_IMAGE_EXTENSIONS, AssetProvenance, import_background
from app.services.ambience_prompt import build_scene_prompt
from app.services.autopilot_plan import AUTO_THEMES, ENVIRONMENTS, FORMATS, NOISE_ENVIRONMENT, find_backgrounds, prompt_spec, slugify
from app.services.image_providers import available_providers, forge_profile, generate_image

logger = logging.getLogger(__name__)
CANDIDATE_ID = re.compile(r"^[a-f0-9]{32}$")
MIN_WIDTH, MIN_HEIGHT = 1920, 1080
MAX_CANDIDATES_PER_REQUEST = 6
# Llicències acceptades en importar una imatge que no has generat tu.
IMPORT_LICENSES = {
    "pexels": "Pexels License",
    "unsplash": "Unsplash License",
    "pixabay": "Pixabay Content License",
    "domini-public": "Public domain / CC0",
    "propia": "Own work",
}


def library_dir() -> Path:
    return settings.assets_dir / "backgrounds"


def candidates_dir() -> Path:
    return settings.image_generation_dir / "candidates"


def forge_ready() -> bool:
    return "a1111" in available_providers()


# --- Generació ----------------------------------------------------------------

def generate_one(theme: str, environment: str, fmt: str, output_dir: Path) -> tuple[Path, dict]:
    """Genera una imatge amb Forge amb el perfil del model carregat. Retorna (fitxer, procedència)."""
    prompt = build_scene_prompt(prompt_spec(theme, environment, fmt))
    profile = forge_profile()
    try:
        result = generate_image("a1111", prompt, hires_scale=settings.auto_hires_scale, profile=profile)
        hires = settings.auto_hires_scale
    except Exception:
        if settings.auto_hires_scale <= 1:
            raise
        logger.warning("Forge ha fallat en ampliar la imatge; es reintenta sense ampliar", exc_info=True)
        result = generate_image("a1111", prompt, profile=profile)
        hires = 1.0
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / result.path.name
    shutil.move(str(result.path), target)
    provenance = {
        "prompt": prompt.positive,
        "negative_prompt": prompt.negative if (profile is None or profile.uses_negative) else "",
        "provider": result.provider,
        "model": result.model,
        "license": "Generat localment amb Forge",
        "source_notes": result.notes,
        "generation": {"profile": profile.name if profile else "", "hires_scale": hires},
    }
    return target, provenance


@dataclass
class GenerationJob:
    id: str
    theme: str
    environment: str
    fmt: str
    total: int
    done: int = 0
    error: str | None = None
    finished: bool = False
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CandidateGenerator:
    """Genera opcions d'una en una en segon pla (Forge només pot fer-ne una alhora)."""

    def __init__(self) -> None:
        self.jobs: dict[str, GenerationJob] = {}
        self._queue: list[GenerationJob] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def submit(self, theme: str, environment: str, fmt: str, count: int) -> GenerationJob:
        validate_choice(theme, environment, fmt)
        if not 1 <= count <= MAX_CANDIDATES_PER_REQUEST:
            raise ValueError(f"Es poden generar entre 1 i {MAX_CANDIDATES_PER_REQUEST} opcions")
        job = GenerationJob(uuid4().hex, theme, environment, fmt, count)
        with self._lock:
            self.jobs[job.id] = job
            self._queue.append(job)
            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._loop, daemon=True)
                self._worker.start()
        return job

    def active(self) -> list[GenerationJob]:
        return [job for job in self.jobs.values() if not job.finished]

    def _loop(self) -> None:
        while True:
            with self._lock:
                if not self._queue:
                    return
                job = self._queue.pop(0)
            self._run(job)

    def _run(self, job: GenerationJob) -> None:
        try:
            for _ in range(job.total):
                path, provenance = generate_one(job.theme, job.environment, job.fmt, candidates_dir())
                save_candidate(path, job.theme, job.environment, job.fmt, provenance)
                job.done += 1
        except Exception as exc:
            logger.exception("Ha fallat la generació d'opcions de fons")
            job.error = f"Forge ha fallat: {exc}"[:500]
        finally:
            job.finished = True


def validate_choice(theme: str, environment: str, fmt: str) -> None:
    if theme not in AUTO_THEMES:
        raise ValueError("Ambientació no vàlida")
    if environment != NOISE_ENVIRONMENT and environment not in ENVIRONMENTS:
        raise ValueError("Entorn no vàlid")
    if fmt not in FORMATS:
        raise ValueError("Format no vàlid")


# --- Opcions per revisar --------------------------------------------------------

def save_candidate(path: Path, theme: str, environment: str, fmt: str, provenance: dict) -> str:
    candidate_id = uuid4().hex
    record = {
        "id": candidate_id, "file": path.name, "theme": theme, "environment": environment, "format": fmt,
        "created_at": datetime.now(timezone.utc).isoformat(), "provenance": provenance,
    }
    (path.parent / f"candidate-{candidate_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return candidate_id


def _candidate(candidate_id: str) -> tuple[Path, Path, dict]:
    if not CANDIDATE_ID.fullmatch(candidate_id):
        raise ValueError("Opció no trobada")
    root = candidates_dir().resolve()
    record_path = root / f"candidate-{candidate_id}.json"
    try:
        if record_path.is_symlink():
            raise ValueError
        record = json.loads(record_path.read_text(encoding="utf-8"))
        image = (root / record["file"]).resolve()
        if image.parent != root or image.is_symlink() or not image.is_file():
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("Opció no trobada") from None
    return record_path, image, record


def list_candidates() -> list[dict]:
    root = candidates_dir()
    if not root.is_dir():
        return []
    items = []
    for record_path in root.glob("candidate-*.json"):
        try:
            _, _, record = _candidate(record_path.stem.removeprefix("candidate-"))
        except ValueError:
            continue
        items.append({key: record[key] for key in ("id", "theme", "environment", "format", "created_at")} | {
            "model": record.get("provenance", {}).get("model", ""),
            "image_url": f"/api/fons/opcions/{record['id']}/imatge",
        })
    return sorted(items, key=lambda item: item["created_at"], reverse=True)


def candidate_image(candidate_id: str) -> Path:
    return _candidate(candidate_id)[1]


def approve_candidate(candidate_id: str) -> Path:
    record_path, image, record = _candidate(candidate_id)
    data = record["provenance"]
    name = f"{slugify(record['theme'])}-{record['environment']}-{datetime.now():%Y%m%d-%H%M%S}-{candidate_id[:4]}"
    target, _ = import_background(image, library_dir(), name, AssetProvenance(**data))
    image.unlink(missing_ok=True)
    record_path.unlink(missing_ok=True)
    return target


def discard_candidate(candidate_id: str) -> None:
    record_path, image, _ = _candidate(candidate_id)
    image.unlink(missing_ok=True)
    record_path.unlink(missing_ok=True)


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
            items.append({"name": path.name, "url": f"/assets/backgrounds/{path.name}", "license": meta.get("license", ""), "model": meta.get("model", ""), "source": meta.get("source_notes", "")[:200]})
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


def import_uploaded(data: bytes, original_name: str, theme: str, license_key: str, source_url: str, author: str) -> Path:
    """Guarda una imatge lliure (Pexels, Unsplash, domini públic…) amb el seu origen."""
    if theme not in AUTO_THEMES:
        raise ValueError("Ambientació no vàlida")
    if license_key not in IMPORT_LICENSES:
        raise ValueError("Tria la llicència de la imatge")
    if license_key != "propia" and not source_url.strip().startswith(("https://", "http://")):
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
            generation={"original_name": Path(original_name).name[:120], "width": width, "height": height},
        )
        name = f"{slugify(theme)}-importat-{datetime.now():%Y%m%d-%H%M%S}"
        target, _ = import_background(source, library_dir(), name, provenance)
    return target


candidate_generator = CandidateGenerator()
