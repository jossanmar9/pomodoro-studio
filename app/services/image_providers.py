"""Interfície desacoblada per a generadors d'imatges opcionals."""
import base64
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx

from app.config import settings
from app.services.ambience_prompt import AmbiencePrompt


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: AmbiencePrompt
    width: int = 1920
    height: int = 1080
    output_dir: Path | None = None
    steps: int = 28
    cfg_scale: float = 6.5


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
    name = "manual"
    def available(self) -> bool: return True
    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        raise RuntimeError("El mode manual no genera imatges; usa el prompt en l'eina que preferisques i importa el resultat")


class A1111ImageProvider:
    """Connector local compatible amb AUTOMATIC1111 i Forge via /sdapi/v1."""
    name = "a1111"

    def __init__(self, base_url: str, model: str = "", timeout: float = 180.0):
        self.base_url = base_url.rstrip("/"); self.model = model.strip(); self.timeout = timeout

    def available(self) -> bool:
        if not self.base_url: return False
        try:
            response = httpx.get(f"{self.base_url}/sdapi/v1/options", timeout=2.0)
            return response.status_code < 400
        except httpx.HTTPError:
            return False

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        if not self.base_url: raise RuntimeError("El proveïdor A1111/Forge no està configurat")
        if request.output_dir is None: raise ValueError("Cal indicar una carpeta d'eixida per a la imatge generada")
        if not 256 <= request.width <= 2048 or not 256 <= request.height <= 2048: raise ValueError("La mida de generació ha d'estar entre 256 i 2048 píxels")
        if not 1 <= request.steps <= 100 or not 1 <= request.cfg_scale <= 30: raise ValueError("Paràmetres de generació fora dels límits admesos")
        request.output_dir.mkdir(parents=True, exist_ok=True)
        payload = {"prompt": request.prompt.positive, "negative_prompt": request.prompt.negative, "width": request.width, "height": request.height, "steps": request.steps, "cfg_scale": request.cfg_scale, "batch_size": 1, "n_iter": 1}
        if self.model:
            payload["override_settings"] = {"sd_model_checkpoint": self.model}; payload["override_settings_restore_afterwards"] = True
        try:
            response = httpx.post(f"{self.base_url}/sdapi/v1/txt2img", json=payload, timeout=self.timeout); response.raise_for_status(); data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"Ha fallat la generació local A1111/Forge: {exc}") from exc
        if not isinstance(data, dict): raise RuntimeError("Resposta A1111/Forge no vàlida")
        images = data.get("images") or []
        if not isinstance(images, list): raise RuntimeError("Resposta A1111/Forge no vàlida")
        if not images: raise RuntimeError("A1111/Forge no ha retornat cap imatge")
        try: raw = base64.b64decode(images[0].split(",", 1)[-1], validate=True)
        except (ValueError, TypeError, AttributeError) as exc: raise RuntimeError("A1111/Forge ha retornat una imatge no vàlida") from exc
        try:
            if len(raw) > 32 * 1024 * 1024: raise ValueError("Imatge massa gran")
            with Image.open(BytesIO(raw)) as image:
                if image.format != "PNG" or image.width * image.height > 16777216:
                    raise ValueError("Format o mida no admés")
                image.verify()
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise RuntimeError("A1111/Forge ha retornat una imatge no vàlida") from exc
        path = request.output_dir / f"generated-{uuid4().hex[:12]}.png"; 
        with path.open("xb") as f: f.write(raw)
        return GeneratedImage(path=path, provider=self.name, model=self.model, notes=str(data.get("info", ""))[:2000])


_PROVIDERS: dict[str, ImageProvider] = {"manual": ManualImageProvider()}


def register_provider(provider: ImageProvider) -> None:
    name = provider.name.strip().casefold()
    if not name or name == "manual": raise ValueError("Nom de proveïdor reservat o no vàlid")
    _PROVIDERS[name] = provider


def configure_a1111(base_url: str, model: str = "") -> None:
    if base_url.strip(): _PROVIDERS["a1111"] = A1111ImageProvider(base_url, model)
    else: _PROVIDERS.pop("a1111", None)


def provider_names() -> tuple[str, ...]: return tuple(sorted(_PROVIDERS))
def available_providers() -> tuple[str, ...]: return tuple(name for name in provider_names() if _PROVIDERS[name].available())

def get_provider(name: str) -> ImageProvider:
    key = name.strip().casefold()
    if key not in _PROVIDERS: raise ValueError("Proveïdor d'imatges no configurat")
    return _PROVIDERS[key]


def generate_image(provider_name: str, prompt: AmbiencePrompt, *, width: int = 1344, height: int = 768, steps: int = 28, cfg_scale: float = 6.5) -> GeneratedImage:
    """Punt d'entrada únic perquè la UI no depenga de cap API concreta."""
    provider = get_provider(provider_name)
    if provider_name != "manual" and not provider.available():
        raise RuntimeError(f"El proveïdor {provider_name} no està disponible")
    return provider.generate(ImageGenerationRequest(prompt, width, height, settings.image_generation_dir, steps, cfg_scale))


configure_a1111(settings.image_a1111_url, settings.image_a1111_model)

