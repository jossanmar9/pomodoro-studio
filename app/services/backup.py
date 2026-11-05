"""Còpia de seguretat setmanal de les dades que no es poden tornar a fer.

Es copien la base de dades (vídeos, calendari, estat dels reels), el fitxer .env i les claus
de YouTube i d'Instagram. Els vídeos, les imatges i els sons no: ocupen molt i es poden refer.
Cada còpia va en una carpeta amb la data; es guarden les últimes `backup_keep`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import threading

from app.config import settings

logger = logging.getLogger(__name__)
PREFIX = "pomodoro-"


def _database_file() -> Path | None:
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        return None
    path = Path(url.removeprefix("sqlite:///"))
    return path if path.is_file() else None


def _extra_files() -> list[Path]:
    files = [Path(".env"), settings.youtube_token_file, settings.youtube_client_secrets, settings.instagram_token_file,
             settings.youtube_playlists_file, settings.youtube_stats_file]
    return [f for f in files if f.is_file()]


def backups(folder: Path | None = None) -> list[Path]:
    folder = folder or settings.backup_dir
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_dir() and p.name.startswith(PREFIX))


def last_backup_time(folder: Path | None = None) -> datetime | None:
    found = backups(folder)
    if not found:
        return None
    try:
        return datetime.strptime(found[-1].name.removeprefix(PREFIX), "%Y-%m-%d_%H%M")
    except ValueError:
        return datetime.fromtimestamp(found[-1].stat().st_mtime)


def make_backup(folder: Path | None = None, now: datetime | None = None) -> Path:
    """Fa una còpia ara mateix. Torna la carpeta creada."""
    folder = folder or settings.backup_dir
    now = now or datetime.now()
    target = folder / f"{PREFIX}{now:%Y-%m-%d_%H%M}"
    target.mkdir(parents=True, exist_ok=True)
    os.chmod(folder, 0o700)  # hi ha claus: només el teu usuari les pot llegir
    os.chmod(target, 0o700)
    database = _database_file()
    if database:
        # Còpia segura encara que Pomodoro estiga escrivint en la base de dades.
        with sqlite3.connect(database) as source, sqlite3.connect(target / database.name) as copy:
            source.backup(copy)
    for file in _extra_files():
        shutil.copy2(file, target / (file.name if file.name != ".env" else "env.txt"))
    for old in backups(folder)[:-max(1, settings.backup_keep)]:
        shutil.rmtree(old, ignore_errors=True)
    logger.info("Còpia de seguretat feta en %s", target)
    return target


def backup_if_due(folder: Path | None = None, now: datetime | None = None) -> Path | None:
    """Fa la còpia si l'última té més de `backup_every_days` dies (o si no n'hi ha cap)."""
    now = now or datetime.now()
    last = last_backup_time(folder)
    if last and now - last < timedelta(days=settings.backup_every_days):
        return None
    return make_backup(folder, now)


def backup_in_background() -> None:
    def work() -> None:
        try:
            backup_if_due()
        except Exception:
            logger.exception("No s'ha pogut fer la còpia de seguretat")
    threading.Thread(target=work, daemon=True).start()
