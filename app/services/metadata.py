"""Fitxers finals i metadades de publicació."""
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services.timer import TimelineSummary, build_chapters
from app.themes import publication_theme


def slugify(text: str) -> str:
    normal = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", normal).strip("-")
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
    """Escriu fitxers llestos per a YouTube.

    La interfície i la documentació són en valencià, però el contingut públic es
    genera en anglés per defecte perquè els vídeos no depenen d'una llengua.
    """
    public_theme = publication_theme(theme)
    duration_label = f"{duration / 60:g}H" if duration >= 60 else f"{duration} min"
    title = f"{duration_label} {public_theme} Pomodoro | {focus}/{pause} Study Timer | Focus Ambience"
    chapters = build_chapters(timeline, language="en")
    description = (
        f"Focus for {duration} minutes in a {public_theme.lower()} ambience. "
        f"This session uses {focus}-minute focus blocks and {pause}-minute breaks.\n\n"
        "Original focus content created with Pomodoro Studio using owned or properly licensed assets.\n\n"
        f"{chapters}\n"
    )
    data = {
        "tema": theme,
        "public_theme": public_theme,
        "concentracio_min": focus,
        "descans_min": pause,
        "duracio_min": duration,
        "resolucio": resolution,
        "sessions": timeline.sessions,
        "idioma_publicacio": "en",
    }
    (folder / "title.txt").write_text(title + "\n", encoding="utf-8")
    (folder / "description.txt").write_text(description + "\n", encoding="utf-8")
    (folder / "chapters.txt").write_text(chapters + "\n", encoding="utf-8")
    (folder / "metadata.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
