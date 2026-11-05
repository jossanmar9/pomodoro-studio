"""Intro del canal (6 s): pantalla negra amb espurnes, apareix «The Amber Window» en daurat,
el nom s'il·lumina fins al blanc, l'escena del vídeo apareix darrere i el nom s'esvaïx.

El clip (negre amb espurnes i nom) es genera una sola vegada i es barreja amb l'inici del
vídeo en mode «screen» (el negre no tapa res); vegeu renderer.build_ffmpeg_command.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import random
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageFont

VERSION = 1
SECONDS = 6
REVEAL_AT = 3.3        # l'escena comença a aparéixer
REVEAL_SECONDS = 1.8
FADE_AT = 3.8          # el nom comença a esvair-se
FADE_SECONDS = 1.8
TIMER_FROM = 5.4       # el comptador apareix quan el nom ja s'ha esvaït
NAME = "THE AMBER WINDOW"
TAGLINE = "COZY AMBIENCE"
GOLD_TOP, GOLD_BOTTOM = (246, 222, 166), (196, 146, 70)


def _font(path: Path | None, size: int):
    for candidate in ([str(path)] if path else []) + ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _title_layers(width: int, height: int, font_path: Path | None) -> tuple[Image.Image, Image.Image]:
    """Capa del nom en daurat (amb la frase i dues línies fines) i la seua lluentor."""
    mask = Image.new("L", (width, height))
    draw = ImageDraw.Draw(mask)
    big = _font(font_path, int(height * 0.1))
    small = _font(font_path, int(height * 0.024))
    cx, cy = width / 2, height * 0.47
    draw.text((cx, cy), NAME, font=big, fill=255, anchor="mm")
    spaced = " ".join(TAGLINE)
    draw.text((cx, cy + height * 0.095), spaced, font=small, fill=210, anchor="mm")
    line = width * 0.07
    gap = draw.textlength(spaced, font=small) / 2 + width * 0.02
    for side in (-1, 1):
        x0 = cx + side * gap
        draw.line([(x0, cy + height * 0.095), (x0 + side * line, cy + height * 0.095)], fill=150, width=max(1, height // 540))
    gradient = Image.new("RGB", (1, height))
    top, bottom = cy - height * 0.06, cy + height * 0.1
    for y in range(height):
        k = max(0.0, min(1.0, (y - top) / (bottom - top)))
        gradient.putpixel((0, y), tuple(round(a + (b - a) * k) for a, b in zip(GOLD_TOP, GOLD_BOTTOM)))
    gold = Image.new("RGBA", (width, height))
    gold.paste(gradient.resize((width, height)), (0, 0), mask)
    glow = Image.new("RGBA", (width, height), (255, 244, 220, 0))
    glow.putalpha(mask.filter(ImageFilter.GaussianBlur(height * 0.012)))
    return gold, glow


def _sparks(width: int, height: int, rng: random.Random, count: int = 140) -> list[tuple[float, float, float, float, float, float]]:
    """(x, y, mida, velocitat de pujada, fase de parpelleig, deriva) de cada espurna."""
    return [(rng.uniform(0, width), rng.uniform(0, height), rng.uniform(0.8, 2.6) * height / 1080, rng.uniform(8, 40) * height / 1080,
             rng.uniform(0, math.tau), rng.uniform(-12, 12) * height / 1080) for _ in range(count)]


def render_frame(t: float, width: int, height: int, gold: Image.Image, glow: Image.Image, sparks) -> Image.Image:
    frame = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(frame)
    sparks_on = _smooth(t / 0.8)
    for x, y, size, speed, phase, drift in sparks:
        px = (x + drift * t) % width
        py = (y - speed * t) % height
        twinkle = 0.55 + 0.45 * math.sin(phase + t * 2.3)
        level = int(255 * sparks_on * twinkle * min(1.0, size / 2.6))
        colour = (level, int(level * 0.8), int(level * 0.5))
        draw.ellipse([px - size, py - size, px + size, py + size], fill=colour)
    frame = frame.filter(ImageFilter.GaussianBlur(0.6))
    appear = _smooth((t - 0.8) / 1.2)
    white = _smooth((t - 2.7) / 0.9)
    if appear > 0:
        layer = Image.new("RGBA", (width, height))
        gold_now = gold.copy()
        gold_now.putalpha(gold.getchannel("A").point(lambda a: int(a * appear)))
        layer = Image.alpha_composite(layer, gold_now)
        if white > 0:
            bright = glow.copy()
            bright.putalpha(glow.getchannel("A").point(lambda a: int(a * white * 0.9)))
            layer = Image.alpha_composite(layer, bright)
            whitened = Image.new("RGBA", (width, height), (255, 250, 240, 0))
            whitened.putalpha(gold.getchannel("A").point(lambda a: int(a * appear * white * 0.85)))
            layer = Image.alpha_composite(layer, whitened)
        frame = Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")
    return frame


def ensure_channel_intro(*, cache_dir: Path, width: int, height: int, fps: int, font: Path | None = None) -> Path:
    """Clip de la intro (es fa la primera vegada i es reutilitza)."""
    tag = hashlib.sha1(f"{font}".encode()).hexdigest()[:8]
    path = cache_dir / f"intro-canal-v{VERSION}-{tag}-{width}x{height}-{fps}.mp4"
    if path.is_file() and path.stat().st_size > 0:
        return path
    gold, glow = _title_layers(width, height, font)
    sparks = _sparks(width, height, random.Random(7))
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part.mp4")
    command = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(partial)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for index in range(SECONDS * fps):
            process.stdin.write(render_frame(index / fps, width, height, gold, glow, sparks).tobytes())
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", "replace")
        if process.wait() != 0:
            raise RuntimeError(f"No s'ha pogut fer la intro: {error[-300:]}")
    except BaseException:
        process.kill()
        partial.unlink(missing_ok=True)
        raise
    partial.replace(path)
    return path


def intro_filters(main: str, intro: str, out: str, fps: int, width: int, height: int) -> list[str]:
    """Barreja la intro amb els primers segons del vídeo; la resta del vídeo passa igual."""
    return [
        f"{main}split[vmain_a][vmain_b]",
        f"[vmain_a]trim=0:{SECONDS},setpts=PTS-STARTPTS,fade=t=in:st={REVEAL_AT}:d={REVEAL_SECONDS},format=gbrp[vhead]",
        f"[vmain_b]trim=start={SECONDS},setpts=PTS-STARTPTS[vtail]",
        f"{intro}scale={width}:{height},setsar=1,fps={fps},fade=t=out:st={FADE_AT}:d={FADE_SECONDS},format=gbrp[vintro]",
        "[vhead][vintro]blend=all_mode=screen,format=yuv420p[vjoined]",
        f"[vjoined][vtail]concat=n=2:v=1:a=0[{out}]",
    ]
