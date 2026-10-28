"""Importació segura i registre de procedència de fons originals."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

@dataclass(frozen=True)
class AssetProvenance:
    prompt: str
    negative_prompt: str = ""
    provider: str = "manual"
    model: str = ""
    license: str = ""
    source_notes: str = ""


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
    if target.exists():
        raise ValueError("Ja existeix un fons amb este nom")
    shutil.copy2(source, target)
    metadata = target.with_suffix(target.suffix + ".json")
    payload = asdict(provenance) | {
        "asset": target.name,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target, metadata
