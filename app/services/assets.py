"""Descobriment de recursos locals autoritzats."""
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.services.renderer import SUPPORTED_AUDIO_SUFFIXES, SUPPORTED_IMAGE_SUFFIXES, SUPPORTED_VIDEO_SUFFIXES


@dataclass(frozen=True)
class AssetCatalog:
    backgrounds: list[str]
    ambience: list[str]
    music: list[str]


def _files(folder: Path, suffixes: set[str]) -> list[str]:
    if not folder.exists():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in suffixes)


def catalog() -> AssetCatalog:
    root = settings.assets_dir
    return AssetCatalog(
        _files(root / "backgrounds", SUPPORTED_IMAGE_SUFFIXES | SUPPORTED_VIDEO_SUFFIXES),
        _files(root / "ambience", SUPPORTED_AUDIO_SUFFIXES),
        _files(root / "music", SUPPORTED_AUDIO_SUFFIXES),
    )


def resolve_asset(kind: str, name: str) -> Path:
    suffixes_by_kind = {
        "backgrounds": SUPPORTED_IMAGE_SUFFIXES | SUPPORTED_VIDEO_SUFFIXES,
        "ambience": SUPPORTED_AUDIO_SUFFIXES,
        "music": SUPPORTED_AUDIO_SUFFIXES,
    }
    if kind not in suffixes_by_kind:
        raise ValueError("Tipus de recurs no vàlid")
    if not name or Path(name).name != name:
        raise ValueError("Nom de recurs no vàlid")

    root = (settings.assets_dir / kind).resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file() or path.suffix.lower() not in suffixes_by_kind[kind]:
        raise ValueError("Recurs no trobat")
    return path
