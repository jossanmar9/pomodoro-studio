"""Tipografies lliures per ambientació (comptador del vídeo i miniatura).

Totes estan en assets/fonts/ amb la seua llicència (SIL OFL 1.1 o Apache 2.0),
que permeten usar-les en vídeos, també monetitzats. Si falta un fitxer, es torna
a DejaVu Sans perquè el renderitzat no falle mai per una tipografia.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FontStyle:
    name: str
    label: str              # FOCUS / BREAK / SESSION
    digits: str             # 24:59
    separator: str = " · "  # per al text de la miniatura
    uppercase_labels: bool = True


# Rutes relatives a assets/fonts/
IM_FELL = "im-fell-english/IMFeENrm28P.ttf"
IM_FELL_SC = "im-fell-english/IMFeENsc28P.ttf"
MEDIEVAL_SHARP = "medievalsharp/MedievalSharp.ttf"
FRAKTUR = "unifraktur-maguntia/UnifrakturMaguntia-Book.ttf"
CINZEL = "cinzel/Cinzel-SemiBold.ttf"
CINZEL_DECO = "cinzel-decorative/CinzelDecorative-Bold.ttf"
UNCIAL = "uncial-antiqua/UncialAntiqua-Regular.ttf"
LORA = "lora/Lora-Variable.ttf"
PLAYFAIR = "playfair-display/PlayfairDisplay-Variable.ttf"
PIRATA = "pirata-one/PirataOne-Regular.ttf"
ZEN_ANTIQUE = "zen-antique/ZenAntique-Latin.ttf"
ORBITRON = "orbitron/Orbitron-Variable.ttf"
SPECIAL_ELITE = "special-elite/SpecialElite-Regular.ttf"
CORMORANT = "cormorant-garamond/CormorantGaramond-SemiBold.ttf"
COMFORTAA = "comfortaa/Comfortaa-Variable.ttf"
BEBAS = "bebas-neue/BebasNeue-Regular.ttf"
JOSEFIN = "josefin-sans/JosefinSans-Variable.ttf"

THEME_FONTS: dict[str, FontStyle] = {
    "Biblioteca medieval": FontStyle("Llibre antic", IM_FELL_SC, IM_FELL),
    "Biblioteca màgica": FontStyle("Inscripció màgica", CINZEL_DECO, CINZEL),
    "Biblioteca èlfica": FontStyle("Uncial", UNCIAL, UNCIAL),
    "Taverna medieval": FontStyle("Taverna", MEDIEVAL_SHARP, MEDIEVAL_SHARP),
    "Torre de l'alquimista": FontStyle("Alquimista", CINZEL_DECO, IM_FELL),
    "Castell gòtic": FontStyle("Gòtica", FRAKTUR, CINZEL, uppercase_labels=False),
    "Cabana amb pluja": FontStyle("Acollidora", LORA, LORA),
    "Biblioteca victoriana": FontStyle("Victoriana", PLAYFAIR, PLAYFAIR),
    "Vaixell pirata": FontStyle("Pirata", PIRATA, PIRATA),
    "Roma antiga": FontStyle("Romana", CINZEL, CINZEL),
    "Grècia antiga": FontStyle("Clàssica", CINZEL, CINZEL),
    "Japó feudal": FontStyle("Estampa antiga", ZEN_ANTIQUE, ZEN_ANTIQUE),
    "Nau espacial": FontStyle("Futurista", ORBITRON, ORBITRON, separator=" / "),
    "Búnquer postapocalíptic": FontStyle("Màquina d'escriure", SPECIAL_ELITE, SPECIAL_ELITE),
    "Bosc": FontStyle("Natural", CORMORANT, CORMORANT),
    "Observatori": FontStyle("Astronòmica", CORMORANT, CINZEL),
    "Cafeteria acollidora": FontStyle("Cafeteria", COMFORTAA, COMFORTAA),
    "Cafeteria moderna": FontStyle("Moderna", JOSEFIN, JOSEFIN),
    "Cafeteria a Nova York": FontStyle("Nova York", BEBAS, BEBAS),
    "Cafeteria a Tòquio": FontStyle("Tòquio", JOSEFIN, ZEN_ANTIQUE),
    "Cafeteria a París": FontStyle("París", PLAYFAIR, PLAYFAIR),
    "Parc a la ciutat": FontStyle("Parc", CORMORANT, CORMORANT),
    "Apartament a la ciutat": FontStyle("Apartament", LORA, LORA),
    "Racó de lectura": FontStyle("Llibre", PLAYFAIR, LORA),
    "Masmorra": FontStyle("Masmorra", FRAKTUR, CINZEL, uppercase_labels=False),
    "Campament d'aventurers": FontStyle("Aventura", MEDIEVAL_SHARP, MEDIEVAL_SHARP),
    "Cova del drac": FontStyle("Drac", CINZEL_DECO, CINZEL),
}


@dataclass(frozen=True)
class ResolvedFonts:
    label: Path | None
    digits: Path | None
    separator: str = " · "
    uppercase_labels: bool = True


def _existing(relative: str, root: Path) -> Path | None:
    path = (root / relative).resolve()
    if path.parent.parent != root.resolve() or not path.is_file():
        return None
    return path


def fonts_for_theme(theme: str, *, root: Path | None = None) -> ResolvedFonts:
    """Fitxers de tipografia de l'ambientació; None vol dir «usa DejaVu Sans»."""
    style = THEME_FONTS.get(theme)
    if style is None:
        return ResolvedFonts(None, None)
    if root is None:
        from app.config import settings  # import tardà: el renderitzador no depén de la configuració
        root = settings.assets_dir / "fonts"
    base = root
    label = _existing(style.label, base)
    digits = _existing(style.digits, base)
    separator = style.separator if label else " · "
    return ResolvedFonts(label, digits, separator, style.uppercase_labels)
