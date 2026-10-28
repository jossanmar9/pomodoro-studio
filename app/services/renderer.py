"""Construcció segura d'ordres FFmpeg per al renderitzat de Pomodoro Studio."""

from dataclasses import dataclass
from pathlib import Path

from app.services.timer import TimelineSummary


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}


@dataclass(frozen=True)
class RenderSpec:
    """Paràmetres necessaris per a construir un renderitzat."""

    background: Path
    output: Path
    resolution: str
    timeline: TimelineSummary
    fps: int = 30


def _escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def build_timer_filters(timeline: TimelineSummary) -> str:
    """Crea filtres drawtext per a mostrar fase, sessió i compte arrere.

    Cada segment usa expressions basades en `t`; no es generen imatges per segon.
    """
    filters: list[str] = []
    for segment in timeline.segments:
        start = segment.start_seconds
        end = segment.end_seconds
        remaining = f"max(0,{end}-t)"
        minutes = f"floor(({remaining})/60)"
        seconds = f"mod(floor({remaining}),60)"
        timer = f"%{{eif\\:{minutes}\\:d\\:2}}\\:%{{eif\\:{seconds}\\:d\\:2}}"
        phase = "CONCENTRACIÓ" if segment.kind.value == "FOCUS" else "DESCANS"
        session = f"SESSIÓ {segment.session}"
        enable = f"between(t,{start},{max(start, end - 0.001)})"
        filters.extend([
            "drawtext="
            f"text='{_escape_drawtext(phase)}':"
            "fontcolor=white@0.88:fontsize=h/32:"
            "x=(w-text_w)/2:y=h*0.37:"
            f"enable='{enable}'",
            "drawtext="
            f"text='{_escape_drawtext(timer)}':"
            "fontcolor=white:fontsize=h/9:"
            "borderw=2:bordercolor=black@0.35:"
            "x=(w-text_w)/2:y=(h-text_h)/2:"
            f"enable='{enable}'",
            "drawtext="
            f"text='{_escape_drawtext(session)}':"
            "fontcolor=white@0.72:fontsize=h/44:"
            "x=(w-text_w)/2:y=h*0.62:"
            f"enable='{enable}'",
        ])
    return ",".join(filters)


def build_ffmpeg_command(spec: RenderSpec) -> list[str]:
    """Retorna l'ordre FFmpeg sense `shell=True`.

    Admet una imatge estàtica o un vídeo curt que es repetix fins a completar la
    línia temporal. El vídeo s'escala i retalla per omplir la resolució triada.
    """
    suffix = spec.background.suffix.lower()
    if suffix not in SUPPORTED_IMAGE_SUFFIXES | SUPPORTED_VIDEO_SUFFIXES:
        raise ValueError(f"Format de fons no compatible: {suffix}")

    try:
        width, height = (int(value) for value in spec.resolution.lower().split("x", 1))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Resolució no vàlida; usa el format amplàriaxaltura") from exc
    if width <= 0 or height <= 0:
        raise ValueError("La resolució ha de ser positiva")

    command = ["ffmpeg", "-y"]
    if suffix in SUPPORTED_IMAGE_SUFFIXES:
        command += ["-loop", "1", "-framerate", str(spec.fps), "-i", str(spec.background)]
    else:
        command += ["-stream_loop", "-1", "-i", str(spec.background)]

    base_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1"
    )
    timer_filters = build_timer_filters(spec.timeline)
    vf = f"{base_filter},{timer_filters}" if timer_filters else base_filter

    command += [
        "-vf", vf,
        "-t", str(spec.timeline.total_seconds),
        "-r", str(spec.fps),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-an",
        str(spec.output),
    ]
    return command
