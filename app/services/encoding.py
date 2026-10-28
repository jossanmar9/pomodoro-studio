"""Perfils d'encoding i selecció segura del motor FFmpeg."""
from dataclasses import dataclass
from functools import lru_cache
import subprocess

ENGINES = {"auto", "cpu", "nvenc"}
QUALITY_PROFILES = {"balanced", "quality", "fast"}


@dataclass(frozen=True)
class EncodingOptions:
    engine: str = "auto"
    quality: str = "balanced"


@dataclass(frozen=True)
class EncodingPlan:
    requested_engine: str
    engine: str
    quality: str
    video_args: tuple[str, ...]


@lru_cache(maxsize=1)
def nvenc_available() -> bool:
    """Comprova una sola vegada per procés que h264_nvenc pot inicialitzar-se."""
    try:
        encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=8, check=False)
        if encoders.returncode != 0 or "h264_nvenc" not in encoders.stdout:
            return False
        probe = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "color=c=black:s=64x64:d=0.05", "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def clear_encoding_cache() -> None:
    """Força una nova detecció després d'un canvi de GPU, drivers o runtime."""
    nvenc_available.cache_clear()


def select_encoding(options: EncodingOptions, *, has_nvenc: bool | None = None) -> EncodingPlan:
    if options.engine not in ENGINES:
        raise ValueError("Motor de renderitzat no vàlid")
    if options.quality not in QUALITY_PROFILES:
        raise ValueError("Perfil de qualitat no vàlid")
    available = nvenc_available() if has_nvenc is None else has_nvenc
    engine = "nvenc" if options.engine == "auto" and available else "cpu" if options.engine == "auto" else options.engine
    if engine == "nvenc" and not available:
        engine = "cpu"
    if engine == "nvenc":
        args = {"fast": ("-c:v", "h264_nvenc", "-preset", "p4", "-cq", "24"), "balanced": ("-c:v", "h264_nvenc", "-preset", "p5", "-cq", "21"), "quality": ("-c:v", "h264_nvenc", "-preset", "p6", "-cq", "18")}[options.quality]
    else:
        args = {"fast": ("-c:v", "libx264", "-preset", "fast", "-crf", "23"), "balanced": ("-c:v", "libx264", "-preset", "medium", "-crf", "20"), "quality": ("-c:v", "libx264", "-preset", "slow", "-crf", "18")}[options.quality]
    return EncodingPlan(options.engine, engine, options.quality, args)
