"""Comprovacions prèvies abans de treballs pesats de renderitzat."""
from dataclasses import dataclass
from pathlib import Path
import shutil


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    free_bytes: int | None = None


def check_render_preflight(output_dir: Path, *, minimum_free_bytes: int = 2 * 1024**3) -> PreflightResult:
    errors: list[str] = []
    warnings: list[str] = []
    if shutil.which("ffmpeg") is None:
        errors.append("FFmpeg no està disponible en PATH")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        errors.append(f"No es pot escriure en la carpeta d'eixida: {exc}")

    free_bytes: int | None = None
    try:
        free_bytes = shutil.disk_usage(output_dir).free
        if free_bytes < minimum_free_bytes:
            warnings.append(f"Espai lliure baix: {free_bytes // (1024**2)} MiB disponibles")
    except OSError as exc:
        warnings.append(f"No s'ha pogut comprovar l'espai lliure: {exc}")

    return PreflightResult(not errors, tuple(errors), tuple(warnings), free_bytes)
