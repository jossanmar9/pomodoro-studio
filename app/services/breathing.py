"""Respiració guiada: un cercle que creix i es fa xicotet al ritme de la respiració.

Es genera un cicle exacte (p. ex. 16 s per a la respiració quadrada) sobre negre,
que es repeteix en bucle i es barreja amb el fons, igual que les capes de moviment.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageFont

VERSION = 1


@dataclass(frozen=True)
class BreathPattern:
    label: str                           # nom en valencià
    public: str                          # nom públic en anglés
    steps: tuple[tuple[str, int], ...]   # (fase, segons): inhale, hold, exhale
    how: str                             # explicació en anglés per a la descripció


PATTERNS: dict[str, BreathPattern] = {
    "quadrada": BreathPattern("Quadrada 4-4-4-4", "Box Breathing", (("inhale", 4), ("hold", 4), ("exhale", 4), ("hold", 4)),
                              "Breathe in for 4 seconds, hold for 4, breathe out for 4 and hold again for 4."),
    "478": BreathPattern("Relaxant 4-7-8", "4-7-8 Breathing", (("inhale", 4), ("hold", 7), ("exhale", 8)),
                         "Breathe in for 4 seconds, hold for 7 and breathe out slowly for 8."),
    "coherent": BreathPattern("Coherent 5-5", "Coherent Breathing", (("inhale", 5), ("exhale", 5)),
                              "Breathe in for 5 seconds and out for 5: six calm breaths per minute."),
}
DURATIONS = (5, 10, 15, 20, 30)
WORDS = {"inhale": "Breathe in", "hold": "Hold", "exhale": "Breathe out"}
DARKEN = 0.2
OPACITY = 0.95


def cycle_seconds(pattern: str) -> int:
    return sum(seconds for _, seconds in PATTERNS[pattern].steps)


def _ease(x: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))


def state(pattern: str, t: float) -> tuple[str, float, int]:
    """(fase, mida 0-1, segons que queden de la fase) en el segon t del cicle."""
    t %= cycle_seconds(pattern)
    size = 0.0
    for phase, seconds in PATTERNS[pattern].steps:
        if t < seconds:
            if phase == "inhale":
                size = _ease(t / seconds)
            elif phase == "exhale":
                size = 1 - _ease(t / seconds)
            else:
                size = 1.0 if size >= 0.5 else 0.0
            return phase, size, max(1, math.ceil(seconds - t))
        size = 1.0 if phase == "inhale" else 0.0 if phase == "exhale" else size
        t -= seconds
    raise AssertionError("cicle buit")


def _font(path: Path | None, size: int) -> ImageFont.ImageFont:
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


# Preparació abans del primer cicle: 10 s per a posar-se còmode i 5 s de compte enrere.
SETTLE_SECONDS = 10
COUNTDOWN_SECONDS = 5
INTRO_SECONDS = SETTLE_SECONDS + COUNTDOWN_SECONDS


def _circle(width: int, height: int, size: float) -> tuple[Image.Image, ImageDraw.ImageDraw, float]:
    image = Image.new("RGB", (width, height))
    unit = min(width, height)
    small, big = unit * 0.13, unit * 0.30
    radius = small + (big - small) * size
    cx, cy = width / 2, height / 2
    glow = Image.new("RGB", (width, height))
    g = ImageDraw.Draw(glow)
    g.ellipse([cx - radius * 1.12, cy - radius * 1.12, cx + radius * 1.12, cy + radius * 1.12], fill=(120, 96, 60))
    image.paste(glow.filter(ImageFilter.GaussianBlur(unit * 0.04)))
    draw = ImageDraw.Draw(image)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(70, 56, 36), outline=(255, 226, 170), width=max(2, unit // 270))
    # Guia: on acaba el cercle quan està ple.
    draw.ellipse([cx - big, cy - big, cx + big, cy + big], outline=(90, 80, 64), width=max(1, unit // 540))
    return image, draw, unit


def render_frame(pattern: str, t: float, width: int, height: int, font: Path | None = None) -> Image.Image:
    phase, size, left = state(pattern, t)
    image, draw, unit = _circle(width, height, size)
    cx, cy = width / 2, height / 2
    word_font, count_font = _font(font, int(unit * 0.055)), _font(font, int(unit * 0.04))
    draw.text((cx, cy - unit * 0.015), WORDS[phase], font=word_font, fill=(255, 240, 215), anchor="ms")
    draw.text((cx, cy + unit * 0.05), str(left), font=count_font, fill=(225, 205, 170), anchor="ms")
    return image


def render_intro_frame(t: float, width: int, height: int, font: Path | None = None) -> Image.Image:
    """Preparació: el cercle quiet (com en començar a inspirar), indicacions i compte enrere."""
    image, draw, unit = _circle(width, height, 0.0)
    cx, cy = width / 2, height / 2
    if t < SETTLE_SECONDS:
        draw.text((cx, cy - unit * 0.015), "Get comfortable", font=_font(font, int(unit * 0.05)), fill=(255, 240, 215), anchor="ms")
        draw.text((cx, cy + unit * 0.045), "Relax your shoulders", font=_font(font, int(unit * 0.03)), fill=(225, 205, 170), anchor="ms")
        draw.text((cx, cy + unit * 0.085), "and breathe naturally", font=_font(font, int(unit * 0.03)), fill=(225, 205, 170), anchor="ms")
    else:
        left = max(1, math.ceil(INTRO_SECONDS - t))
        draw.text((cx, cy - unit * 0.03), "Starting in", font=_font(font, int(unit * 0.04)), fill=(225, 205, 170), anchor="ms")
        draw.text((cx, cy + unit * 0.06), str(left), font=_font(font, int(unit * 0.09)), fill=(255, 240, 215), anchor="ms")
    return image


def _encode(path: Path, frames, width: int, height: int, fps: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part.mp4")
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(partial),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in frames:
            process.stdin.write(frame.tobytes())
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", "replace")
        if process.wait() != 0:
            raise RuntimeError(f"No s'ha pogut generar la respiració: {error[-300:]}")
    except BaseException:
        process.kill()
        partial.unlink(missing_ok=True)
        raise
    partial.replace(path)
    return path


def ensure_breath_intro(*, cache_dir: Path, width: int, height: int, fps: int, font: Path | None = None) -> Path:
    """Clip de preparació (15 s) que va abans del primer cicle."""
    tag = hashlib.sha1(str(font or "").encode()).hexdigest()[:8]
    path = cache_dir / f"respiracio-intro-v{VERSION}-{tag}-{width}x{height}-{fps}.mp4"
    if path.is_file() and path.stat().st_size > 0:
        return path
    frames = (render_intro_frame(index / fps, width, height, font) for index in range(INTRO_SECONDS * fps))
    return _encode(path, frames, width, height, fps)


def ensure_breath_clip(pattern: str, *, cache_dir: Path, width: int, height: int, fps: int, font: Path | None = None) -> Path:
    """Clip d'un cicle exacte (es genera la primera vegada i es reutilitza)."""
    if pattern not in PATTERNS:
        raise ValueError("Respiració no vàlida")
    tag = hashlib.sha1(str(font or "").encode()).hexdigest()[:8]
    path = cache_dir / f"respiracio-{pattern}-v{VERSION}-{tag}-{width}x{height}-{fps}.mp4"
    if path.is_file() and path.stat().st_size > 0:
        return path
    frames = (render_frame(pattern, index / fps, width, height, font) for index in range(cycle_seconds(pattern) * fps))
    return _encode(path, frames, width, height, fps)
