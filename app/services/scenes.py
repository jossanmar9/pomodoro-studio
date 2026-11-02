"""Temes de temporada: un sol tema per estació o festa amb diverses escenes (fons).

Cada fons d'un tema de temporada és una «escena» (p. ex. «Porxo d'estiu» dins
d'«Estiu»). El nom del fitxer comença pel nom de l'escena, i l'escena diu quin
efecte de moviment li va bé i si és a l'aire lliure.
"""
from __future__ import annotations

import re
import unicodedata


def slugify(text: str) -> str:
    normal = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", normal).strip("-")


# Tema → (nom públic en anglés, icona, efecte per defecte, descripció visual per a prompts)
SEASONS: dict[str, tuple[str, str, str, tuple[str, str, str]]] = {
    "Estiu": ("Summer", "☀️", "pols", ("cozy summer scene", "warm golden summer light, open windows, sea, fields and warm evenings", "cozy")),
    "Tardor": ("Autumn", "🍂", "pols", ("cozy autumn scene", "red and golden trees, falling leaves, soft rain and warm lamps", "cozy")),
    "Primavera": ("Spring", "🌸", "pols", ("cozy spring scene", "cherry blossoms, fresh flowers, soft bright light and green leaves", "cozy")),
    "Hivern": ("Winter", "❄️", "pols", ("cozy winter scene", "snow outside the windows, warm fireplaces and hot drinks", "cozy")),
    "Nadal": ("Christmas", "🎄", "pols", ("cozy christmas scene", "christmas trees with warm lights, garlands, candles and snow outside", "cozy")),
    "Halloween": ("Halloween", "🎃", "boira", ("cozy halloween scene", "carved pumpkins with candlelight, autumn leaves, a full moon and light fog", "cozy")),
    "Pasqua": ("Easter", "🐣", "pols", ("cozy easter scene", "pastel painted eggs, spring flowers and soft morning sunlight", "cozy")),
}

# Escena → (tema, efecte, a l'aire lliure)
SCENES: dict[str, tuple[str, str, bool]] = {
    "Porxo d'estiu": ("Estiu", "cuques", True),
    "Nit d'estiu": ("Estiu", "cuques", True),
    "Casa de la platja": ("Estiu", "pols", False),
    "Terrassa d'estiu": ("Estiu", "pols", True),
    "Camp de lavanda": ("Estiu", "pols", True),
    "Cabana de tardor": ("Tardor", "pols", False),
    "Cafeteria de tardor": ("Tardor", "pols", False),
    "Bosc de tardor": ("Tardor", "fulles", True),
    "Biblioteca de tardor": ("Tardor", "pols", False),
    "Racó de tardor": ("Tardor", "pols", False),
    "Jardí de primavera": ("Primavera", "petals", True),
    "Racó de primavera": ("Primavera", "pols", False),
    "Cafeteria de primavera": ("Primavera", "pols", False),
    "Bosc de primavera": ("Primavera", "pols", True),
    "Hivernacle de primavera": ("Primavera", "pols", False),
    "Cabana a la neu": ("Hivern", "pols", False),
    "Cafeteria d'hivern": ("Hivern", "pols", False),
    "Bosc nevat": ("Hivern", "neu", True),
    "Biblioteca d'hivern": ("Hivern", "pols", False),
    "Tren d'hivern": ("Hivern", "pols", False),
    "Cabana de Nadal": ("Nadal", "pols", False),
    "Sala de Nadal": ("Nadal", "pols", False),
    "Cafeteria de Nadal": ("Nadal", "pols", False),
    "Biblioteca de Nadal": ("Nadal", "pols", False),
    "Poble nevat": ("Nadal", "neu", True),
    "Mercat de Nadal": ("Nadal", "neu", True),
    "Cabana de Halloween": ("Halloween", "boira", False),
    "Biblioteca de Halloween": ("Halloween", "boira", False),
    "Cafeteria de Halloween": ("Halloween", "pols", False),
    "Poble de Halloween": ("Halloween", "boira", True),
    "Matí de Pasqua": ("Pasqua", "pols", False),
    "Jardí de Pasqua": ("Pasqua", "petals", True),
    "Pastisseria de Pasqua": ("Pasqua", "pols", False),
}


def season_slugs(theme: str) -> list[str]:
    """Prefixos de fitxer d'un tema de temporada: el tema mateix i totes les seues escenes."""
    if theme not in SEASONS:
        return []
    return [slugify(theme)] + [slugify(scene) for scene, (season, _, _) in SCENES.items() if season == theme]


def scene_for(stem: str) -> str | None:
    """Escena d'un fitxer pel seu nom (el prefix més llarg que encaixa)."""
    slug = slugify(stem)
    matches = [scene for scene in SCENES if slug == slugify(scene) or slug.startswith(slugify(scene) + "-")]
    return max(matches, key=lambda scene: len(slugify(scene))) if matches else None
