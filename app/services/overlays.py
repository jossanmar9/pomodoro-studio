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
    "fulles": (24, 1.0),
    "petals": (24, 1.0),
    "cuques": (20, 1.0),
    "boira": (60, 0.6),
}
# Les fulles i els pètals tapen el fons (no són llum): es retallen del negre i es posen damunt.
KEY_STYLES = {"fulles", "petals"}
STYLE_LABELS = {
    "pluja": "Pluja",
    "pluja-forta": "Pluja forta",
    "neu": "Neu",
    "pols": "Pols en la llum",
    "guspires": "Guspires",
    "fulles": "Fulles caient",
    "petals": "Pètals",
    "cuques": "Cuques de llum",
    "boira": "Boirina",
}
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}

# Temes on la foto és a l'aire lliure: només ací cau pluja o neu per tota la imatge.
OUTDOOR_THEMES = {"Bosc", "Parc a la ciutat", "Campament d'aventurers", "Platja", "Riu", "Port",
                  "Bosc de tardor", "Jardí de primavera", "Porxo d'estiu", "Nit d'estiu"}
# Temes de Nadal a l'aire lliure: sempre neva.
SNOW_THEMES = {"Poble nevat", "Mercat de Nadal"}
# Temes de temporada: la capa va amb el tema (si no plou o fa tempesta a l'aire lliure).
SEASON_THEMES = {
    "Bosc de tardor": "fulles",
    "Jardí de primavera": "petals",
    "Porxo d'estiu": "cuques", "Nit d'estiu": "cuques",
    "Cabana de Halloween": "boira", "Biblioteca de Halloween": "boira",
}
# Temes on la pols flotant no té sentit.
NO_DUST_THEMES = {"Avió"}
_RAIN = {"pluja", "pluja-llar", "pluja-ciutat", "pluja-bosc", "pluja-finestra", "port", "biblioteca"}
_STORM = {"tempesta", "tempesta-mar", "bosc-tempesta", "platja-tempesta", "llar-tempesta"}
_FIRE_OUTSIDE = {"campament"}


def overlay_style(theme: str, environment: str) -> str | None:
    """Estil de capa que encaixa amb el tema i l'entorn (None = cap)."""
    if theme in SNOW_THEMES:
        return "neu"
    if theme in SEASON_THEMES:
        if theme in OUTDOOR_THEMES and environment in _STORM:
            return "pluja-forta"
        if theme in OUTDOOR_THEMES and environment in _RAIN and SEASON_THEMES[theme] != "fulles":
            return "pluja"
        return SEASON_THEMES[theme]
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
    if style == "fulles":
        return [_Particle(rng.uniform(0, width), rng.uniform(0, height), rng.choice((1, 1, 2)), rng.uniform(6, 11) * scale,
                          rng.randrange(len(LEAF_COLORS)), rng.uniform(20, 60) * scale, rng.choice((1, 2)), rng.uniform(0, 2 * math.pi),
                          bob_turns=rng.choice((1, 2, 3))) for _ in range(45)]
    if style == "petals":
        return [_Particle(rng.uniform(0, width), rng.uniform(0, height), rng.choice((1, 1, 2)), rng.uniform(2.5, 4.5) * scale,
                          rng.randrange(len(PETAL_COLORS)), rng.uniform(30, 80) * scale, rng.choice((1, 2, 3)), rng.uniform(0, 2 * math.pi),
                          bob_turns=rng.choice((2, 3, 4))) for _ in range(70)]
    if style == "cuques":
        return [_Particle(rng.uniform(0, width), rng.uniform(height * 0.25, height), 0, rng.uniform(2.2, 3.6) * scale,
                          rng.randint(220, 255), rng.uniform(15, 60) * scale, rng.choice((1, 2)), rng.uniform(0, 2 * math.pi),
                          rng.uniform(10, 40) * scale, rng.choice((2, 3, 4, 5))) for _ in range(55)]
    if style == "boira":
        return [_Particle(rng.uniform(0, width), rng.uniform(height * 0.5, height * 0.98), 0, rng.uniform(0.12, 0.28) * width,
                          rng.randint(95, 150), 0, 1, rng.uniform(0, 2 * math.pi), rng.uniform(0.02, 0.06) * height, 1) for _ in range(16)]
    raise ValueError(f"Estil de capa desconegut: {style}")


LEAF_COLORS = ((232, 122, 40), (205, 64, 42), (236, 182, 58), (178, 104, 52))
PETAL_COLORS = ((250, 190, 212), (252, 226, 236), (246, 168, 196))


def _rotated_ellipse(cx: float, cy: float, rx: float, ry: float, angle: float, steps: int = 12) -> list[tuple[float, float]]:
    ca, sa = math.cos(angle), math.sin(angle)
    points = []
    for i in range(steps):
        a = 2 * math.pi * i / steps
        x, y = rx * math.cos(a), ry * math.sin(a)
        points.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return points


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
        elif style in {"fulles", "petals"}:
            colors = LEAF_COLORS if style == "fulles" else PETAL_COLORS
            spin = p.phase + p.bob_turns * angle
            # Les fulles giren mentre cauen: l'amplada canvia com si es voltejaren.
            flip = 0.35 + 0.65 * abs(math.cos(spin))
            draw.polygon(_rotated_ellipse(x, y, p.size * flip, p.size * (0.5 if style == "fulles" else 0.7), spin), fill=colors[p.level % len(colors)])
        elif style == "cuques":
            y = (p.y + p.bob * math.sin(p.bob_turns * angle + p.phase * 1.3)) % height
            glow = max(0.0, math.sin(p.bob_turns * angle + p.phase)) ** 3
            level = int(p.level * glow)
            c = (int(level * 0.8), level, int(level * 0.35))
            draw.ellipse([x - p.size, y - p.size, x + p.size, y + p.size], fill=c)
        elif style == "boira":
            # Bancs de boira que passen lentament d'esquerra a dreta (es dibuixen també a l'altre costat per a no tallar-los).
            x = (p.x + width * t) % width
            y = p.y + p.bob * math.sin(angle + p.phase)
            c = (p.level, p.level, min(255, p.level + 8))
            for dx in (-width, 0, width):
                draw.ellipse([x + dx - p.size, y - p.size * 0.35, x + dx + p.size, y + p.size * 0.35], fill=c)
        else:  # guspires: pugen i s'apaguen en arribar a dalt
            fade = min(1.0, 1.6 * y / height)
            level = int(p.level * fade)
            c = (level, int(level * 0.55), int(level * 0.18))
            draw.ellipse([x - p.size, y - p.size, x + p.size, y + p.size], fill=c)
    blur = {"pluja": 0.6, "pluja-forta": 0.7, "neu": 1.1, "pols": 1.4, "guspires": 0.9, "fulles": 0.5, "petals": 0.5,
            "cuques": 1.8, "boira": width * 0.04}[style]
    return image.filter(ImageFilter.GaussianBlur(blur))


def _generate(style: str, output: Path, width: int, height: int, fps: int, *, seed: int = 7) -> Path:
    seconds = STYLES[style][0]
    frames = seconds * fps
    shrink = 4 if style == "boira" else 2  # es dibuixa més xicotet i s'amplia (la boira és tota borrosa)
    work_w, work_h = max(2, width // shrink // 2 * 2), max(2, height // shrink // 2 * 2)
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


def overlay_mode(style: str) -> str:
    """«key» (es retalla el negre i es posa damunt) o «screen» (se suma com a llum)."""
    return "key" if style in KEY_STYLES else "screen"
