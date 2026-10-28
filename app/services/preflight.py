"""Comprovacions prèvies abans de treballs pesats de renderitzat."""
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    free_bytes: int | None = None


def estimate_required_bytes(duration_seconds: int, resolution: str) -> int:
    """Estimació conservadora per evitar iniciar renders sense espai suficient."""
    try:
        width, height = (int(part) for part in resolution.lower().split("x", 1))
    except (AttributeError, ValueError) as exc:
        raise ValueError("Resolució no vàlida") from exc
    if duration_seconds <= 0 or width <= 0 or height <= 0:
        raise ValueError("Duració i resolució han de ser positives")
    pixels = width * height
    video_bps = 8_000_000 * (pixels / (1920 * 1080))
    return int((video_bps / 8) * duration_seconds * 1.35) + 256 * 1024**2


def ffmpeg_available() -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def check_render_preflight(
    output_dir: Path,
    *,
    resources: tuple[Path, ...] = (),
    duration_seconds: int | None = None,
    resolution: str | None = None,
    minimum_free_bytes: int = 512 * 1024**2,
    require_ffmpeg: bool = True,
) -> PreflightResult:
    errors: list[str] = []
    warnings: list[str] = []

    if require_ffmpeg and not ffmpeg_available():
        errors.append("FFmpeg no està disponible o no respon correctament")

    missing = [str(path) for path in resources if not path.is_file()]
    if missing:
        errors.append("Falten recursos necessaris: " + ", ".join(missing[:5]))

    required = minimum_free_bytes
    if duration_seconds is not None and resolution is not None:
        try:
            required = max(required, estimate_required_bytes(duration_seconds, resolution))
        except ValueError as exc:
            errors.append(str(exc))

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".pomodoro-write-test"
        probe.write_bytes(b"ok")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        errors.append(f"No es pot escriure en la carpeta d'eixida: {exc}")

    free_bytes: int | None = None
    try:
        free_bytes = shutil.disk_usage(output_dir).free
        if free_bytes < required:
            errors.append(
                f"Espai lliure insuficient: calen aproximadament {required // (1024**2)} MiB "
                f"i n'hi ha {free_bytes // (1024**2)} MiB"
            )
        elif free_bytes < required * 2:
            warnings.append("L'espai lliure és ajustat per a este renderitzat")
    except OSError as exc:
        warnings.append(f"No s'ha pogut comprovar l'espai lliure: {exc}")

    return PreflightResult(not errors, tuple(errors), tuple(warnings), free_bytes)
