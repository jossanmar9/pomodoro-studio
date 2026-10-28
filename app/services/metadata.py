"""Fitxers finals i paquet de publicació."""
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services.timer import TimelineSummary, build_chapters
from app.themes import publication_theme

MAX_TITLE = 100
MAX_DESCRIPTION = 5000
MAX_TAGS = 500
PUBLICATION_FILES = ("video.mp4", "thumbnail.jpg", "title.txt", "description.txt", "chapters.txt", "tags.txt", "metadata.json")


@dataclass(frozen=True)
class PublicationDraft:
    title: str
    description: str
    chapters: str
    tags: str = ""
    language: str = "en"


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


def default_publication(*, theme: str, focus: int, pause: int, duration: int, timeline: TimelineSummary) -> PublicationDraft:
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
    tags = f"pomodoro, study with me, focus ambience, study timer, {public_theme.lower()}"
    return PublicationDraft(title, description, chapters, tags)


def _starts_at_zero(chapters: str) -> bool:
    """Accepta els formats de capítols habituals i el HH:MM:SS generat internament."""
    lines = [line.strip() for line in chapters.splitlines() if line.strip()]
    if not lines:
        return False
    timestamp = lines[0].split(maxsplit=1)[0]
    parts = timestamp.split(":")
    if len(parts) not in {2, 3} or not all(part.isdigit() for part in parts):
        return False
    return all(int(part) == 0 for part in parts)


def validate_publication(draft: PublicationDraft) -> list[str]:
    errors: list[str] = []
    if not draft.title.strip(): errors.append("El títol és obligatori")
    if len(draft.title) > MAX_TITLE: errors.append(f"El títol supera {MAX_TITLE} caràcters")
    if len(draft.description) > MAX_DESCRIPTION: errors.append(f"La descripció supera {MAX_DESCRIPTION} caràcters")
    if len(draft.tags) > MAX_TAGS: errors.append(f"Les etiquetes superen {MAX_TAGS} caràcters")
    if draft.language not in {"en", "ca", "es"}: errors.append("Idioma de publicació no admés")
    lines = [line.strip() for line in draft.chapters.splitlines() if line.strip()]
    if not lines: errors.append("Els capítols són obligatoris")
    elif not _starts_at_zero(draft.chapters): errors.append("Els capítols han de començar en 0:00")
    return errors


def write_publication_files(folder: Path, draft: PublicationDraft, data: dict) -> None:
    errors = validate_publication(draft)
    if errors: raise ValueError("; ".join(errors))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "title.txt").write_text(draft.title.strip() + "\n", encoding="utf-8")
    (folder / "description.txt").write_text(draft.description.rstrip() + "\n", encoding="utf-8")
    (folder / "chapters.txt").write_text(draft.chapters.rstrip() + "\n", encoding="utf-8")
    (folder / "tags.txt").write_text(draft.tags.strip() + "\n", encoding="utf-8")
    payload = {**data, "idioma_publicacio": draft.language, "title": draft.title.strip(), "description": draft.description.rstrip(), "chapters": draft.chapters.rstrip(), "tags": [x.strip() for x in draft.tags.split(",") if x.strip()]}
    (folder / "metadata.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_metadata(folder: Path, *, theme: str, focus: int, pause: int, duration: int, resolution: str, timeline: TimelineSummary, draft: PublicationDraft | None = None) -> None:
    chosen = draft or default_publication(theme=theme, focus=focus, pause=pause, duration=duration, timeline=timeline)
    data = {"tema": theme, "public_theme": publication_theme(theme), "concentracio_min": focus, "descans_min": pause, "duracio_min": duration, "resolucio": resolution, "sessions": timeline.sessions}
    write_publication_files(folder, chosen, data)


def build_publication_zip(folder: Path) -> Path:
    """Crea el paquet sense recomprimir MP4, que ja és un format comprimit.

    ZIP_STORED per al vídeo redueix molt CPU i temps en fitxers de diverses GB;
    els fitxers de text i la miniatura continuen usant DEFLATE.
    """
    target = folder / "publication-package.zip"
    with zipfile.ZipFile(target, "w", allowZip64=True) as archive:
        for name in PUBLICATION_FILES:
            path = folder / name
            if not path.is_file():
                continue
            compression = zipfile.ZIP_STORED if name == "video.mp4" else zipfile.ZIP_DEFLATED
            archive.write(path, arcname=name, compress_type=compression)
    return target
