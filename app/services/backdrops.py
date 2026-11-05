"""Ombres suaus integrades en el fons perquè el text del vídeo es llija bé sobre qualsevol imatge.

Es fan una sola vegada amb PIL abans de renderitzar (no costen res durant el vídeo):
- comptador: un halo fosc i difús darrere del rellotge, al centre;
- Shorts: degradats foscos a dalt (títol) i a baix (peu).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.services.renderer import SUPPORTED_IMAGE_SUFFIXES

TIMER_SHADE = 0.42   # foscor màxima al centre del rellotge
SHORT_SHADE = 0.62   # foscor màxima a dalt i a baix del Short


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    scale = max(width / image.width, height / image.height)
    image = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    left, top = (image.width - width) // 2, (image.height - height) // 2
    return image.crop((left, top, left + width, top + height))


def _apply(image: Image.Image, mask_small: Image.Image) -> Image.Image:
    mask = mask_small.resize(image.size, Image.BICUBIC)
    return Image.composite(Image.new("RGB", image.size, (6, 5, 4)), image, mask)


def timer_backdrop(background: Path, output: Path, width: int = 1920, height: int = 1080) -> Path:
    """Fons amb un halo fosc i suau darrere del comptador (centre de la pantalla)."""
    if background.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        return background
    image = _cover(Image.open(background).convert("RGB"), width, height)
    w, h = 192, 108
    mask = Image.new("L", (w, h))
    for y in range(h):
        for x in range(w):
            dx, dy = (x - w / 2) / (w * 0.30), (y - h * 0.47) / (h * 0.30)
            d = (dx * dx + dy * dy) ** 0.5
            k = max(0.0, 1 - d)
            mask.putpixel((x, y), int(255 * TIMER_SHADE * (k * k * (3 - 2 * k))))
    output.parent.mkdir(parents=True, exist_ok=True)
    _apply(image, mask).save(output)
    return output


def short_backdrop(background: Path, output: Path, width: int = 1080, height: int = 1920) -> Path:
    """Fons vertical amb degradats foscos a dalt i a baix, on va el text del Short."""
    if background.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        return background
    image = _cover(Image.open(background).convert("RGB"), width, height)
    h = 192
    mask = Image.new("L", (1, h))
    for y in range(h):
        top = max(0.0, 1 - y / (h * 0.30))
        bottom = max(0.0, (y - h * 0.78) / (h * 0.22))
        k = max(top, bottom)
        mask.putpixel((0, y), int(255 * SHORT_SHADE * k ** 1.3))
    output.parent.mkdir(parents=True, exist_ok=True)
    _apply(image, mask).save(output)
    return output
