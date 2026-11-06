#!/usr/bin/env python3
"""Baixa els sons i la música del catàleg que encara no tens.

Ús, des de la carpeta pomodoro-studio:

    python3 scripts/descarregar-sons.py

Només baixa els fitxers que falten (no toca els que ja tens), comprova la
suma SHA-256 quan el catàleg la porta i no necessita cap paquet extra.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "assets" / "audio-catalog.json"
INCOMPETECH = "https://incompetech.com/music/royalty-free/"
HEADERS = {"User-Agent": "PomodoroStudio/1.0 (+https://github.com/jossanmar9/pomodoro-studio)"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
        while chunk := response.read(1024 * 256):
            output.write(chunk)
    partial.replace(target)


_pieces: list[dict] | None = None


def incompetech_url(title: str) -> str | None:
    """Busca el nom real del fitxer en el catàleg d'incompetech pel títol de la peça."""
    global _pieces
    if _pieces is None:
        request = urllib.request.Request(INCOMPETECH + "pieces.json", headers=HEADERS)
        with urllib.request.urlopen(request, timeout=60) as response:
            _pieces = json.load(response)
    wanted = title.casefold().strip()
    for piece in _pieces:
        if str(piece.get("title", "")).casefold().strip() == wanted and piece.get("filename"):
            return INCOMPETECH + "mp3-royaltyfree/" + urllib.parse.quote(piece["filename"])
    return None


FREESOUND_PREVIEW = re.compile(r"https://cdn\.freesound\.org/previews/\d+/\d+_\d+-(?:hq|lq)\.mp3")


def freesound_url(page: str) -> str:
    """Adreça de l'MP3 d'alta qualitat (vista prèvia) d'un so de Freesound, llegida de la seua pàgina."""
    request = urllib.request.Request(page, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        html = response.read().decode("utf-8", "replace")
    found = FREESOUND_PREVIEW.findall(html)
    if not found:
        raise ValueError("no s'ha trobat l'àudio en la pàgina de Freesound")
    best = next((u for u in found if u.endswith("-hq.mp3")), found[0])
    return best.replace("-lq.mp3", "-hq.mp3")


def fetch(entry: dict, target: Path) -> None:
    if entry.get("freesound_page"):
        download(freesound_url(entry["freesound_page"]), target)
        return
    try:
        download(entry["download_url"], target)
    except urllib.error.HTTPError as exc:
        title = entry.get("incompetech_title")
        if exc.code != 404 or not title:
            raise
        url = incompetech_url(title)
        if not url:
            raise ValueError("no s'ha trobat en incompetech.com") from None
        download(url, target)


def main() -> int:
    entries = json.loads(CATALOG.read_text(encoding="utf-8"))
    pending = [e for e in entries if e.get("download_url") and not (ROOT / e["file"]).is_file()]
    if not pending and not any(e.get("manual") and not (ROOT / e["file"]).is_file() for e in entries):
        print("Ja tens tots els sons del catàleg.")
        return 0
    print(f"Falten {len(pending)} fitxers. Baixant…\n")
    failed = 0
    for number, entry in enumerate(pending, 1):
        target = ROOT / entry["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        label = f"[{number}/{len(pending)}] {target.name} — {entry.get('title', '')}"
        try:
            fetch(entry, target)
            expected = entry.get("sha256")
            if expected and sha256(target) != expected:
                target.unlink(missing_ok=True)
                raise ValueError("la suma SHA-256 no coincidix")
            print(f"✔ {label}")
        except Exception as exc:  # una fallada no ha d'aturar la resta
            failed += 1
            print(f"✘ {label}: {exc}")
            print(f"  Pots baixar-lo a mà des de {entry.get('source_url') or entry['download_url']} i guardar-lo com {entry['file']}")
        time.sleep(0.5)  # amb calma, per respecte al servidor
    print(f"\nFet: {len(pending) - failed} baixats, {failed} amb error.")
    manual = [e for e in entries if e.get("manual") and not (ROOT / e["file"]).is_file()]
    if manual:
        print(f"\nHi ha {len(manual)} peces que cal baixar a mà (la web demana iniciar sessió):")
        for entry in manual:
            print(f"  • {entry['title']} ({entry.get('album', '')}): {entry['source_url']} → guarda-la com {entry['file']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
