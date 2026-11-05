"""Shorts verticals (1080×1920, 45 s) que enllacen amb el vídeo llarg.

Es fan a partir del fons original (no del vídeo final, que és horitzontal i porta
el comptador), amb la mateixa capa de moviment i un tros de l'àudio del vídeo.
"""
from __future__ import annotations

from pathlib import Path

from app.services.renderer import _escape_drawtext, font_option, overlay_parts

WIDTH, HEIGHT, FPS = 1080, 1920, 30
SECONDS = 45
SHADOW = "shadowcolor=black@0.6:shadowx=3:shadowy=3"


def short_start(total_seconds: int, seconds: int = SECONDS, part: int = 1) -> int:
    """Tros d'àudio: el primer a partir dels 2 minuts; el segon i el tercer, a un terç i a dos terços del vídeo."""
    latest = max(0, total_seconds - seconds - 5)
    wanted = 120 if part == 1 else int(total_seconds * (part - 1) / 3)
    return max(0, min(wanted, latest))


# Frase de dalt i títol de cada Short (el primer usa la duració i el so).
SHORT_VARIANTS = {
    2: ("Close your eyes and listen", "Close your eyes · {theme} with {sound} #shorts"),
    3: ("Stay a while", "Stay a while · {theme} · {sound} #shorts"),
}


def variant_title(part: int, theme: str, sound: str) -> str:
    title = SHORT_VARIANTS[part][1].format(theme=theme, sound=sound)
    return title if len(title) <= 100 else f"{theme} #shorts"[:100]


def title_size(title: str) -> int:
    """Títol tan gran com càpia en l'amplària del Short (els noms llargs es fan més xicotets)."""
    return max(64, min(112, int(1000 / (0.62 * max(1, len(title))))))


def build_short_command(background: Path, video: Path, output: Path, *, title: str, subtitle: str, start: int,
                        seconds: int = SECONDS, label_font: Path | None = None, text_font: Path | None = None,
                        overlay: Path | None = None, overlay_opacity: float = 0.6, darken: float = 0.0,
                        footer: str = "Full video on the channel", overlay_mode: str = "screen") -> list[str]:
    command = ["ffmpeg", "-y", "-nostdin", "-loglevel", "error",
               "-loop", "1", "-framerate", str(FPS), "-i", str(background),
               "-ss", str(start), "-t", str(seconds), "-i", str(video)]
    if overlay is not None:
        command += ["-stream_loop", "-1", "-i", str(overlay)]
    base = [f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase", f"crop={WIDTH}:{HEIGHT}", "setsar=1"]
    if darken > 0:
        base.append(f"eq=brightness={-min(0.5, darken):g}:saturation=0.85")
    parts = []
    if overlay is not None:
        parts.extend(overlay_parts(f"[0:v]{','.join(base)}", "[2:v]", WIDTH, HEIGHT, FPS, min(1.0, max(0.0, overlay_opacity)), overlay_mode, "pic"))
        source = "[pic]"
    else:
        parts.append(f"[0:v]{','.join(base)},format=yuv420p[pic]")
        source = "[pic]"
    texts = [
        f"drawtext={font_option(label_font)}:text='{_escape_drawtext(title)}':fontsize={title_size(title)}:fontcolor=0xFFF7E8:x=(w-text_w)/2:y=h*0.09:borderw=2:bordercolor=black@0.3:{SHADOW}",
        f"drawtext={font_option(text_font)}:text='{_escape_drawtext(subtitle)}':fontsize=60:fontcolor=0xF3C47A:x=(w-text_w)/2:y=h*0.09+{title_size(title) + 40}:{SHADOW}",
        f"drawtext={font_option(text_font)}:text='{_escape_drawtext(footer)}':fontsize=58:fontcolor=0xFFF7E8:x=(w-text_w)/2:y=h*0.87:{SHADOW}",
        "fade=t=in:st=0:d=0.6",
        f"fade=t=out:st={seconds - 1}:d=1",
    ]
    parts.append(f"{source}{','.join(texts)}[vout]")
    parts.append(f"[1:a]afade=t=in:st=0:d=1.5,afade=t=out:st={seconds - 2}:d=2[aout]")
    command += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]",
                "-t", str(seconds), "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(output)]
    return command


def short_texts(title: str, description: str, tags: list[str], video_id: str) -> tuple[str, str, list[str]]:
    """Títol, descripció i etiquetes del Short a partir de les del vídeo llarg."""
    head = title.split(" | ")[0].strip()
    short_title = f"{head} #shorts"
    if len(short_title) > 100:
        short_title = head[: 100 - len(" #shorts")].rstrip() + " #shorts"
    first = description.strip().split("\n\n")[0].strip()
    short_description = f"Watch the full video: https://youtu.be/{video_id}\n\n{first}\n\n#shorts"
    return short_title, short_description[:4900], list(dict.fromkeys([*tags, "shorts"]))[:30]


def channel_short_texts(public_theme: str, sound: str, channel_url: str, music: str | None = None) -> tuple[str, str, list[str]]:
    """Textos d'un Short independent que porta al canal (no a un vídeo concret)."""
    title = f"{public_theme} · {sound} Ambience #shorts"
    if len(title) > 100:
        title = f"{public_theme} Ambience #shorts"[:100]
    with_music = f" and {music}" if music else ""
    description = (
        f"A quiet moment in a {public_theme.lower()}, with {sound.lower()} sounds{with_music}.\n\n"
        f"Long ambience videos for studying, reading and sleep on the channel: {channel_url}\n\n"
        "#shorts #ambience #cozy #relaxing"
    )
    tags = ["shorts", "ambience", "cozy ambience", f"{sound.lower()} sounds", public_theme.lower(), "relaxing sounds", "study ambience"]
    return title, description, tags
