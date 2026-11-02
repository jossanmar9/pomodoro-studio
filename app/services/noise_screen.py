"""Fons propi dels vídeos de soroll de color: un color llis i fosc, o pantalla negra.

No usa cap foto: es genera una imatge amb un degradat suau del color del soroll
(marró, rosa o blanc) i, si es vol, el nom xicotet al centre.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Pantalla: «color» (degradat del color del soroll) o «negre» (pantalla negra).
NOISE_SCREENS = {"color": "Fons de color", "negre": "Pantalla negra"}

# Color del centre i de les vores per a cada soroll.
PALETTE: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "marro": ((92, 60, 40), (30, 19, 12)),
    "rosa": ((132, 88, 96), (48, 30, 35)),
    "blanc": ((150, 150, 154), (70, 70, 74)),
}
# Quant varia la llum quan el color «respira» (cicle de 20 s).
PULSE_PERIOD = 20
PULSE_DEPTH = 0.04


def _font(path: Path | None, size: int) -> ImageFont.ImageFont:
    for candidate in ([str(path)] if path else []) + ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_noise_background(noise: str, screen: str, output: Path, *, width: int, height: int,
                          text: str | None = None, font: Path | None = None) -> Path:
    """Imatge de fons: degradat radial del color del soroll (o negre) amb el nom opcional."""
    if noise not in PALETTE:
        raise ValueError("Color de soroll no vàlid")
    if screen not in NOISE_SCREENS:
        raise ValueError("Pantalla no vàlida")
    if screen == "negre":
        image = Image.new("RGB", (width, height))
    else:
        centre, edge = PALETTE[noise]
        # Degradat radial calculat en xicotet i ampliat: suau i ràpid.
        small_w, small_h = 192, max(1, round(192 * height / width))
        small = Image.new("RGB", (small_w, small_h))
        pixels = small.load()
        cx, cy = (small_w - 1) / 2, (small_h - 1) / 2
        reach = (cx ** 2 + cy ** 2) ** 0.5
        for y in range(small_h):
            for x in range(small_w):
                d = min(1.0, (((x - cx) ** 2 + (y - cy) ** 2) ** 0.5) / reach)
                k = d * d * (3 - 2 * d)
                pixels[x, y] = tuple(round(c + (e - c) * k) for c, e in zip(centre, edge))
        image = small.resize((width, height), Image.BICUBIC)
    if text:
        draw = ImageDraw.Draw(image)
        colour = (90, 90, 90) if screen == "negre" else (52, 52, 56) if noise == "blanc" else (215, 205, 195)
        draw.text((width / 2, height / 2), text, font=_font(font, max(12, height // 22)), fill=colour, anchor="mm")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return output


def pulse_filter() -> str:
    """Filtre d'FFmpeg: la llum baixa i puja molt a poc a poc (no s'aclareix mai per damunt de l'original)."""
    return f"eq=brightness='-{PULSE_DEPTH:g}*(1-cos(2*PI*t/{PULSE_PERIOD}))/2':eval=frame"
