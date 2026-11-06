#!/usr/bin/env python3
"""Passa els fons de pomodoro antics a «per a dormir» (els foscos) o a «so ambiental» (la resta).

Ús, des de la carpeta pomodoro-studio:

    python3 scripts/reclassificar-fons.py --prova     (només mostra què faria)
    python3 scripts/reclassificar-fons.py             (ho aplica)
    python3 scripts/reclassificar-fons.py --desfer    (torna a deixar-los com a pomodoro)

Només canvia el format de la fitxa .json de cada imatge: no renomena ni esborra res.
Els fons nous d'escriptori (importats amb «importar-fons.py --escriptori») no es toquen mai.
Una imatge és «fosca» si la seua lluminositat mitjana és menor que el llindar (per defecte 80 de 255);
es pot canviar amb --llindar.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
FORMAT_NAMES = {"dormir": "per a dormir", "ambient": "so ambiental", "pomodoro": "pomodoro"}


def brightness(path: Path) -> float:
    """Lluminositat mitjana de la imatge (0 = negre, 255 = blanc)."""
    with Image.open(path) as image:
        small = image.convert("L").resize((64, 36))
        pixels = list(small.getdata())
    return sum(pixels) / len(pixels)


def load(sidecar: Path) -> dict | None:
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None, folder: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reclassifica els fons de pomodoro antics.")
    parser.add_argument("--prova", action="store_true", help="només mostra què faria, sense canviar res")
    parser.add_argument("--desfer", action="store_true", help="torna a pomodoro els fons que es van moure")
    parser.add_argument("--llindar", type=float, default=80, help="lluminositat per davall de la qual un fons és fosc (0-255)")
    args = parser.parse_args(argv)
    folder = folder or ROOT / "assets" / "backgrounds"
    if not folder.is_dir():
        print(f"No trobe la carpeta {folder}")
        return 1

    counts = {"dormir": 0, "ambient": 0, "pomodoro": 0}
    for path in sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGES):
        sidecar = path.with_suffix(path.suffix + ".json")
        data = load(sidecar) if sidecar.exists() else None
        if sidecar.exists() and data is None:
            print(f"  ✘ {path.name}: no puc llegir la fitxa, no la toque")
            continue
        data = data or {}
        generation = data.setdefault("generation", {})
        if not isinstance(generation, dict):
            continue
        if args.desfer:
            if data.get("format_original") != "pomodoro":
                continue
            new, note = "pomodoro", ""
            data.pop("format_original", None)
        else:
            fmt = generation.get("format")
            if fmt is None and not sidecar.exists():
                fmt = "pomodoro" if "pomodoro" in path.stem.lower() else None
            if fmt != "pomodoro" or generation.get("layout") == "escriptori":
                continue
            try:
                light = brightness(path)
            except OSError:
                print(f"  ✘ {path.name}: no puc obrir la imatge")
                continue
            new = "dormir" if light < args.llindar else "ambient"
            note = f"  (lluminositat {light:.0f})"
            data["format_original"] = "pomodoro"
        generation["format"] = new
        counts[new] += 1
        print(f"{'(prova) ' if args.prova else ''}{path.name}  →  {FORMAT_NAMES[new]}{note}")
        if not args.prova:
            sidecar.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    verb = "Es mourien" if args.prova else "Mogudes"
    if args.desfer:
        print(f"\n{verb} a pomodoro: {counts['pomodoro']}")
    else:
        print(f"\n{verb} a «per a dormir»: {counts['dormir']} · a «so ambiental»: {counts['ambient']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
