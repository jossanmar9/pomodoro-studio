"""Comprovació del vídeo abans de pujar-lo: duració, so i imatge.

És ràpida: el so es llig sencer (descodificar només l'àudio va de pressa) i la imatge
es comprova en uns quants punts repartits pel vídeo.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

DURATION_TOLERANCE = 3     # segons de diferència acceptats
SILENCE_DB = -70           # per davall d'açò es considera silenci
SILENCE_SECONDS = 15       # un silenci tan llarg ja és un problema
BLACK_LEVEL = 4            # lluminositat mitjana (0-255) per davall de la qual el fotograma és negre
SAMPLES = 8


def _run(command: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, timeout=timeout, check=False)


def _duration_and_streams(video: Path) -> tuple[float, set[str]]:
    result = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "default=nw=1", str(video)], 120)
    text = result.stdout.decode("utf-8", "replace")
    streams = set(re.findall(r"codec_type=(\w+)", text))
    match = re.search(r"duration=([\d.]+)", text)
    return (float(match.group(1)) if match else 0.0), streams


def _silences(video: Path, end: float) -> list[float]:
    """Duració dels silencis llargs (sense comptar la fosa del final)."""
    result = _run(["ffmpeg", "-nostdin", "-hide_banner", "-i", str(video), "-map", "0:a:0", "-vn",
                   "-af", f"silencedetect=noise={SILENCE_DB}dB:d={SILENCE_SECONDS}", "-f", "null", "-"])
    text = result.stderr.decode("utf-8", "replace")
    found = []
    for start, length in zip(re.findall(r"silence_start: ([\d.]+)", text), re.findall(r"silence_duration: ([\d.]+)", text)):
        if float(start) < end - 10:
            found.append(float(length))
    return found


def _brightness(video: Path, second: float) -> float | None:
    result = _run(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{second:.1f}", "-i", str(video), "-frames:v", "1",
                   "-vf", "scale=64:36", "-f", "rawvideo", "-pix_fmt", "gray", "-"], 120)
    data = result.stdout
    return sum(data) / len(data) if data else None


def check_video(video: Path, expected_seconds: int, *, dark_after: int | None = None, black_screen: bool = False) -> list[str]:
    """Torna la llista de problemes trobats (buida si tot està bé).

    `dark_after`: segon a partir del qual la pantalla s'enfosquix a posta (vídeos per a dormir).
    `black_screen`: el vídeo és negre a posta (soroll amb pantalla negra).
    """
    if not video.is_file() or video.stat().st_size == 0:
        return ["el fitxer del vídeo no existeix o està buit"]
    problems: list[str] = []
    duration, streams = _duration_and_streams(video)
    if "video" not in streams:
        problems.append("el vídeo no té imatge")
    if "audio" not in streams:
        problems.append("el vídeo no té so")
    if abs(duration - expected_seconds) > DURATION_TOLERANCE:
        problems.append(f"dura {duration / 60:.1f} min i n'hauria de durar {expected_seconds / 60:.0f}")
    if "audio" in streams:
        silences = _silences(video, duration or expected_seconds)
        if silences:
            problems.append(f"hi ha {len(silences)} tros{'sos' if len(silences) > 1 else ''} sense so (el més llarg, de {max(silences):.0f} s)")
    if "video" in streams and not black_screen and duration > 0:
        last = min(duration, dark_after) if dark_after else duration
        points = [5 + (last - 10) * n / max(1, SAMPLES - 1) for n in range(SAMPLES)] if last > 20 else [last / 2]
        black = [p for p in points if (b := _brightness(video, p)) is not None and b < BLACK_LEVEL]
        if black:
            problems.append(f"la imatge és negra en {len(black)} de {len(points)} punts revisats")
    return problems
