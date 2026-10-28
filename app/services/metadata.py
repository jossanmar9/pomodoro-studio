"""Fitxers finals i metadades de publicació."""
import json
import re
from datetime import datetime
from pathlib import Path
from app.config import settings
from app.services.timer import TimelineSummary, build_chapters

def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value or "pomodoro"

def create_output_dir(project_id: int, theme: str) -> Path:
    root = settings.output_dir
    root.mkdir(parents=True, exist_ok=True)
    base = f"{datetime.now():%Y-%m-%d}-{slugify(theme)}-{project_id:03d}"
    target = root / base
    counter = 2
    while target.exists():
        target = root / f"{base}-{counter}"
        counter += 1
    target.mkdir(parents=True)
    return target

def write_metadata(folder: Path, *, theme: str, focus: int, pause: int, duration: int, resolution: str, timeline: TimelineSummary) -> None:
    hours = duration / 60
    duration_label = f"{hours:g}H" if duration >= 60 else f"{duration} min"
    title = f"{duration_label} {theme} Pomodoro | {focus}/{pause} Study Timer | Focus Ambience"
    description = (
        f"Sessió Pomodoro de {duration} minuts ambientada en {theme}. "
        f"Intervals de {focus} minuts de concentració i {pause} minuts de descans.\n\n"
        "Contingut original creat amb Pomodoro Studio.\n\n"
        + build_chapters(timeline)
    )
    chapters = build_chapters(timeline)
    data = {"tema": theme, "concentracio_min": focus, "descans_min": pause, "duracio_min": duration, "resolucio": resolution, "sessions": timeline.sessions}
    (folder / "title.txt").write_text(title + "\n", encoding="utf-8")
    (folder / "description.txt").write_text(description + "\n", encoding="utf-8")
    (folder / "chapters.txt").write_text(chapters + "\n", encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
