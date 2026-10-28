"""Importació segura i registre de procedència de fons originals."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import os

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

@dataclass(frozen=True)
class AssetProvenance:
    prompt: str
    negative_prompt: str = ""
    provider: str = "manual"
    model: str = ""
    license: str = ""
    source_notes: str = ""
    generation: dict = field(default_factory=dict)


def safe_asset_name(name: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    if not stem:
        raise ValueError("El nom del recurs no és vàlid")
    return stem[:80]


def import_background(source: Path, assets_dir: Path, name: str, provenance: AssetProvenance) -> tuple[Path, Path]:
    source = source.resolve()
    if not source.is_file():
        raise ValueError("La imatge d'origen no existeix")
    suffix = source.suffix.casefold()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Format d'imatge no admés")
    assets_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_asset_name(name)
    target = (assets_dir / f"{stem}{suffix}").resolve()
    if target.parent != assets_dir.resolve():
        raise ValueError("Destinació no vàlida")
    metadata = target.with_suffix(target.suffix + ".json")
    payload = asdict(provenance) | {
        "asset": target.name,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    created = []
    try:
        for path in (metadata, target):
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                raise ValueError("Ja existeix un fons o metadades amb este nom") from None
            created.append(path)
            with os.fdopen(fd, "wb") as output:
                if path == metadata:
                    output.write((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode())
                else:
                    with source.open("rb") as input_file:
                        shutil.copyfileobj(input_file, output)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return target, metadata
