"""Capes de moviment natural (pluja, neu, pols, guspires) damunt del fons.

En compte de moure la foto sencera, es genera un vídeo curt de partícules sobre
negre que es repeteix en bucle i es barreja amb el fons (mode «screen»): només
es mou la pluja, la neu, la pols o les guspires.

- Els bucles són exactes: cada partícula torna al punt de partida al final del
  cicle, així que no es nota on comença i on acaba.
- No cal baixar res: les capes es generen una vegada i es guarden en
  data/overlays/.
- Si poses un vídeo teu en assets/overlays/ amb el nom de l'estil al principi
  (p. ex. «neu-pexels.mp4», fet sobre fons negre), s'usa eixe en lloc del generat.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import random
import subprocess

from PIL import Image, ImageDraw, ImageFilter

VERSION = 1
# Estil → (durada del bucle en segons, opacitat en barrejar-lo amb el fons)
STYLES: dict[str, tuple[int, float]] = {
    "pluja": (4, 0.65),
    "pluja-forta": (4, 0.7),
    "neu": (20, 0.8),
    "pols": (30, 0.75),
    "guspires": (12, 1.0),
}
STYLE_LABELS = {
    "pluja": "Pluja",
    "pluja-forta": "Pluja forta",
    "neu": "Neu",
    "pols": "Pols en la llum",
    "guspires": "Guspires",
}
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}

# Temes on la foto és a l'aire lliure: només ací cau pluja o neu per tota la imatge.
OUTDOOR_THEMES = {"Bosc", "Parc a la ciutat", "Campament d'aventurers"}
# Temes on la pols flotant no té sentit.
NO_DUST_THEMES = {"Nau espacial"}
_RAIN = {"pluja", "pluja-llar", "pluja-ciutat", "pluja-bosc", "pluja-finestra"}
_STORM = {"tempesta", "tempesta-mar"}
_FIRE_OUTSIDE = {"campament"}


def overlay_style(theme: str, environment: str) -> str | None:
    """Estil de capa que encaixa amb el tema i l'entorn (None = cap)."""
    if theme in OUTDOOR_THEMES:
        if environment in _STORM:
            return "pluja-forta"
        if environment in _RAIN:
            return "pluja"
        if environment == "hivern":
            return "neu"
        if environment in _FIRE_OUTSIDE:
            return "guspires"
        return "pols"
    if theme in NO_DUST_THEMES:
        return None
    # Interiors: la pluja és darrere de la finestra; dins només sura la pols en la llum.
    return "pols"


@dataclass(frozen=True)
class _Particle:
    x: float
    y: float
    speed: int        # voltes completes (de dalt a baix) per bucle; 0 = no cau
    size: float
    level: int        # brillantor 0-255
    sway: float       # amplitud del balanceig horitzontal
    sway_turns: int   # balanceigs per bucle
    phase: float
    bob: float = 0.0  # amplitud vertical (pols)
    bob_turns: int = 1


def _particles(style: str, width: int, height: int, rng: random.Random) -> list[_Particle]:
    scale = width / 960
    if style in {"pluja", "pluja-forta"}:
        count, speeds, level = (700, (4, 5, 6), (90, 170)) if style == "pluja-forta" else (380, (3, 4, 5), (60, 130))
        return [_Particle(rng.uniform(0, width), rng.uniform(0, height), rng.choice(speeds), rng.uniform(10, 26) * scale,
                          rng.randint(*level), 0, 1, 0) for _ in range(count)]
    if style == "neu":
        return [_Particle(rng.uniform(0, width), rng.uniform(0, height), rng.choice((1, 1, 2)), rng.uniform(0.8, 2.6) * scale,
                          rng.randint(140, 235), rng.uniform(4, 22) * scale, rng.choice((1, 2, 3)), rng.uniform(0, 2 * math.pi)) for _ in range(240)]
    if style == "pols":
        return [_Particle(rng.uniform(0, width), rng.uniform(0, height), 0, rng.uniform(1.2, 2.8) * scale,
                          rng.randint(140, 235), rng.uniform(8, 40) * scale, rng.choice((1, 2)), rng.uniform(0, 2 * math.pi),
                          rng.uniform(6, 30) * scale, rng.choice((1, 2, 3))) for _ in range(130)]
    if style == "guspires":
        return [_Particle(rng.uniform(0, width), rng.uniform(0, height), -rng.choice((1, 1, 2)), rng.uniform(1.3, 2.6) * scale,
                          rng.randint(200, 255), rng.uniform(6, 26) * scale, rng.choice((1, 2, 3)), rng.uniform(0, 2 * math.pi)) for _ in range(80)]
    raise ValueError(f"Estil de capa desconegut: {style}")


def render_frame(style: str, particles: list[_Particle], width: int, height: int, t: float) -> Image.Image:
    """Fotograma en la fracció de cicle t (0 ≤ t < 1). t=1 és idèntic a t=0."""
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    angle = 2 * math.pi * t
    for p in particles:
        y = (p.y + p.speed * height * t) % height
        x = (p.x + p.sway * math.sin(p.sway_turns * angle + p.phase)) % width
        if style in {"pluja", "pluja-forta"}:
            c = (p.level, p.level, min(255, p.level + 12))
            draw.line([(x, y), (x - p.size * 0.12, y - p.size)], fill=c, width=1)
        elif style == "neu":
            c = (p.level,) * 3
            draw.ellipse([x - p.size, y - p.size, x + p.size, y + p.size], fill=c)
        elif style == "pols":
            y = (p.y + p.bob * math.sin(p.bob_turns * angle + p.phase * 1.7)) % height
            glow = 0.55 + 0.45 * math.sin(2 * p.bob_turns * angle + p.phase)
            level = int(p.level * glow)
            c = (level, int(level * 0.9), int(level * 0.72))
            draw.ellipse([x - p.size, y - p.size, x + p.size, y + p.size], fill=c)
        else:  # guspires: pugen i s'apaguen en arribar a dalt
            fade = min(1.0, 1.6 * y / height)
            level = int(p.level * fade)
            c = (level, int(level * 0.55), int(level * 0.18))
            draw.ellipse([x - p.size, y - p.size, x + p.size, y + p.size], fill=c)
    blur = {"pluja": 0.6, "pluja-forta": 0.7, "neu": 1.1, "pols": 1.4, "guspires": 0.9}[style]
    return image.filter(ImageFilter.GaussianBlur(blur))


def _generate(style: str, output: Path, width: int, height: int, fps: int, *, seed: int = 7) -> Path:
    seconds = STYLES[style][0]
    frames = seconds * fps
    work_w, work_h = max(2, width // 2 // 2 * 2), max(2, height // 2 // 2 * 2)  # es dibuixa a mitja mida i s'amplia
    particles = _particles(style, work_w, work_h, random.Random(seed))
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(".part.mp4")
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{work_w}x{work_h}", "-r", str(fps), "-i", "-",
        "-vf", f"scale={width}:{height}:flags=bicubic", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(partial),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for index in range(frames):
            process.stdin.write(render_frame(style, particles, work_w, work_h, index / frames).tobytes())
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", "replace")
        if process.wait() != 0:
            raise RuntimeError(f"No s'ha pogut generar la capa «{style}»: {error[-300:]}")
    except BaseException:
        process.kill()
        partial.unlink(missing_ok=True)
        raise
    partial.replace(output)
    return output


def find_custom(folder: Path, style: str) -> Path | None:
    """Vídeo propi per a l'estil en assets/overlays/ (nom que comença per l'estil)."""
    if not folder.is_dir():
        return None
    for path in sorted(folder.iterdir()):
        stem = path.stem.casefold()
        if path.suffix.casefold() in VIDEO_SUFFIXES and (stem == style or stem.startswith(style + "-")) and not (style == "pluja" and stem.startswith("pluja-forta")):
            return path
    return None


def ensure_overlay(style: str, *, cache_dir: Path, custom_dir: Path, width: int, height: int, fps: int) -> Path:
    """Torna la capa de l'estil: la teua si n'hi ha, o la generada (es fa només la primera vegada)."""
    if style not in STYLES:
        raise ValueError(f"Estil de capa desconegut: {style}")
    custom = find_custom(custom_dir, style)
    if custom:
        return custom
    path = cache_dir / f"{style}-v{VERSION}-{width}x{height}-{fps}.mp4"
    if path.is_file() and path.stat().st_size > 0:
        return path
    return _generate(style, path, width, height, fps)


def overlay_opacity(style: str) -> float:
    return STYLES[style][1]
