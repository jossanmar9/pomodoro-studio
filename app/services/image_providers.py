"""Interfície desacoblada per a generadors d'imatges opcionals."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.services.ambience_prompt import AmbiencePrompt

@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: AmbiencePrompt
    width: int = 1920
    height: int = 1080
    output_dir: Path | None = None

@dataclass(frozen=True)
class GeneratedImage:
    path: Path
    provider: str
    model: str = ""
    notes: str = ""

class ImageProvider(Protocol):
    name: str

    def available(self) -> bool: ...
    def generate(self, request: ImageGenerationRequest) -> GeneratedImage: ...

class ManualImageProvider:
    """Mode explícit sense IA: el prompt es copia i la imatge s'importa després."""
    name = "manual"

    def available(self) -> bool:
        return True

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        raise RuntimeError("El mode manual no genera imatges; usa el prompt en l'eina que preferisques i importa el resultat")

_PROVIDERS: dict[str, ImageProvider] = {"manual": ManualImageProvider()}


def register_provider(provider: ImageProvider) -> None:
    name = provider.name.strip().casefold()
    if not name or name == "manual":
        raise ValueError("Nom de proveïdor reservat o no vàlid")
    _PROVIDERS[name] = provider


def provider_names() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


def available_providers() -> tuple[str, ...]:
    return tuple(name for name in provider_names() if _PROVIDERS[name].available())


def get_provider(name: str) -> ImageProvider:
    key = name.strip().casefold()
    if key not in _PROVIDERS:
        raise ValueError("Proveïdor d'imatges no configurat")
    return _PROVIDERS[key]
