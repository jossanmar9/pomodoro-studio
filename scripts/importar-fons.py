#!/usr/bin/env python3
"""Importa una carpeta d'imatges de fons fetes amb ChatGPT.

Ús, des de la carpeta pomodoro-studio:

    python3 scripts/importar-fons.py ~/amber/fons --anime
    python3 scripts/importar-fons.py ~/Baixades/fons            (realistes)
    python3 scripts/importar-fons.py ~/amber/fons --anime --prova   (només ho mostra)
    python3 scripts/importar-fons.py ~/fons-escriptori --escriptori  (pomodoros nous d'escriptori i finestra)

Les imatges han de dur el nom dels prompts:
    «Pomodoro + Cabana amb pluja + Pluja i llar de foc.png»     (format + tema + so)
    «Nadal + Cabana de Nadal + Llar de foc.png»                 (temporada + escena + so)

Per a cada imatge, en fa una còpia en assets/backgrounds amb el nom que Pomodoro
entén (p. ex. «cabana-amb-pluja-pluja-llar-pomodoro-anime.png») i la seua fitxa .json.
Les originals no es toquen. Les que ja s'havien importat no es tornen a copiar.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.autopilot_plan import AUTO_THEMES, ENVIRONMENTS, slugify  # noqa: E402
from app.services.scenes import SCENES  # noqa: E402

FORMATS = {"pomodoro": "pomodoro", "per a llegir": "llegir", "per a dormir": "dormir", "so ambiental": "ambient",
           "partida de rol": "rol", "respiracio guiada": "respiracio"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}


def plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").casefold().strip()


ENV_BY_LABEL = {plain(env.label): key for key, env in ENVIRONMENTS.items()}
THEME_BY_NAME = {plain(t): t for t in AUTO_THEMES}
SCENE_BY_NAME = {plain(s): s for s in SCENES}


def image_size(path: Path) -> tuple[int | None, int | None]:
    with path.open("rb") as handle:
        head = handle.read(24)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", head[16:24])
    return None, None


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def plan(path: Path, anime: bool, desk: bool = False) -> tuple[str, dict] | str:
    """Nom nou i fitxa de la imatge, o el motiu pel qual no es pot importar."""
    parts = [p.strip() for p in unicodedata.normalize("NFC", path.stem).split(" + ")]
    if len(parts) != 3:
        return "el nom no té la forma «A + B + C»"
    first, second, sound = parts
    environment = ENV_BY_LABEL.get(plain(sound))
    if not environment:
        return f"no conec el so «{sound}»"
    suffix = "-anime" if anime else ""
    if plain(first) in FORMATS:
        theme = THEME_BY_NAME.get(plain(second))
        if not theme:
            return f"no conec el tema «{second}»"
        fmt, scene = FORMATS[plain(first)], None
        name = f"{slugify(theme)}-{environment}-{fmt}{suffix}{path.suffix.lower()}"
    else:
        scene = SCENE_BY_NAME.get(plain(second))
        if not scene:
            return f"no conec l'escena «{second}»"
        theme, fmt = SCENES[scene][0], None
        name = f"{slugify(scene)}-{environment}-temporada{suffix}{path.suffix.lower()}"
    width, height = image_size(path)
    meta = {
        "generation": {"format": fmt, "environment": environment, "scene": scene, "theme": theme,
                       "style": "anime" if anime else "realista", "width": width, "height": height},
        "provider": "import", "model": "ChatGPT", "license": "Generated with ChatGPT for The Amber Window",
        "source_notes": path.name, "sha256": "",
    }
    if desk:
        meta["generation"]["layout"] = "escriptori"
    return name, meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa imatges de fons a Pomodoro Studio.")
    parser.add_argument("carpeta", type=Path, help="carpeta amb les imatges")
    parser.add_argument("--anime", action="store_true", help="les imatges són d'estil anime")
    parser.add_argument("--escriptori", action="store_true", help="són els fons nous d'escriptori davant de la finestra")
    parser.add_argument("--prova", action="store_true", help="només mostra què faria, sense copiar res")
    args = parser.parse_args()
    source = args.carpeta.expanduser()
    if not source.is_dir():
        print(f"No trobe la carpeta {source}")
        return 1
    target_dir = ROOT / "assets" / "backgrounds"
    target_dir.mkdir(parents=True, exist_ok=True)
    known = {}
    for sidecar in target_dir.glob("*.json"):
        try:
            known[json.loads(sidecar.read_text(encoding="utf-8")).get("sha256")] = sidecar.stem
        except (OSError, ValueError):
            pass

    copied, skipped, problems = 0, 0, []
    for path in sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in IMAGES):
        result = plan(path, args.anime, args.escriptori)
        if isinstance(result, str):
            problems.append(f"{path.name}: {result}")
            continue
        name, meta = result
        meta["sha256"] = digest(path)
        if meta["sha256"] in known:
            skipped += 1
            continue
        stem, ext = Path(name).stem, Path(name).suffix
        target, n = target_dir / name, 2
        while target.exists():
            target, n = target_dir / f"{stem}-{n}{ext}", n + 1
        print(f"{'(prova) ' if args.prova else ''}{path.name}  →  {target.name}")
        if not args.prova:
            shutil.copy2(path, target)
            target.with_suffix(target.suffix + ".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        copied += 1

    print(f"\n{'Es copiarien' if args.prova else 'Copiades'}: {copied} · Ja hi eren: {skipped} · No importades: {len(problems)}")
    for problem in problems:
        print(f"  ✘ {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
